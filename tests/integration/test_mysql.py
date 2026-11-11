"""Opt-in real MySQL verification in fresh randomly named test databases.

No application .env or API credentials are used. CI provides MySQL 8.0. Local
execution can use a separate --skip-networking instance via an explicit socket.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import runpy
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
def mysql_database(monkeypatch, request):
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
    if getattr(request, "param", None) != "empty":
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


def test_migration_reapply_detects_missing_foreign_key(mysql_database):
    connection, cursor = mysql_database
    migration.apply(connection, cursor)
    cursor.execute("ALTER TABLE live_matches DROP FOREIGN KEY fk_fixture_home_season")
    connection.commit()
    with pytest.raises(ValueError, match="schema"):
        migration.apply(connection, cursor)


def test_rollback_finishes_after_interruption_following_metadata_drop(mysql_database):
    connection, cursor = mysql_database
    migration.apply(connection, cursor)
    cursor.execute("UPDATE pipeline_control SET enabled=FALSE WHERE control_id=1")
    connection.commit()
    first = next(migration.statements(migration.MIGRATIONS / "003_incremental_etl.down.sql"))
    cursor.execute(first)
    connection.commit()
    migration.rollback(connection, cursor)
    cursor.execute("SHOW TABLES")
    assert {next(iter(row.values())) for row in cursor.fetchall()} == {"live_matches", "teams", "venues"}
    store.assert_historical_snapshot(cursor, ROOT, metadata=False)


def test_migration_refuses_wrong_metadata_type(mysql_database):
    connection, cursor = mysql_database
    migration.apply(connection, cursor)
    cursor.execute("ALTER TABLE live_matches MODIFY elapsed INT UNSIGNED NULL")
    connection.commit()
    with pytest.raises(ValueError, match="schema column/type"):
        migration.apply(connection, cursor)


def test_migration_refuses_missing_control_primary_key(mysql_database):
    connection, cursor = mysql_database
    migration.apply(connection, cursor)
    cursor.execute("ALTER TABLE pipeline_control DROP PRIMARY KEY")
    connection.commit()
    with pytest.raises(ValueError, match="primary-key"):
        migration.apply(connection, cursor)


def test_migrations_are_mutually_exclusive(mysql_database):
    connection, cursor = mysql_database
    other = store.get_connection()
    other_cursor = other.cursor(dictionary=True)
    try:
        with migration.migration_lock(cursor):
            with pytest.raises(ValueError, match="schema lock"):
                migration.apply(other, other_cursor)
    finally:
        other_cursor.close()
        other.close()
    assert "season" not in migration.column_names(cursor)


def test_extraction_retry_without_manifest_keeps_one_observation_time(mysql_database):
    connection, cursor = mysql_database
    migration.apply(connection, cursor)
    started = datetime(2026, 11, 2, 6)
    _, _, first = store.extraction_state([2026], "same-extraction", started)
    _, _, retry = store.extraction_state([2026], "same-extraction", started + timedelta(minutes=5))
    assert first == retry == started


def test_readiness_is_read_only_before_and_after_migration(mysql_database, monkeypatch):
    import check_readiness
    connection, cursor = mysql_database
    monkeypatch.setattr(check_readiness, "get_connection", store.get_connection)
    before = check_readiness.check_database()
    assert before["archive_matches"] and not before["migration_003_applied"]
    migration.apply(connection, cursor)
    after = check_readiness.check_database()
    assert after["archive_matches"] and after["pipeline_enabled"]
    assert before["counts"] == after["counts"]
    connection.commit()
    cursor.execute("SELECT pending_run_id FROM pipeline_control WHERE control_id=1")
    assert cursor.fetchone()["pending_run_id"] is None
    cursor.execute("SELECT COUNT(*) AS total FROM season_sync_state")
    assert cursor.fetchone()["total"] == 0


# Provider follow-up: these use the same isolated, random test databases only.
def football_data_match(status='FINISHED', goals=(2,1), source_id=1208021):
    return {'id':source_id,'competition':{'id':2021,'code':'PL'},
            'season':{'startDate':'2026-08-21'},'utcDate':None if status=='POSTPONED' else '2026-11-01T16:30:00Z',
            'status':status,'homeTeam':{'id':33,'name':'Manchester United'},'awayTeam':{'id':34,'name':'Newcastle'},
            'score':{'duration':'REGULAR','fullTime':{'home':goals[0],'away':goals[1]}}}


def football_data_teams():
    teams=[{'id':i,'name':f'Source club {i}','venue':'Source ground'} for i in range(33,53)]
    teams[0]['name']='Manchester United'  # Same natural name and raw ID as historical API-FOOTBALL.
    teams[1]['name']='Newcastle'
    return {'competition':{'code':'PL'},'season':{'startDate':'2026-08-21'},'count':20,'teams':teams}


def football_data_matches(values):
    return {'competition':{'code':'PL'},'resultSet':{'count':len(values)},'matches':values}


def test_source_migration_up_down_reapply_preserves_archive(mysql_database):
    import migrate_sources
    connection,cursor=mysql_database
    migration.apply(connection,cursor)
    migrate_sources.apply(connection,cursor)
    migrate_sources.apply(connection,cursor)
    cursor.execute('SELECT COUNT(*) AS total FROM fixture_source_ids')
    assert cursor.fetchone()['total']==380
    with pytest.raises(ValueError,match='004 first'):
        migration.rollback(connection,cursor)
    migrate_sources.rollback(connection,cursor)
    assert 'source_registry_state' not in migration.tables_present(cursor)
    store.assert_historical_snapshot(cursor,ROOT)
    migrate_sources.apply(connection,cursor)
    store.assert_historical_snapshot(cursor,ROOT)


def test_football_data_five_stages_corrections_retries_and_id_collisions(mysql_database,monkeypatch,tmp_path):
    import football_data as fd
    import migrate_sources
    from unittest.mock import Mock
    connection,cursor=mysql_database
    migration.apply(connection,cursor)
    migrate_sources.apply(connection,cursor)
    response=Mock(side_effect=[football_data_matches([football_data_match('POSTPONED',(None,None))]),football_data_teams(),
                               football_data_matches([football_data_match()]),football_data_teams()])
    monkeypatch.setattr(fd.Client,'request',response)
    config={'provider':'football_data','seasons':[2026],'league':39,'run_id':'fd-first','path':tmp_path/'first.json',
            'overlap_days':14,'reconcile_days':28}
    for stage in etl.STAGES:etl.execute_stage(stage,config)
    for stage in etl.STAGES:etl.execute_stage(stage,config)  # Frozen completed-run retries perform no HTTP/SQL reload.
    assert response.call_count==2
    config.update(run_id='fd-correction',path=tmp_path/'correction.json')
    for stage in etl.STAGES:etl.execute_stage(stage,config)
    assert not etl.read_manifest(config)['plans']['2026']['full']
    connection.commit()
    cursor.execute('SELECT COUNT(*) AS total,COUNT(DISTINCT fixture_id) AS ids FROM live_matches')
    assert cursor.fetchone()=={'total':381,'ids':381}
    cursor.execute('SELECT home_goals,status_short FROM live_matches WHERE fixture_id=%s',(2**63+1208021,))
    assert cursor.fetchone()=={'home_goals':2,'status_short':'FT'}
    cursor.execute("SELECT source_id,canonical_id FROM fixture_source_ids WHERE provider='football_data'")
    assert cursor.fetchone()=={'source_id':1208021,'canonical_id':2**63+1208021}
    cursor.execute("SELECT COUNT(*) AS total FROM teams WHERE team_name='Manchester United'")
    assert cursor.fetchone()['total']==2
    cursor.execute('SELECT COUNT(*) AS total FROM venues')
    assert cursor.fetchone()['total']==20
    store.assert_historical_snapshot(cursor,ROOT)
    with pytest.raises(ValueError,match='bindings/data'):
        migrate_sources.rollback(connection,cursor)
    with pytest.raises(ValueError,match='another provider'):
        store.extraction_state([2026],'wrong-provider',datetime.now(timezone.utc).replace(tzinfo=None),provider='api_football')


def test_source_migration_partial_up_resumes_and_drift_is_rejected(mysql_database):
    import migrate_sources
    connection,cursor=mysql_database
    migration.apply(connection,cursor)
    for statement in migration.statements(migration.MIGRATIONS/'004_source_registry.up.sql'):
        cursor.execute(statement)
        connection.commit()
        if '-- step: teams' in statement:break
    migrate_sources.apply(connection,cursor)
    cursor.execute('ALTER TABLE team_source_ids DROP CHECK chk_team_namespace')
    connection.commit()
    with pytest.raises(ValueError,match='constraint'):
        migrate_sources.apply(connection,cursor)


def test_source_constraints_block_bad_namespace_and_cross_season_mapping(mysql_database):
    import migrate_sources
    connection,cursor=mysql_database
    migration.apply(connection,cursor)
    migrate_sources.apply(connection,cursor)
    cursor.execute('SELECT fixture_id FROM live_matches LIMIT 1')
    fixture_id=cursor.fetchone()['fixture_id']
    with pytest.raises(mysql.connector.Error):
        cursor.execute("INSERT INTO team_source_ids VALUES ('football_data',100,100)")
    with pytest.raises(mysql.connector.Error):
        cursor.execute("UPDATE fixture_source_ids SET season=2026 WHERE canonical_id=%s",(fixture_id,))
    connection.rollback()
    store.assert_historical_snapshot(cursor,ROOT)


def test_fd_requires_004_and_invalid_source_leaves_no_owner_or_checkpoint(mysql_database,monkeypatch,tmp_path):
    import migrate_sources
    import football_data as fd
    from unittest.mock import Mock
    connection,cursor=mysql_database
    migration.apply(connection,cursor)
    with pytest.raises(RuntimeError,match='004'):
        store.extraction_state([2026],'no-registry',datetime.now(),provider='football_data')
    connection.commit()
    cursor.execute('SELECT pending_run_id FROM pipeline_control WHERE control_id=1')
    assert cursor.fetchone()['pending_run_id'] is None
    migrate_sources.apply(connection,cursor)
    bad=football_data_match();bad['season']['startDate']='2025-08-01'
    monkeypatch.setattr(fd.Client,'request',Mock(return_value=football_data_matches([bad])))
    config={'provider':'football_data','seasons':[2026],'league':39,'run_id':'invalid-fd','path':tmp_path/'bad.json',
            'overlap_days':14,'reconcile_days':28}
    with pytest.raises(ValueError):etl.execute_stage('extract_matches',config)
    assert not config['path'].exists()
    connection.commit()
    cursor.execute('SELECT COUNT(*) AS total FROM live_matches')
    assert cursor.fetchone()['total']==380
    cursor.execute('SELECT COUNT(*) AS total FROM season_sync_state')
    assert cursor.fetchone()['total']==0
    store.assert_historical_snapshot(cursor,ROOT)


def test_api_football_still_loads_with_source_registry(mysql_database):
    import migrate_sources
    connection,cursor=mysql_database
    migration.apply(connection,cursor)
    migrate_sources.apply(connection,cursor)
    at=datetime(2026,11,2,6)
    run=manifest('api-after-004',at,[match()])
    complete_run(run,at)
    connection.commit()
    cursor.execute("SELECT source_id,canonical_id FROM fixture_source_ids WHERE season=2026")
    assert cursor.fetchone()=={'source_id':2000001,'canonical_id':2000001}
    with pytest.raises(ValueError,match='another provider'):
        store.extraction_state([2026],'fd-switch',at+timedelta(days=7),provider='football_data')
    store.assert_historical_snapshot(cursor,ROOT)


def test_football_data_multiple_seasons_with_independent_checkpoints(mysql_database,monkeypatch,tmp_path):
    import migrate_sources
    import football_data as fd
    from unittest.mock import Mock
    connection,cursor=mysql_database
    migration.apply(connection,cursor)
    migrate_sources.apply(connection,cursor)
    older=football_data_match(source_id=1208020);older['season']['startDate']='2025-08-01';older['utcDate']='2025-11-01T16:30:00Z'
    older_teams=football_data_teams();older_teams['season']['startDate']='2025-08-01'
    monkeypatch.setattr(fd.Client,'request',Mock(side_effect=[football_data_matches([older]),football_data_matches([football_data_match()]),older_teams,football_data_teams()]))
    config={'provider':'football_data','seasons':[2025,2026],'league':39,'run_id':'fd-multiple','path':tmp_path/'multi.json',
            'overlap_days':14,'reconcile_days':28}
    for stage in etl.STAGES:etl.execute_stage(stage,config)
    connection.commit()
    cursor.execute('SELECT season FROM season_sync_state ORDER BY season')
    assert [r['season'] for r in cursor.fetchall()]==[2025,2026]
    cursor.execute('SELECT COUNT(*) AS total FROM live_matches')
    assert cursor.fetchone()['total']==382
    store.assert_historical_snapshot(cursor,ROOT)


def test_source_migration_rejects_nonunique_identity_index(mysql_database):
    import migrate_sources
    connection,cursor=mysql_database
    migration.apply(connection,cursor)
    migrate_sources.apply(connection,cursor)
    cursor.execute('ALTER TABLE teams DROP INDEX uq_team_name_league, ADD INDEX uq_team_name_league (team_name,league,source_provider)')
    connection.commit()
    with pytest.raises(ValueError,match='unique identity'):
        migrate_sources.apply(connection,cursor)


def test_source_rollback_resumes_after_partial_table_cleanup(mysql_database):
    import migrate_sources
    connection,cursor=mysql_database
    migration.apply(connection,cursor)
    migrate_sources.apply(connection,cursor)
    cursor.execute('UPDATE source_registry_state SET ready=FALSE WHERE control_id=1')
    connection.commit()
    cursor.execute('DROP TABLE fixture_source_ids')
    connection.commit()
    migrate_sources.rollback(connection,cursor)
    assert not (migrate_sources.TABLES & migration.tables_present(cursor))
    store.assert_historical_snapshot(cursor,ROOT)


def test_readonly_readiness_validates_source_registry_and_bindings(mysql_database,monkeypatch):
    import migrate_sources
    import check_readiness
    connection,cursor=mysql_database
    migration.apply(connection,cursor)
    migrate_sources.apply(connection,cursor)
    monkeypatch.setattr(check_readiness,'get_connection',store.get_connection)
    result=check_readiness.check_database()
    assert result['archive_matches'] and result['source_registry_ready']
    assert result['season_sources']=={'2024':'api_football'}
    assert result['counts']['live_matches']=={'total':380,'unique_ids':380}


def test_registry_reapply_rejects_weakened_check_with_same_name(mysql_database):
    import migrate_sources
    connection,cursor=mysql_database
    migration.apply(connection,cursor)
    migrate_sources.apply(connection,cursor)
    cursor.execute('ALTER TABLE team_source_ids DROP CHECK chk_team_namespace, ADD CONSTRAINT chk_team_namespace CHECK (source_id>0 AND source_id<2147483648 AND 2147483648=2147483648)')
    connection.commit()
    with pytest.raises(ValueError,match='CHECK constraint expression'):
        migrate_sources.apply(connection,cursor)


@pytest.mark.parametrize("mysql_database", ["empty"], indirect=True)
def test_aws_demo_bootstrap_seeds_and_validates_archive(mysql_database, monkeypatch):
    import db
    import load_live_matches
    import load_teams
    import migrate_sources

    connection, cursor = mysql_database
    # The fixture's socket/host and random schema are the only test endpoints.
    def connect():
        return store.get_connection()

    for module in (db, load_live_matches, load_teams):
        monkeypatch.setattr(module, "get_connection", connect)
    monkeypatch.setattr(load_teams, "TEAMS_PATH", load_teams.TEAMS_PATH)
    monkeypatch.setattr(load_teams, "VENUES_PATH", load_teams.VENUES_PATH)
    monkeypatch.setattr(load_live_matches, "INPUT_PATH", load_live_matches.INPUT_PATH)
    bootstrap = runpy.run_path(str(ROOT / "deploy/aws/demo/bootstrap.py"))
    bootstrap["seed"](ROOT / "sql/schema.sql", ROOT / "data")
    store.assert_historical_snapshot(cursor, ROOT)
    migrate_sources.verify_registry(cursor)
    cursor.execute("SELECT COUNT(*) AS total FROM live_matches WHERE season=2024")
    assert cursor.fetchone()["total"] == 380
    with pytest.raises(RuntimeError, match="Expected an empty demo database"):
        bootstrap["seed"](ROOT / "sql/schema.sql", ROOT / "data")
