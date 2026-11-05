"""Opt-in real MySQL verification in fresh randomly named test databases.

No application .env or API credentials are used. CI provides MySQL 8.0. Local
execution can use a separate --skip-networking instance via an explicit socket.
"""

from copy import deepcopy
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from uuid import uuid4

import mysql.connector
import pandas as pd
import pytest

import incremental as etl
import migrate_phase2 as migration
import season_store as store
from load_live_matches import UPSERT_SQL, prepare_rows
from load_teams import TEAM_UPSERT_SQL, VENUE_UPSERT_SQL, prepare_team_rows, prepare_venue_rows


ROOT = Path(__file__).resolve().parents[2]
CONNECT = mysql.connector.connect
pytestmark = pytest.mark.skipif(
    not (os.getenv("PIPELINE_TEST_MYSQL_SOCKET") or os.getenv("PIPELINE_TEST_MYSQL_HOST")),
    reason="Real MySQL integration tests require an explicitly configured test server.",
)


@pytest.fixture
def mysql_database(monkeypatch):
    options = {"user": "root", "password": os.getenv("PIPELINE_TEST_MYSQL_PASSWORD", "")}
    if os.getenv("PIPELINE_TEST_MYSQL_SOCKET"):
        options["unix_socket"] = os.environ["PIPELINE_TEST_MYSQL_SOCKET"]
    else:
        options.update(host=os.environ["PIPELINE_TEST_MYSQL_HOST"], port=int(os.getenv("PIPELINE_TEST_MYSQL_PORT", "3306")))
    admin = CONNECT(**options)
    name = "pl_test_" + uuid4().hex
    cursor = admin.cursor()
    cursor.execute(f"CREATE DATABASE {name}")
    cursor.close()
    connection = CONNECT(**options, database=name)
    cursor = connection.cursor(dictionary=True)
    for statement in migration.statements(ROOT / "sql/schema.sql"):
        text = statement.strip().upper()
        if text.startswith(("CREATE DATABASE", "USE ")):
            continue
        cursor.execute(statement)
    cursor.executemany(VENUE_UPSERT_SQL, prepare_venue_rows(pd.read_csv(ROOT / "data/venues.csv")))
    cursor.executemany(TEAM_UPSERT_SQL, prepare_team_rows(pd.read_csv(ROOT / "data/teams.csv")))
    cursor.executemany(UPSERT_SQL, prepare_rows(pd.read_csv(ROOT / "data/live_matches.csv")))
    connection.commit()
    monkeypatch.setattr(store, "get_connection", lambda: CONNECT(**options, database=name))
    try:
        yield connection, cursor
    finally:
        cursor.close()
        connection.close()
        # Only this fixture's uniquely named database is ever removed.
        assert name.startswith("pl_test_") and len(name) == 40
        cleanup = admin.cursor()
        cleanup.execute(f"DROP DATABASE {name}")
        cleanup.close()
        admin.close()


def team_batch():
    teams = json.loads(pd.read_csv(ROOT / "data/teams.csv").to_json(orient="records"))
    venues = json.loads(pd.read_csv(ROOT / "data/venues.csv").to_json(orient="records"))
    return {"season": 2026, "teams": teams, "venues": venues}


def match(status="FT", goals=(2, 1), fixture_id=2000001, date="2026-11-01T16:30:00Z", season=2026):
    return etl.parse_fixture({
        "fixture": {"id": fixture_id, "date": date, "status": {"short": status, "long": "Test status", "elapsed": None}},
        "league": {"id": 39, "season": season},
        "teams": {"home": {"id": 33, "name": "Manchester United"}, "away": {"id": 34, "name": "Newcastle"}},
        "goals": {"home": goals[0], "away": goals[1]},
    }, season)


def manifest(run_id, at, matches, seasons=None):
    seasons = seasons or [2026]
    return {"run_id": run_id, "started_at": at.isoformat(), "seasons": seasons,
            "plans": {str(season): {"full": True} for season in seasons}, "matches": matches}


def complete_run(run, at):
    store.extraction_state(run["seasons"], run["run_id"], at)
    batches = []
    for season in run["seasons"]:
        batch = team_batch()
        batch["season"] = season
        batches.append(batch)
    store.load_team_batches(run, batches, at)
    store.load_match_batch(run, etl.match_rows(run["matches"], at), at)
    store.finish_run(run, at, ROOT)


