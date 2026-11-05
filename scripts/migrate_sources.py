"""Explicit migration 004. Default is read-only; never called by ETL."""
import argparse
import re

import mysql.connector

from db import get_connection
import migrate_phase2 as phase2
from season_store import assert_historical_snapshot

TABLES = {'source_registry_state', 'season_sources', 'team_source_ids', 'fixture_source_ids'}


def indexes(cursor, table):
    cursor.execute(f"SHOW INDEX FROM {table}")
    result = {}
    for row in sorted(cursor.fetchall(), key=lambda r: (r['Key_name'], r['Seq_in_index'])):
        result.setdefault(row['Key_name'], []).append(row['Column_name'])
    return result


def validate(cursor):
    if not TABLES <= phase2.tables_present(cursor):
        raise ValueError('Source registry tables are incomplete.')
    cursor.execute("SHOW COLUMNS FROM teams WHERE Field='source_provider'")
    provider_column = cursor.fetchone()
    if (not provider_column or provider_column['Type'] != "enum('api_football','football_data')"
            or provider_column['Null'] != 'NO'):
        raise ValueError('Team provider column mismatch.')
    expected = {
        'source_registry_state': {'control_id': 'tinyint unsigned', 'ready': 'tinyint'},
        'season_sources': {'season': 'smallint unsigned', 'provider': "enum('api_football','football_data')"},
        'team_source_ids': {'provider': "enum('api_football','football_data')", 'source_id': 'int unsigned', 'canonical_id': 'int unsigned'},
        'fixture_source_ids': {'provider': "enum('api_football','football_data')", 'source_id': 'bigint unsigned', 'canonical_id': 'bigint unsigned', 'season': 'smallint unsigned'},
    }
    for table, spec in expected.items():
        cursor.execute(f'SHOW COLUMNS FROM {table}')
        rows = cursor.fetchall()
        actual = {r['Field']: re.sub(r'\b(tinyint|smallint|int|bigint)\(\d+\)', r'\1', r['Type'].lower()) for r in rows}
        if actual != spec or any(r['Null'] != 'NO' for r in rows):
            raise ValueError('Source registry column/type/nullability mismatch.')
    for table, name, columns in [('teams','uq_team_name_league',['team_name','league','source_provider']),
                                  ('teams','uq_team_source',['api_team_id','source_provider']),
                                  ('live_matches','uq_fixture_id_season',['fixture_id','season']),
                                  ('team_source_ids','PRIMARY',['provider','source_id']),
                                  ('team_source_ids','uq_team_canonical',['canonical_id']),
                                  ('fixture_source_ids','PRIMARY',['provider','source_id']),
                                  ('fixture_source_ids','uq_fixture_canonical',['canonical_id']),
                                  ('season_sources','PRIMARY',['season']),
                                  ('season_sources','uq_season_source',['season','provider']),
                                  ('source_registry_state','PRIMARY',['control_id'])]:
        if indexes(cursor, table).get(name) != columns:
            raise ValueError('Source registry index mismatch.')
        cursor.execute(f"SHOW INDEX FROM {table} WHERE Key_name=%s", (name,))
        if any(row['Non_unique'] != 0 for row in cursor.fetchall()):
            raise ValueError('Source registry requires unique identity indexes.')
    cursor.execute("SELECT TABLE_NAME,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()")
    engines = {r['TABLE_NAME']:r['ENGINE'] for r in cursor.fetchall()}
    if any(engines.get(t) != 'InnoDB' for t in TABLES):
        raise ValueError('Source registry requires InnoDB.')
    # Verify actual referenced columns and enforced CHECK clauses, not just names.
    clauses = {
        'team_source_ids': ["FOREIGN KEY (`canonical_id`,`provider`) REFERENCES `teams` (`api_team_id`,`source_provider`)",
                           'source_id', '2147483648', 'chk_team_namespace'],
        'fixture_source_ids': ["FOREIGN KEY (`canonical_id`,`season`) REFERENCES `live_matches` (`fixture_id`,`season`)",
                              "FOREIGN KEY (`season`,`provider`) REFERENCES `season_sources` (`season`,`provider`)",
                              '9223372036854775808', 'chk_fixture_namespace'],
        'season_sources': ['chk_archive_source', '2024'],
    }
    for table, parts in clauses.items():
        cursor.execute(f'SHOW CREATE TABLE {table}')
        ddl = cursor.fetchone()['Create Table'].replace(' ', '').lower()
        if any(part.replace(' ', '').lower() not in ddl for part in parts) or 'notenforced' in ddl:
            raise ValueError('Source registry constraint mismatch.')


