"""Explicit, guarded Phase 2 migrations. Default invocation is a read-only preflight.

Use an administrator connection, never automatic ETL DDL. MySQL DDL implicitly
commits, so partial up migrations are resumed by checking named steps. Down is
permitted only before ingestion, when the database is still the exact archive.
"""

import argparse
from contextlib import contextmanager, suppress
import os
from pathlib import Path
import re

from dotenv import load_dotenv
import mysql.connector
import pandas as pd

from db import get_connection
from season_store import assert_historical_snapshot, historical_match_rows


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "sql/migrations"
METADATA_COLUMNS = {"season", "status_short", "status_long", "elapsed", "home_api_team_id",
                    "away_api_team_id", "source_observed_at"}
SUPPORT_COLUMNS = {
    "season_teams": {"season": "smallint unsigned", "api_team_id": "int unsigned",
                     "team_name": "varchar(100)", "venue_id": "int unsigned", "team_data": "json", "venue_data": "json"},
    "season_sync_state": {"season": "smallint unsigned", "last_success_at": "datetime(6)", "last_full_sync_at": "datetime(6)"},
    "pipeline_control": {"control_id": "tinyint unsigned", "enabled": "tinyint", "pending_run_id": "varchar(250)",
                         "pending_started_at": "datetime(6)", "pending_lease_until": "datetime(6)",
                         "last_completed_at": "datetime(6)", "last_completed_run_id": "varchar(250)"},
}


def tables_present(cursor):
    cursor.execute("SHOW TABLES")
    return {next(iter(row.values())) for row in cursor.fetchall()}


def validate_schema(cursor, metadata=False, complete=False):
    """Reject drift rather than treating column names as proof of migration."""
    tables = tables_present(cursor)
    if complete and not set(SUPPORT_COLUMNS).issubset(tables):
        raise ValueError("Phase 2 schema is missing supporting tables.")
    specs = {table: spec for table, spec in SUPPORT_COLUMNS.items() if table in tables}
    if metadata:
        specs["live_matches"] = {"season": "smallint unsigned", "status_short": "varchar(5)",
                                 "status_long": "varchar(100)", "elapsed": "smallint unsigned",
                                 "home_api_team_id": "int unsigned", "away_api_team_id": "int unsigned",
                                 "source_observed_at": "datetime(6)", "match_date": "datetime(6)"}
    for table, expected in specs.items():
        cursor.execute(f"SHOW COLUMNS FROM {table}")
        actual = {row["Field"]: re.sub(r"\b(tinyint|smallint|int|bigint)\(\d+\)", r"\1", row["Type"].lower())
                  for row in cursor.fetchall()}
        if any(actual.get(name) != kind for name, kind in expected.items()):
            raise ValueError(f"Phase 2 schema column/type mismatch in {table}.")
        if table != "live_matches" and set(actual) != set(expected):
            raise ValueError(f"Unexpected Phase 2 schema columns in {table}.")
    primary_keys = {"season_teams": ["season", "api_team_id"], "season_sync_state": ["season"],
                    "pipeline_control": ["control_id"]}
    for table in set(primary_keys) & tables:
        cursor.execute(f"SHOW INDEX FROM {table} WHERE Key_name='PRIMARY'")
        columns = [row["Column_name"] for row in sorted(cursor.fetchall(), key=lambda row: row["Seq_in_index"])]
        if columns != primary_keys[table]:
            raise ValueError(f"Phase 2 schema primary-key mismatch in {table}.")
    cursor.execute("SELECT TABLE_NAME,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()")
    engines = {row["TABLE_NAME"]: row["ENGINE"] for row in cursor.fetchall()}
    if any(engines.get(table) != "InnoDB" for table in {"live_matches", "teams", "venues", *specs}):
        raise ValueError("Pipeline schema requires InnoDB transaction support.")
    expected_keys = {
        "fk_season_team": [("season_teams", "api_team_id", "teams", "api_team_id")],
        "fk_season_venue": [("season_teams", "venue_id", "venues", "venue_id")],
    } if "season_teams" in tables else {}
    if metadata:
        expected_keys.update({
            "fk_fixture_home_season": [("live_matches", "season", "season_teams", "season"),
                                       ("live_matches", "home_api_team_id", "season_teams", "api_team_id")],
            "fk_fixture_away_season": [("live_matches", "season", "season_teams", "season"),
                                       ("live_matches", "away_api_team_id", "season_teams", "api_team_id")],
        })
    cursor.execute("""SELECT CONSTRAINT_NAME,TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME
                      FROM information_schema.KEY_COLUMN_USAGE
                      WHERE CONSTRAINT_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL
                      ORDER BY CONSTRAINT_NAME,ORDINAL_POSITION""")
    keys = {}
    for row in cursor.fetchall():
        keys.setdefault(row["CONSTRAINT_NAME"], []).append(tuple(row[key] for key in
            ("TABLE_NAME", "COLUMN_NAME", "REFERENCED_TABLE_NAME", "REFERENCED_COLUMN_NAME")))
    if any(keys.get(name) != columns for name, columns in expected_keys.items()):
        raise ValueError("Phase 2 schema foreign-key mismatch.")
    if metadata:
        cursor.execute("SHOW INDEX FROM live_matches WHERE Key_name='idx_fixture_season_status_date'")
        columns = [row["Column_name"] for row in sorted(cursor.fetchall(), key=lambda row: row["Seq_in_index"])]
        if columns != ["season", "status_short", "match_date"]:
            raise ValueError("Phase 2 schema season/status/date index mismatch.")