def test_up_down_reapply_preserves_all_original_values(mysql_database):
    connection, cursor = mysql_database
    migration.apply(connection, cursor)
    migration.apply(connection, cursor)
    store.assert_historical_snapshot(cursor, ROOT)
    migration.rollback(connection, cursor)
    assert "season" not in migration.column_names(cursor)
    store.assert_historical_snapshot(cursor, ROOT, metadata=False)
    migration.apply(connection, cursor)
    cursor.execute("SELECT COUNT(*) AS total FROM season_teams WHERE season=2024")
    assert cursor.fetchone()["total"] == 20


def test_partial_up_migration_resumes_without_reclassifying_data(mysql_database):
    connection, cursor = mysql_database
    for statement in migration.statements(migration.MIGRATIONS / "003_incremental_etl.up.sql"):
        cursor.execute(statement)
        connection.commit()
        if "-- step: metadata" in statement:
            break
    migration.apply(connection, cursor)
    store.assert_historical_snapshot(cursor, ROOT)


def test_migration_refuses_an_unverified_snapshot_before_ddl(mysql_database):
    connection, cursor = mysql_database
    cursor.execute("UPDATE live_matches SET home_goals=100 WHERE fixture_id=(SELECT fixture_id FROM (SELECT MIN(fixture_id) AS fixture_id FROM live_matches) x)")
    connection.commit()
    with pytest.raises(ValueError, match="Historical match snapshot"):
        migration.apply(connection, cursor)
    assert "season" not in migration.column_names(cursor)


def test_incremental_insert_postpone_finish_correct_and_rerun(mysql_database):
    connection, cursor = mysql_database
    migration.apply(connection, cursor)
    connection.commit()
    start = datetime(2026, 11, 2, 6)
    versions = [match("NS", (None, None)), match("PST", (None, None), date=None),
                match("FT", (2, 1), date="2026-11-15T16:30:00Z"),
                match("FT", (3, 1), date="2026-11-15T16:30:00Z"),
                match("FT", (3, 1), date="2026-11-15T16:30:00Z")]
    for index, record in enumerate(versions):
        at = start + timedelta(days=index)
        run = manifest(f"run-{index}", at, [record])
        complete_run(run, at)
        # Retrying validation after its DB commit is idempotent.
        store.finish_run(run, at, ROOT)
        connection.commit()
        cursor.execute("SELECT COUNT(*) AS total FROM live_matches")
        assert cursor.fetchone()["total"] == 381
    connection.commit()
    cursor.execute("SELECT home_goals,away_goals,status_short FROM live_matches WHERE fixture_id=2000001")
    assert tuple(cursor.fetchone().values()) == (3, 1, "FT")
    store.assert_historical_snapshot(cursor, ROOT)
    with pytest.raises(ValueError, match="Rollback refused"):
        migration.rollback(connection, cursor)
    connection.rollback()


def test_multiple_seasons_and_empty_window_advance_separate_checkpoints(mysql_database):
    connection, cursor = mysql_database
    migration.apply(connection, cursor)
    at = datetime(2026, 11, 2, 6)
    run = manifest("multi-season", at, [match(), match(fixture_id=1900001, season=2025, date="2025-11-01T16:30:00Z")], [2025, 2026])
    complete_run(run, at)
    noop = manifest("empty-window", at + timedelta(days=7), [], [2025, 2026])
    noop["plans"] = {"2025": {"full": False}, "2026": {"full": False}}
    complete_run(noop, at + timedelta(days=7))
    connection.commit()
    cursor.execute("SELECT * FROM season_sync_state ORDER BY season")
    rows = cursor.fetchall()
    assert [row["season"] for row in rows] == [2025, 2026]
    assert all(row["last_full_sync_at"] == at for row in rows)
    assert all(row["last_success_at"] == at + timedelta(days=7) for row in rows)
    store.assert_historical_snapshot(cursor, ROOT)


def test_failed_quality_check_retains_checkpoint_and_pending_run(mysql_database):
    connection, cursor = mysql_database
    migration.apply(connection, cursor)
    at = datetime(2026, 11, 2, 6)
    run = manifest("quality-failure", at, [match()])
    store.extraction_state([2026], run["run_id"], at)
    store.load_team_batches(run, [team_batch()], at)
    store.load_match_batch(run, etl.match_rows(run["matches"], at), at)
    cursor.execute("UPDATE live_matches SET status_short='BAD' WHERE fixture_id=2000001")
    connection.commit()
    with pytest.raises(ValueError):
        store.finish_run(run, at, ROOT)
    connection.commit()
    cursor.execute("SELECT COUNT(*) AS total FROM season_sync_state")
    assert cursor.fetchone()["total"] == 0
    cursor.execute("SELECT pending_run_id FROM pipeline_control WHERE control_id=1")
    assert cursor.fetchone()["pending_run_id"] == "quality-failure"
    store.release_run("quality-failure")
    connection.commit()
    store.assert_historical_snapshot(cursor, ROOT)