def preflight(cursor):
    upgraded, _ = phase2.preflight(cursor)
    if not upgraded:
        raise ValueError('Apply reviewed migration 003 before migration 004.')
    phase2.validate_schema(cursor, metadata=True, complete=True)
    assert_historical_snapshot(cursor, phase2.ROOT)
    cursor.execute('SELECT pending_run_id FROM pipeline_control WHERE control_id=1')
    row = cursor.fetchone()
    if not row or row['pending_run_id']:
        raise ValueError('Stop/resume pending ETL before migration 004.')
    present = phase2.tables_present(cursor)
    if 'source_registry_state' in present:
        cursor.execute('SELECT ready FROM source_registry_state WHERE control_id=1')
        state = cursor.fetchone()
        if state and state['ready']:
            validate(cursor)
            return True
    # Initial/resume target cannot contain unmapped upper-namespace data.
    cursor.execute('SELECT COUNT(*) AS total FROM teams WHERE api_team_id IS NULL OR api_team_id>=2147483648')
    if cursor.fetchone()['total']:
        raise ValueError('Existing team IDs conflict with the reserved namespace.')
    cursor.execute('SELECT COUNT(*) AS total FROM live_matches WHERE fixture_id>=9223372036854775808 OR season IS NULL')
    if cursor.fetchone()['total']:
        raise ValueError('Existing fixtures conflict with source namespace/classification.')
    return False


def verify_registry(cursor):
    for table, mapping, key in [('teams','team_source_ids','api_team_id'), ('live_matches','fixture_source_ids','fixture_id')]:
        cursor.execute(f'SELECT COUNT(*) AS total FROM {table} t LEFT JOIN {mapping} m ON m.canonical_id=t.{key} WHERE m.canonical_id IS NULL')
        if cursor.fetchone()['total']:
            raise ValueError('Source registry backfill is incomplete.')


def apply(connection, cursor):
    with phase2.migration_lock(cursor):
        if preflight(cursor):
            verify_registry(cursor)
            print('Migration 004 already applied; no changes made.')
            return
        for statement in phase2.statements(phase2.MIGRATIONS / '004_source_registry.up.sql'):
            if '-- step: teams' in statement:
                cursor.execute('SHOW COLUMNS FROM teams')
                if 'source_provider' in {r['Field'] for r in cursor.fetchall()}:
                    continue
            if '-- step: fixtures' in statement and 'uq_fixture_id_season' in indexes(cursor,'live_matches'):
                continue
            cursor.execute(statement)
            connection.commit()
        validate(cursor)
        verify_registry(cursor)
        assert_historical_snapshot(cursor, phase2.ROOT)
        cursor.execute('UPDATE source_registry_state SET ready=TRUE WHERE control_id=1')
        connection.commit()
        print('Migration 004 applied; historical values and IDs preserved.')


def rollback(connection, cursor):
    with phase2.migration_lock(cursor):
        phase2.preflight(cursor)
        assert_historical_snapshot(cursor, phase2.ROOT)
        cursor.execute('SELECT pending_run_id FROM pipeline_control WHERE control_id=1')
        if cursor.fetchone()['pending_run_id']:
            raise ValueError('Rollback refused while an ETL run is pending.')
        tables = phase2.tables_present(cursor)
        for table, predicate in [('live_matches','fixture_id>=9223372036854775808'),
                                  ('teams','api_team_id>=2147483648'),('season_sources',"provider='football_data'")]:
            if table in tables:
                cursor.execute(f'SELECT COUNT(*) AS total FROM {table} WHERE {predicate}')
                if cursor.fetchone()['total']:
                    raise ValueError('Rollback refused: football-data bindings/data exist. Retain schema and records.')
        if 'source_registry_state' in tables:
            cursor.execute('UPDATE source_registry_state SET ready=FALSE WHERE control_id=1')
            connection.commit()
        for statement in phase2.statements(phase2.MIGRATIONS / '004_source_registry.down.sql'):
            drop = re.search(r'DROP TABLE (\w+)', statement)
            if drop and drop.group(1) not in tables:
                continue
            if 'ALTER TABLE live_matches' in statement and 'uq_fixture_id_season' not in indexes(cursor,'live_matches'):
                continue
            if 'ALTER TABLE teams' in statement:
                cursor.execute('SHOW COLUMNS FROM teams')
                if 'source_provider' not in {r['Field'] for r in cursor.fetchall()}:
                    continue
            cursor.execute(statement)
            connection.commit()
        assert_historical_snapshot(cursor, phase2.ROOT)
        print('Migration 004 rolled back; original data and migration 003 retained.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--apply', action='store_true')
    group.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        if args.apply:
            apply(connection,cursor)
        elif args.rollback:
            rollback(connection,cursor)
        else:
            ready = preflight(cursor)
            print(f'Migration 004 preflight passed; registry ready={ready}. No changes made.')
    finally:
        connection.rollback()
        cursor.close()
        connection.close()


if __name__ == '__main__':
    try:
        main()
    except (mysql.connector.Error, ValueError) as exc:
        raise SystemExit(f'Migration 004 stopped ({type(exc).__name__}); inspect preflight/schema safely.') from None
