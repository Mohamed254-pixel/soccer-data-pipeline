"""MySQL operations for incremental ETL. No DDL or automatic migrations here."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

import pandas as pd

from db import get_connection
from load_live_matches import prepare_rows as historical_match_rows
from load_teams import prepare_team_rows, prepare_venue_rows


MATCH_COLUMNS = (
    "fixture_id", "match_date", "home_team", "away_team", "home_goals", "away_goals",
    "season", "status_short", "status_long", "elapsed", "home_api_team_id",
    "away_api_team_id", "source_observed_at",
)
MATCH_UPSERT = """
INSERT INTO live_matches (
    fixture_id, match_date, home_team, away_team, home_goals, away_goals,
    season, status_short, status_long, elapsed, home_api_team_id, away_api_team_id,
    source_observed_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    match_date=VALUES(match_date), home_team=VALUES(home_team),
    away_team=VALUES(away_team), home_goals=VALUES(home_goals),
    away_goals=VALUES(away_goals), status_short=VALUES(status_short),
    status_long=VALUES(status_long), elapsed=VALUES(elapsed),
    home_api_team_id=VALUES(home_api_team_id), away_api_team_id=VALUES(away_api_team_id),
    source_observed_at=VALUES(source_observed_at)
"""


@contextmanager
def database(write=False):
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        yield cursor
        if write:
            connection.commit()
        else:
            connection.rollback()
    except Exception:
        connection.rollback()
        raise
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            connection.close()


def require_schema(cursor):
    cursor.execute("SELECT enabled FROM pipeline_control WHERE control_id=1")
    row = cursor.fetchone()
    if not row or not row["enabled"]:
        raise RuntimeError("Phase 2 is disabled. Review and apply migration 003 first.")


def extraction_state(seasons, run_id, started_at):
    with database(write=True) as cursor:
        require_schema(cursor)
        # Claim the entire ETL before contacting the source. This also prevents
        # local extraction from racing an active Airflow run.
        lock_run(cursor, run_id, started_at, claim=True)
        states = {}
        for season in seasons:
            cursor.execute("SELECT * FROM season_sync_state WHERE season=%s", (season,))
            states[season] = cursor.fetchone()
        # Future NS fixtures are handled by the moving window. Uncertain or overdue
        # fixtures must be polled by ID regardless of their original kickoff date.
        cursor.execute("""
            SELECT fixture_id, season FROM live_matches
            WHERE season IN (""" + ",".join(["%s"] * len(seasons)) + """)
              AND (status_short IN ('TBD','PST','SUSP','INT','ABD','CANC',
                                   '1H','HT','2H','ET','BT','P','LIVE')
                   OR (status_short='NS' AND match_date <= UTC_TIMESTAMP()))
            ORDER BY fixture_id
        """, tuple(seasons))
        pending = cursor.fetchall()
    return states, pending


def lock_run(cursor, run_id, started_at, claim=False):
    cursor.execute("SELECT * FROM pipeline_control WHERE control_id=1 FOR UPDATE")
    control = cursor.fetchone()
    if not control or not control["enabled"]:
        raise RuntimeError("Phase 2 is disabled.")
    if control.get("last_completed_run_id") == run_id:
        raise RuntimeError("This run ID has already completed. Use a new ID for a fresh extraction.")
    owner = control["pending_run_id"]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expired = control.get("pending_lease_until") is not None and control["pending_lease_until"] < now
    if owner and owner != run_id:
        if not (claim and expired):
            raise RuntimeError("Another pipeline run is pending. Resume it, wait for its lease, or explicitly release it first.")
    completed = control["last_completed_at"]
    if completed and started_at <= completed:
        raise RuntimeError("This staging batch is stale or already completed.")
    if claim:
        cursor.execute("UPDATE pipeline_control SET pending_run_id=%s,pending_lease_until=%s WHERE control_id=1", (run_id, now + timedelta(hours=6)))
    elif owner != run_id:
        raise RuntimeError("Load teams and venues before loading matches or validating.")
    else:
        cursor.execute("UPDATE pipeline_control SET pending_lease_until=%s WHERE control_id=1", (now + timedelta(hours=6),))


def load_team_batches(manifest, batches, started_at):
    # Validate every season before opening a write transaction.
    if sorted(batch["season"] for batch in batches) != sorted(manifest["seasons"]) or 2024 in manifest["seasons"]:
        raise ValueError("Team batches do not match the requested nonhistorical seasons.")
    prepared = []
    for batch in batches:
        teams = prepare_team_rows(pd.DataFrame(batch["teams"]))
        if len(teams) != 20:
            raise ValueError("Each active season requires 20 team memberships.")
        venues_frame = pd.DataFrame(batch["venues"], columns=[
            "venue_id", "venue_name", "address", "city", "capacity", "surface", "image_url"
        ])
        venues = prepare_venue_rows(venues_frame)
        venue_ids = {row[0] for row in venues}
        if any(row[9] is not None and row[9] not in venue_ids for row in teams):
            raise ValueError("Teams reference missing venues.")
        prepared.append((batch["season"], teams, venues, batch))
    with database(write=True) as cursor:
        lock_run(cursor, manifest["run_id"], started_at)
        for season, teams, venues, batch in prepared:
            # Preserve existing canonical metadata, including the complete 2024
            # snapshot. Current descriptions belong in the season snapshots below.
            for row in venues:
                cursor.execute("""
                    INSERT INTO venues (venue_id,venue_name,address,city,capacity,surface,image_url)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE venue_id=venues.venue_id
                """, row)
            for row in teams:
                cursor.execute("SELECT api_team_id FROM teams WHERE team_name=%s AND league=%s", (row[1], row[4]))
                collision = cursor.fetchone()
                if collision and collision["api_team_id"] != row[0]:
                    raise ValueError("Team identity conflicts with an existing unique key.")
                cursor.execute("""
                    INSERT INTO teams (api_team_id,team_name,team_code,country,league,stadium,
                                       founded,is_national,logo_url,venue_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE api_team_id=teams.api_team_id
                """, row)
            venues_by_id = {row["venue_id"]: row for row in batch["venues"]}
            for team in batch["teams"]:
                cursor.execute("""
                    INSERT INTO season_teams (season,api_team_id,team_name,venue_id,team_data,venue_data)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE team_name=VALUES(team_name), venue_id=VALUES(venue_id),
                        team_data=VALUES(team_data), venue_data=VALUES(venue_data)
                """, (season, team["api_team_id"], team["team_name"], team["venue_id"],
                      json.dumps(team), json.dumps(venues_by_id.get(team["venue_id"]))))


def upsert_matches(cursor, rows):
    """Use fixture_id as identity, guarding MySQL's other unique constraint."""
    seen_ids, natural_keys = set(), set()
    for row in rows:
        natural_key = row[1:4]
        if row[0] in seen_ids or (row[1] is not None and natural_key in natural_keys):
            raise ValueError("Duplicate fixture identity or date/team key within the batch.")
        seen_ids.add(row[0])
        natural_keys.add(natural_key)
    for row in rows:
        cursor.execute("SELECT season, source_observed_at FROM live_matches WHERE fixture_id=%s FOR UPDATE", (row[0],))
        existing = cursor.fetchone()
        if existing:
            if existing["season"] != row[6] or existing["season"] == 2024:
                raise ValueError("Fixture season identity conflict or protected historical fixture.")
            if existing["source_observed_at"] and existing["source_observed_at"] > row[12]:
                raise ValueError("Refusing an older observation of a fixture.")
        cursor.execute("""
            SELECT fixture_id FROM live_matches
            WHERE match_date=%s AND home_team=%s AND away_team=%s AND fixture_id<>%s
        """, (row[1], row[2], row[3], row[0]))
        if cursor.fetchone():
            raise ValueError("Fixture conflicts with the date/team unique key.")
        # Check and write each row inside the one caller transaction. The next
        # check then also sees MySQL collation-equivalent keys from this batch.
        cursor.execute(MATCH_UPSERT, row)


def load_match_batch(manifest, rows, started_at):
    if any(row[6] not in manifest["seasons"] or row[6] == 2024 for row in rows):
        raise ValueError("Match batch contains an unrequested or protected season.")
    with database(write=True) as cursor:
        lock_run(cursor, manifest["run_id"], started_at)
        upsert_matches(cursor, rows)


def assert_historical_snapshot(cursor, root, metadata=True):
    """Compare every original match/team/venue value, not just row counts."""
    snapshot = Path(os.getenv("HISTORICAL_DATA_DIR", root / "data"))
    expected_matches = sorted(historical_match_rows(pd.read_csv(snapshot / "live_matches.csv")))
    cursor.execute("SELECT fixture_id,match_date,home_team,away_team,home_goals,away_goals FROM live_matches "
                   + ("WHERE season=2024 " if metadata else "") + "ORDER BY fixture_id")
    actual = [tuple(row.values()) for row in cursor.fetchall()]
    if actual != expected_matches or len(actual) != 380:
        raise ValueError("Historical match snapshot differs from the protected 2024 CSV.")
    checks = [
        ("teams", "api_team_id,team_name,team_code,country,league,stadium,founded,is_national,logo_url,venue_id",
         prepare_team_rows(pd.read_csv(snapshot / "teams.csv"))),
        ("venues", "venue_id,venue_name,address,city,capacity,surface,image_url",
         prepare_venue_rows(pd.read_csv(snapshot / "venues.csv"))),
    ]
    for table, columns, expected in checks:
        key = columns.split(",")[0]
        ids = [row[0] for row in expected]
        cursor.execute(f"SELECT {columns} FROM {table} WHERE {key} IN (" + ",".join(["%s"] * len(ids)) + f") ORDER BY {key}", tuple(ids))
        actual = [tuple(row.values()) for row in cursor.fetchall()]
        if actual != sorted(expected):
            raise ValueError(f"Historical {table} snapshot differs from the protected CSV.")


def validate_seasons(cursor, seasons):
    cursor.execute("SELECT COUNT(*) AS total FROM live_matches WHERE season IS NULL OR status_short IS NULL")
    if cursor.fetchone()["total"]:
        raise ValueError("Unclassified fixture rows exist.")
    for season in seasons:
        cursor.execute("""
            SELECT COUNT(*) AS total, COUNT(DISTINCT fixture_id) AS unique_ids,
              COALESCE(SUM(status_short IS NULL OR status_short NOT IN
                ('TBD','NS','1H','HT','2H','ET','BT','P','SUSP','INT','FT','AET','PEN','PST','CANC','ABD','AWD','WO','LIVE')
                OR (match_date IS NULL AND status_short NOT IN ('TBD','PST'))
                OR home_api_team_id IS NULL OR away_api_team_id IS NULL
                OR (status_short IN ('FT','AET','PEN') AND (home_goals IS NULL OR away_goals IS NULL))),0) AS invalid
            FROM live_matches WHERE season=%s
        """, (season,))
        result = cursor.fetchone()
        if result["total"] > 380 or result["total"] != result["unique_ids"] or result["invalid"]:
            raise ValueError(f"Invalid fixture counts/status data for season {season}.")
        cursor.execute("SELECT COUNT(*) AS total FROM season_teams WHERE season=%s", (season,))
        if cursor.fetchone()["total"] != 20:
            raise ValueError(f"Expected 20 team memberships for season {season}.")
        print(f"PASS | season {season} | fixtures={result['total']} | unique={result['unique_ids']}")


def finish_run(manifest, started_at, root):
    with database(write=True) as cursor:
        cursor.execute("SELECT * FROM pipeline_control WHERE control_id=1 FOR UPDATE")
        control = cursor.fetchone()
        if control and control["last_completed_run_id"] == manifest["run_id"]:
            if control["last_completed_at"] != started_at:
                raise ValueError("A completed run ID cannot be reused with another staging observation.")
            print("Validation/checkpoint commit already completed for this run.")
            return
        lock_run(cursor, manifest["run_id"], started_at)
        assert_historical_snapshot(cursor, root)
        validate_seasons(cursor, manifest["seasons"])
        # Verify staged rows really reached MySQL, including their exact latest
        # values. A process dying after commit can safely retry before this step.
        from incremental import match_rows
        for row in match_rows(manifest["matches"], started_at):
            cursor.execute("SELECT " + ",".join(MATCH_COLUMNS) + " FROM live_matches WHERE fixture_id=%s", (row[0],))
            actual = cursor.fetchone()
            if not actual or tuple(actual.values()) != row:
                raise ValueError("Loaded fixture does not match this run's staging batch.")
        for season in manifest["seasons"]:
            full_at = started_at if manifest["plans"][str(season)]["full"] else None
            cursor.execute("""
                INSERT INTO season_sync_state (season,last_success_at,last_full_sync_at)
                VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE
                    last_success_at=VALUES(last_success_at),
                    last_full_sync_at=COALESCE(VALUES(last_full_sync_at),last_full_sync_at)
            """, (season, started_at, full_at))
        cursor.execute("UPDATE pipeline_control SET pending_run_id=NULL,pending_lease_until=NULL,last_completed_at=%s,last_completed_run_id=%s WHERE control_id=1", (started_at, manifest["run_id"]))
    print("PASS | protected 2024 snapshot unchanged | checkpoints committed")


def release_run(run_id):
    with database(write=True) as cursor:
        cursor.execute("SELECT pending_run_id FROM pipeline_control WHERE control_id=1 FOR UPDATE")
        row = cursor.fetchone()
        if not row or row["pending_run_id"] != run_id:
            raise ValueError("The supplied run ID does not own the pending run.")
        cursor.execute("UPDATE pipeline_control SET pending_run_id=NULL,pending_lease_until=NULL WHERE control_id=1")
    print("Released pending run. Existing rows retained; checkpoint not advanced.")