def test_duplicate_natural_keys_do_not_silently_replace_fixture_ids(mysql_database):
    connection, cursor = mysql_database
    migration.apply(connection, cursor)
    at = datetime(2026, 11, 2, 6)
    run = manifest("duplicate-natural-key", at, [match(), match(fixture_id=2000002)])
    store.extraction_state([2026], run["run_id"], at)
    store.load_team_batches(run, [team_batch()], at)
    with pytest.raises(ValueError, match="Duplicate fixture"):
        store.load_match_batch(run, etl.match_rows(run["matches"], at), at)
    connection.commit()
    cursor.execute("SELECT COUNT(*) AS total FROM live_matches")
    assert cursor.fetchone()["total"] == 380


def test_mysql_collation_collision_rolls_back_the_entire_match_batch(mysql_database):
    connection, cursor = mysql_database
    migration.apply(connection, cursor)
    at = datetime(2026, 11, 2, 6)
    first = match()
    second = deepcopy(first)
    second.update(fixture_id=2000002, home_team=first["home_team"].lower())
    run = manifest("collation-collision", at, [first, second])
    store.extraction_state([2026], run["run_id"], at)
    store.load_team_batches(run, [team_batch()], at)
    with pytest.raises(ValueError, match="date/team unique key"):
        store.load_match_batch(run, etl.match_rows(run["matches"], at), at)
    connection.commit()
    cursor.execute("SELECT COUNT(*) AS total FROM live_matches")
    assert cursor.fetchone()["total"] == 380


def test_current_metadata_does_not_overwrite_historical_canonical_rows(mysql_database):
    connection, cursor = mysql_database
    migration.apply(connection, cursor)
    at = datetime(2026, 11, 2, 6)
    run = manifest("new-metadata", at, [match()])
    batch = team_batch()
    batch["teams"][0]["stadium"] = "Updated stadium description"
    batch["venues"][0]["venue_name"] = "Updated venue name"
    store.extraction_state([2026], run["run_id"], at)
    store.load_team_batches(run, [batch], at)
    connection.commit()
    store.assert_historical_snapshot(cursor, ROOT)
    cursor.execute("SELECT team_data FROM season_teams WHERE season=2026 AND api_team_id=%s", (batch["teams"][0]["api_team_id"],))
    assert json.loads(cursor.fetchone()["team_data"])["stadium"] == "Updated stadium description"


def test_complete_five_stage_pipeline_with_mock_api_and_real_mysql(mysql_database, monkeypatch, tmp_path):
    connection, cursor = mysql_database
    migration.apply(connection, cursor)
    record = match()
    source_fixture = {
        "fixture": {"id": record["fixture_id"], "date": record["match_date"],
                    "status": {"short": "FT", "long": "Test status", "elapsed": None}},
        "league": {"id": 39, "season": 2026},
        "teams": {"home": {"id": 33, "name": "Manchester United"}, "away": {"id": 34, "name": "Newcastle"}},
        "goals": {"home": 2, "away": 1},
    }
    batch = team_batch()
    venues = {row["venue_id"]: row for row in batch["venues"]}
    source_teams = []
    for row in batch["teams"]:
        venue = venues[row["venue_id"]]
        source_teams.append({
            "team": {"id": row["api_team_id"], "name": row["team_name"], "code": row["team_code"],
                     "country": row["country"], "founded": row["founded"], "national": False, "logo": row["logo_url"]},
            "venue": {"id": venue["venue_id"], "name": venue["venue_name"], "address": venue["address"],
                      "city": venue["city"], "capacity": venue["capacity"], "surface": venue["surface"], "image": venue["image_url"]},
        })
    calls = []
    def request(endpoint, params):
        calls.append((endpoint, params))
        return [source_fixture] if endpoint == "fixtures" else source_teams
    monkeypatch.setattr(etl, "request_api", request)
    config = {"seasons": [2026], "league": 39, "run_id": "end-to-end-mocked-api",
              "path": tmp_path / "run.json", "overlap_days": 14, "reconcile_days": 28}
    for stage in etl.STAGES:
        etl.execute_stage(stage, config)
    assert etl.read_manifest(config)["stage"] == "validate_data_quality"
    for stage in etl.STAGES:
        etl.execute_stage(stage, config)
    assert len(calls) == 2
    connection.commit()
    cursor.execute("SELECT COUNT(*) AS total FROM live_matches")
    assert cursor.fetchone()["total"] == 381
    store.assert_historical_snapshot(cursor, ROOT)
