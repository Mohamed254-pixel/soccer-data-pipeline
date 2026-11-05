"""Explicit, guarded Phase 2 migrations. Default invocation is a read-only preflight.

Use an administrator connection, never automatic ETL DDL. MySQL DDL implicitly
commits, so partial up migrations are resumed by checking named steps. Down is
permitted only before ingestion, when the database is still the exact archive.
"""

import argparse
import os
from pathlib import Path
import re

from dotenv import load_dotenv
import mysql.connector

from db import get_connection
from season_store import assert_historical_snapshot


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "sql/migrations"
METADATA_COLUMNS = {"season", "status_short", "status_long", "elapsed", "home_api_team_id",
                    "away_api_team_id", "source_observed_at"}


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
    if present:
        cursor.execute("SELECT COUNT(*) AS total FROM live_matches WHERE season IS NOT NULL AND season<>2024")
        future = cursor.fetchone()["total"]
        # Fully applied migrations are safe no-ops, but are not safe down targets.
        assert_historical_snapshot(cursor, ROOT, metadata=bool(future))
        return True, future
    assert_historical_snapshot(cursor, ROOT, metadata=False)
    return False, 0


def apply(connection, cursor):
    upgraded, future = preflight(cursor)
    if upgraded:
        cursor.execute("SELECT enabled FROM pipeline_control WHERE control_id=1")
        row = cursor.fetchone()
        if row and row["enabled"]:
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
    upgraded, future = preflight(cursor)
    if not upgraded:
        print("Match schema is already at Phase 1; no changes made.")
        return
    cursor.execute("SELECT * FROM pipeline_control WHERE control_id=1 FOR UPDATE")
    control = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) AS total FROM season_sync_state")
    states = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) AS total FROM season_teams WHERE season<>2024")
    memberships = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) AS total FROM teams")
    teams = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) AS total FROM venues")
    venues = cursor.fetchone()["total"]
    if future or states or memberships or teams != 20 or venues != 20 or (control and control["pending_run_id"]):
        raise ValueError("Rollback refused: incremental data or a pending run exists. Retain the additive schema and pause the DAG.")
    cursor.execute("UPDATE pipeline_control SET enabled=FALSE WHERE control_id=1")
    connection.commit()
    for statement in statements(MIGRATIONS / "003_incremental_etl.down.sql"):
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
