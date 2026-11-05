from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
import requests

import incremental as etl
import season_store as store


NOW = datetime(2026, 11, 2, 6)


@pytest.fixture
def fixture_record():
    return {
        "fixture": {"id": 2000001, "date": "2026-11-01T16:30:00+00:00",
                    "status": {"short": "FT", "long": "Match Finished", "elapsed": 90}},
        "league": {"id": 39, "season": 2026},
        "teams": {"home": {"id": 33, "name": "Manchester United"},
                  "away": {"id": 34, "name": "Newcastle"}},
        "goals": {"home": 2, "away": 1},
    }


@pytest.fixture
def config(tmp_path):
    return {"seasons": [2026], "league": 39, "run_id": "test-run",
            "path": tmp_path / "batch.json", "overlap_days": 14, "reconcile_days": 28}


def test_active_season_defaults_to_2026(monkeypatch):
    monkeypatch.setenv("PIPELINE_RUN_ID", "test")
    monkeypatch.setenv("FOOTBALL_SEASON", "2024")
    assert etl.settings()["seasons"] == [2026]


@pytest.mark.parametrize("seasons,expected", [("2025,2026", [2025, 2026]), ("2026,2026", [2026])])
def test_multiple_seasons(monkeypatch, seasons, expected):
    monkeypatch.setenv("PIPELINE_RUN_ID", "test")
    monkeypatch.setenv("FOOTBALL_SEASONS", seasons)
    assert etl.settings()["seasons"] == expected


@pytest.mark.parametrize("name,value", [("FOOTBALL_SEASONS", "2024"), ("FOOTBALL_SEASONS", ""),
                                      ("FOOTBALL_SEASONS", "2026.5"), ("FOOTBALL_LEAGUE_ID", "1"),
                                      ("INCREMENTAL_OVERLAP_DAYS", "0"), ("FULL_RECONCILE_DAYS", "-1")])
def test_invalid_configuration(monkeypatch, name, value):
    monkeypatch.setenv("PIPELINE_RUN_ID", "test")
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        etl.settings()


def test_run_id_is_required():
    with pytest.raises(ValueError, match="PIPELINE_RUN_ID"):
        etl.settings()


@pytest.mark.parametrize("status", sorted(etl.STATUSES))
def test_all_supported_fixture_statuses(fixture_record, status):
    fixture_record["fixture"]["status"]["short"] = status
    if status not in etl.FINISHED:
        fixture_record["goals"] = {"home": None, "away": None}
    parsed = etl.parse_fixture(fixture_record, 2026)
    assert parsed["status_short"] == status
    assert parsed["season"] == 2026


@pytest.mark.parametrize("status", ["TBD", "PST"])
def test_unknown_kickoff_is_preserved_as_null(fixture_record, status):
    fixture_record["fixture"].update(date=None)
    fixture_record["fixture"]["status"]["short"] = status
    fixture_record["goals"] = {"home": None, "away": None}
    assert etl.parse_fixture(fixture_record, 2026)["match_date"] is None


@pytest.mark.parametrize("change", [
    lambda x: x["fixture"]["status"].update(short="UNKNOWN"),
    lambda x: x["fixture"].update(date=None),
    lambda x: x["fixture"].update(date="invalid"),
    lambda x: x["league"].update(season=2025),
    lambda x: x["league"].update(id=1),
    lambda x: x["goals"].update(home=-1),
    lambda x: x["goals"].update(home=1.5),
    lambda x: x["goals"].update(home=None),
    lambda x: x["teams"]["home"].update(id=34),
    lambda x: x["teams"]["home"].update(name=" "),
    lambda x: x["fixture"].update(id=True),
    lambda x: x["fixture"].update(id=None),
])
def test_invalid_fixture_rejected_before_loading(fixture_record, change):
    change(fixture_record)
    with pytest.raises(ValueError):
        etl.parse_fixture(fixture_record, 2026)


def test_bootstrap_and_reconciliation_use_only_requested_season():
    assert etl.plan_requests(2026, None, [], NOW)["requests"] == [{"league": 39, "season": 2026, "timezone": "UTC"}]
    state = {"last_success_at": NOW - timedelta(days=7), "last_full_sync_at": NOW - timedelta(days=29)}
    assert etl.plan_requests(2026, state, [], NOW)["full"] is True


def test_window_widens_after_missed_runs_and_batches_pending_ids():
    state = {"last_success_at": NOW - timedelta(days=21), "last_full_sync_at": NOW - timedelta(days=21)}
    pending = [{"fixture_id": n, "season": 2026} for n in range(1, 44)]
    pending.append({"fixture_id": 9999, "season": 2024})
    plan = etl.plan_requests(2026, state, pending, NOW)
    assert plan["full"] is False
    assert plan["requests"][0]["from"] == (NOW - timedelta(days=35)).date().isoformat()
    ids = [query["ids"].split("-") for query in plan["requests"][1:]]
    assert [len(batch) for batch in ids] == [20, 20, 3]
    assert "9999" not in sum(ids, [])


