"""Initialize only the fresh demo schema from committed archive fixtures."""
import os
import sys
from pathlib import Path

import db
import load_live_matches
import load_teams
import migrate_phase2
import migrate_sources


def seed(schema, archive):
    with db.get_connection() as connection, connection.cursor(dictionary=True) as cursor:
        cursor.execute("SHOW TABLES")
        if cursor.fetchall():
            raise RuntimeError("Expected an empty demo database. Inspect a partial setup before retrying.")
        for statement in migrate_phase2.statements(schema):
            if not statement.strip().upper().startswith(("CREATE DATABASE", "USE ")):
                cursor.execute(statement)
    load_teams.TEAMS_PATH = archive / "teams.csv"
    load_teams.VENUES_PATH = archive / "venues.csv"
    load_live_matches.INPUT_PATH = archive / "live_matches.csv"
    load_teams.main()
    load_live_matches.main()
    with db.get_connection() as connection, connection.cursor(dictionary=True) as cursor:
        migrate_phase2.apply(connection, cursor)
        migrate_sources.apply(connection, cursor)


def main():
    if os.environ["DB_HOST"] != "mysql" or os.environ["DB_USER"] != "demo_bootstrap":
        raise ValueError("The bootstrap requires the isolated demo MySQL account.")
    os.environ["DB_PASSWORD"] = Path("/run/secrets/demo_bootstrap").read_text().strip()
    seed(Path("/opt/soccer/sql/schema.sql"), Path(os.environ["HISTORICAL_DATA_DIR"]))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.exit(f"Demo database setup stopped ({type(exc).__name__}); inspect the disposable database.")