@contextmanager
def migration_lock(cursor):
    cursor.execute("SELECT GET_LOCK(CONCAT('pl_migration_003:',LEFT(SHA2(DATABASE(),256),32)),0) AS acquired")
    if cursor.fetchone()["acquired"] != 1:
        raise ValueError("Another migration process holds the schema lock.")
    try:
        yield
    finally:
        with suppress(mysql.connector.Error):
            cursor.execute("SELECT RELEASE_LOCK(CONCAT('pl_migration_003:',LEFT(SHA2(DATABASE(),256),32))) AS released")
            cursor.fetchone()


def column_names(cursor):
    cursor.execute("SHOW COLUMNS FROM live_matches")
    return {row["Field"] for row in cursor.fetchall()}


def statements(path):
    """The migration files contain plain SQL, no procedures/delimiter changes."""
    for statement in path.read_text().split(";"):
        if re.sub(r"--[^\n]*", "", statement).strip():
            yield statement


def preflight(cursor):
    columns = column_names(cursor)
    present = METADATA_COLUMNS & columns
    if present and present != METADATA_COLUMNS:
        raise ValueError("Unexpected partial match metadata. Inspect the schema before proceeding.")
    validate_schema(cursor, metadata=bool(present))
    if present:
        cursor.execute("SELECT COUNT(*) AS total FROM live_matches WHERE season IS NOT NULL AND season<>2024")
        future = cursor.fetchone()["total"]
        # Fully applied migrations are safe no-ops, but are not safe down targets.
        assert_historical_snapshot(cursor, ROOT, metadata=bool(future))
        return True, future
    assert_historical_snapshot(cursor, ROOT, metadata=False)
    return False, 0


def apply(connection, cursor):
    with migration_lock(cursor):
        _apply(connection, cursor)