@pytest.mark.parametrize("payload", [None, [], {}, {"errors": ["private-value"], "response": []},
                                     {"response": [], "paging": {"current": 1, "total": 2}},
                                     {"response": [], "results": 1}])
def test_api_contract_errors_are_not_successful_empty_windows(monkeypatch, payload):
    monkeypatch.setenv("API_KEY", "test-only-key")
    response = Mock()
    response.json.return_value = payload
    monkeypatch.setattr(etl.requests, "get", Mock(return_value=response))
    with pytest.raises(RuntimeError):
        etl.request_api("fixtures", {})


@pytest.mark.parametrize("error", [requests.Timeout, requests.HTTPError, ValueError])
def test_api_transport_and_json_failure(monkeypatch, error):
    monkeypatch.setenv("API_KEY", "test-only-key")
    response = Mock()
    if error is ValueError:
        response.json.side_effect = error("invalid JSON")
        expected = RuntimeError
    else:
        response.raise_for_status.side_effect = error("unavailable")
        expected = error
    monkeypatch.setattr(etl.requests, "get", Mock(return_value=response))
    with pytest.raises(expected):
        etl.request_api("fixtures", {})


def test_empty_incremental_window_is_noop_but_empty_bootstrap_fails(monkeypatch, config):
    monkeypatch.setattr(etl, "request_api", Mock(return_value=[]))
    state = {"last_success_at": NOW - timedelta(days=7), "last_full_sync_at": NOW - timedelta(days=7)}
    batch = etl.extract_batch(config, {2026: state}, [], NOW)
    assert batch["matches"] == []
    with pytest.raises(ValueError, match="Empty bootstrap"):
        etl.extract_batch(config, {2026: None}, [], NOW)


def test_postponed_id_outside_window_gets_latest_result(monkeypatch, config, fixture_record):
    state = {"last_success_at": NOW - timedelta(days=7), "last_full_sync_at": NOW - timedelta(days=7)}
    old = deepcopy(fixture_record)
    old["fixture"]["status"]["short"] = "PST"
    old["goals"] = {"home": None, "away": None}
    get = Mock(side_effect=[[old], [fixture_record]])
    monkeypatch.setattr(etl, "request_api", get)
    batch = etl.extract_batch(config, {2026: state}, [{"fixture_id": 2000001, "season": 2026}], NOW)
    assert len(batch["matches"]) == 1
    assert batch["matches"][0]["status_short"] == "FT"
    assert get.call_args_list[1].args[1]["ids"] == "2000001"


def test_duplicate_ids_in_one_response_are_rejected(monkeypatch, config, fixture_record):
    monkeypatch.setattr(etl, "request_api", Mock(return_value=[fixture_record, fixture_record]))
    with pytest.raises(ValueError, match="Duplicate fixture"):
        etl.extract_batch(config, {2026: None}, [], NOW)


def test_missing_pending_id_is_failure(monkeypatch, config):
    state = {"last_success_at": NOW, "last_full_sync_at": NOW}
    monkeypatch.setattr(etl, "request_api", Mock(return_value=[]))
    with pytest.raises(ValueError, match="omitted"):
        etl.extract_batch(config, {2026: state}, [{"fixture_id": 99, "season": 2026}], NOW)


def test_multiple_season_batch_keeps_separate_identities(monkeypatch, config, fixture_record):
    config["seasons"] = [2025, 2026]
    older = deepcopy(fixture_record)
    older["league"]["season"] = 2025
    older["fixture"]["id"] = 1999999
    monkeypatch.setattr(etl, "request_api", Mock(side_effect=[[older], [fixture_record]]))
    batch = etl.extract_batch(config, {2025: None, 2026: None}, [], NOW)
    assert {row["season"] for row in batch["matches"]} == {2025, 2026}


def test_staging_is_atomic_and_rejects_other_run(monkeypatch, config, fixture_record):
    monkeypatch.setattr(etl, "request_api", Mock(return_value=[fixture_record]))
    batch = etl.extract_batch(config, {2026: None}, [], NOW)
    etl.save_manifest(config, batch)
    original = config["path"].read_bytes()
    with pytest.raises(ValueError):
        etl.save_manifest(config, {"invalid": float("nan")})
    assert config["path"].read_bytes() == original
    assert etl.read_manifest(config) == batch
    config["run_id"] = "different-run"
    with pytest.raises(ValueError, match="identity"):
        etl.read_manifest(config)