def _apply(connection, cursor):
    upgraded, future = preflight(cursor)
    if upgraded:
        cursor.execute("SELECT enabled FROM pipeline_control WHERE control_id=1")
        row = cursor.fetchone()
        if row and row["enabled"]:
            validate_schema(cursor, metadata=True, complete=True)
            assert_historical_snapshot(cursor, ROOT)
            print("Migration 003 is already applied; no changes made.")
            return
        if future:
            raise ValueError("Unexpected nonhistorical data in an incomplete migration.")
    for table in ("teams", "venues"):
        cursor.execute(f"SELECT COUNT(*) AS total FROM {table}")
        if cursor.fetchone()["total"] != 20:
            raise ValueError("Initial migration requires the verified 2024-only database.")
    for statement in statements(MIGRATIONS / "003_incremental_etl.up.sql"):
        if "-- step: metadata" in statement and upgraded:
            continue
        if "-- step: historical_metadata" in statement:
            snapshot = Path(os.getenv("HISTORICAL_DATA_DIR", ROOT / "data"))
            ids = [row[0] for row in historical_match_rows(pd.read_csv(snapshot / "live_matches.csv"))]
            statement = statement.replace("__ARCHIVE_FIXTURE_IDS__", ",".join(["%s"] * len(ids)))
            cursor.execute(statement, tuple(ids))
        else:
            if "-- step: enable" in statement:
                validate_schema(cursor, metadata=True, complete=True)
                assert_historical_snapshot(cursor, ROOT, metadata=False)
            cursor.execute(statement)
        # Verify the backfill before allowing the ETL to run.
        if "-- step: historical_metadata" in statement:
            cursor.execute("SELECT COUNT(*) AS total FROM live_matches WHERE season=2024 AND home_api_team_id IS NOT NULL AND away_api_team_id IS NOT NULL")
            if cursor.fetchone()["total"] != 380:
                raise ValueError("Historical metadata backfill was incomplete.")
            assert_historical_snapshot(cursor, ROOT)
        connection.commit()
    assert_historical_snapshot(cursor, ROOT)
    print("Migration 003 applied. All original snapshot values preserved.")


def rollback(connection, cursor):
    with migration_lock(cursor):
        _rollback(connection, cursor)


def _rollback(connection, cursor):
    if "source_registry_state" in tables_present(cursor):
        raise ValueError("Rollback source migration 004 first; do not remove metadata referenced by source mappings.")
    upgraded, future = preflight(cursor)
    tables = tables_present(cursor)
    if not upgraded and not set(SUPPORT_COLUMNS).intersection(tables):
        print("Match schema is already at Phase 1; no changes made.")
        return
    control = None
    if "pipeline_control" in tables:
        cursor.execute("SELECT * FROM pipeline_control WHERE control_id=1 FOR UPDATE")
        control = cursor.fetchone()
    states = memberships = 0
    if "season_sync_state" in tables:
        cursor.execute("SELECT COUNT(*) AS total FROM season_sync_state")
        states = cursor.fetchone()["total"]
    if "season_teams" in tables:
        cursor.execute("SELECT COUNT(*) AS total FROM season_teams WHERE season<>2024")
        memberships = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) AS total FROM teams")
    teams = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) AS total FROM venues")
    venues = cursor.fetchone()["total"]
    if future or states or memberships or teams != 20 or venues != 20 or (control and control["pending_run_id"]):
        raise ValueError("Rollback refused: incremental data or a pending run exists. Retain the additive schema and pause the DAG.")
    if "pipeline_control" in tables:
        cursor.execute("UPDATE pipeline_control SET enabled=FALSE WHERE control_id=1")
    connection.commit()
    for statement in statements(MIGRATIONS / "003_incremental_etl.down.sql"):
        if "ALTER TABLE live_matches" in statement and not upgraded:
            continue
        drop = re.search(r"DROP TABLE (\w+)", statement)
        if drop and drop.group(1) not in tables:
            continue
        cursor.execute(statement)
        connection.commit()
    assert_historical_snapshot(cursor, ROOT, metadata=False)
    print("Migration 003 rolled back. All original snapshot values preserved.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    load_dotenv(os.getenv("PIPELINE_ENV_FILE", ROOT / ".env"))
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        if args.apply:
            apply(connection, cursor)
        elif args.rollback:
            rollback(connection, cursor)
        else:
            upgraded, future = preflight(cursor)
            print(f"Preflight passed. Phase 2 metadata present={upgraded}; nonhistorical fixtures={future}. No changes made.")
    except Exception:
        connection.rollback()
        raise
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            connection.close()


if __name__ == "__main__":
    try:
        main()
    except mysql.connector.Error as exc:
        raise SystemExit(f"Migration database operation failed ({type(exc).__name__}, errno={exc.errno}).") from None