def test_invalid_api_does_not_publish_or_load(monkeypatch, config):
    monkeypatch.setattr(store, "extraction_state", Mock(return_value=({2026: None}, [])))
    monkeypatch.setattr(etl, "request_api", Mock(side_effect=RuntimeError("API failure")))
    load = Mock()
    monkeypatch.setattr(store, "load_match_batch", load)
    with pytest.raises(RuntimeError):
        etl.execute_stage("extract_matches", config)
    assert not config["path"].exists()
    load.assert_not_called()


def test_staging_retries_reuse_frozen_extraction(monkeypatch, config, fixture_record):
    monkeypatch.setattr(store, "extraction_state", Mock(return_value=({2026: None}, [])))
    get = Mock(return_value=[fixture_record])
    monkeypatch.setattr(etl, "request_api", get)
    etl.execute_stage("extract_matches", config)
    etl.execute_stage("extract_matches", config)
    assert get.call_count == 1


def test_row_preparation_preserves_season_status_and_nulls(fixture_record):
    fixture_record["fixture"].update(date=None)
    fixture_record["fixture"]["status"]["short"] = "TBD"
    fixture_record["goals"] = {"home": None, "away": None}
    parsed = etl.parse_fixture(fixture_record, 2026)
    row = etl.match_rows([parsed], NOW)[0]
    assert row[1] is None and row[4:6] == (None, None)
    assert row[6:8] == (2026, "TBD")
    assert row[-1] == NOW


@pytest.mark.parametrize("kind", ["cross_season", "historical", "stale", "unique_key"])
def test_upsert_identity_and_staleness_guards(fixture_record, kind):
    row = etl.match_rows([etl.parse_fixture(fixture_record, 2026)], NOW)[0]
    cursor = Mock()
    existing = {"season": 2026, "source_observed_at": NOW}
    if kind == "cross_season":
        existing["season"] = 2025
    elif kind == "historical":
        existing["season"] = 2024
    elif kind == "stale":
        existing["source_observed_at"] = NOW + timedelta(days=1)
    cursor.fetchone.side_effect = [existing, {"fixture_id": 123} if kind == "unique_key" else None]
    with pytest.raises(ValueError):
        store.upsert_matches(cursor, [row])
    cursor.executemany.assert_not_called()


@pytest.mark.parametrize("owner,completed", [("other-run", None), (None, NOW)])
def test_overlapping_or_stale_runs_are_blocked(owner, completed):
    cursor = Mock()
    cursor.fetchone.return_value = {"enabled": True, "pending_run_id": owner, "last_completed_at": completed}
    with pytest.raises(RuntimeError):
        store.lock_run(cursor, "this-run", NOW, claim=True)


def test_expired_owner_can_be_replaced_but_old_worker_is_fenced():
    cursor = Mock()
    cursor.fetchone.return_value = {"enabled": True, "pending_run_id": "abandoned",
                                    "pending_lease_until": datetime(2000, 1, 1), "last_completed_at": None}
    store.lock_run(cursor, "fresh-extraction", NOW, claim=True)
    assert cursor.execute.call_args.args[1][0] == "fresh-extraction"
    cursor.fetchone.return_value = {"enabled": True, "pending_run_id": "fresh-extraction",
                                    "pending_lease_until": datetime(2100, 1, 1), "last_completed_at": None}
    with pytest.raises(RuntimeError, match="Another pipeline run"):
        store.lock_run(cursor, "abandoned", NOW)


def test_completed_run_id_cannot_claim_a_different_batch():
    cursor = Mock()
    cursor.fetchone.return_value = {"enabled": True, "pending_run_id": None,
                                    "last_completed_run_id": "completed", "last_completed_at": NOW}
    with pytest.raises(RuntimeError, match="already completed"):
        store.lock_run(cursor, "completed", NOW + timedelta(days=1), claim=True)


def test_database_failure_rolls_back_and_closes(monkeypatch, database):
    connection, cursor = database
    monkeypatch.setattr(store, "get_connection", lambda: connection)
    with pytest.raises(ValueError):
        with store.database(write=True):
            raise ValueError("invalid batch")
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
    connection.close.assert_called_once()


def test_stage_failure_does_not_advance_staging(monkeypatch, config, fixture_record):
    monkeypatch.setattr(etl, "request_api", Mock(return_value=[fixture_record]))
    manifest = etl.extract_batch(config, {2026: None}, [], NOW)
    manifest["stage"] = "load_matches"
    etl.save_manifest(config, manifest)
    monkeypatch.setattr(store, "finish_run", Mock(side_effect=ValueError("quality failed")))
    with pytest.raises(ValueError, match="quality failed"):
        etl.execute_stage("validate_data_quality", config)
    assert etl.read_manifest(config)["stage"] == "load_matches"
