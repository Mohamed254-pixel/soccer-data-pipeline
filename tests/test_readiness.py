import base64
import json
from unittest.mock import Mock

import pytest
import requests

import check_readiness as readiness
import incremental as etl


@pytest.mark.parametrize("healthy", [True, False])
def test_service_readiness_requires_all_seven_healthy_services(monkeypatch, tmp_path, healthy):
    names = ["postgres", "redis", "airflow-apiserver", "airflow-scheduler", "airflow-dag-processor",
             "airflow-worker", "airflow-triggerer"]
    rows = [{"Service": name, "State": "running", "Health": "healthy"} for name in names]
    if not healthy:
        rows[-1]["Health"] = "unhealthy"
    run = Mock(return_value=Mock(returncode=0, stdout="\n".join(json.dumps(row) for row in rows)))
    monkeypatch.setattr(readiness.subprocess, "run", run)
    assert readiness.check_services(tmp_path / "private.env")["all_healthy"] is healthy
    assert run.call_args.args[0][-4:] == ["ps", "--all", "--format", "json"]
    assert "ps" in run.call_args.args[0]
    assert "up" not in run.call_args.args[0]


def test_secret_check_rejects_empty_and_documented_defaults():
    assert readiness.check_secrets({}) == {"jwt_secret_ready": False, "fernet_key_ready": False}
    assert not readiness.check_secrets({"AIRFLOW__API_AUTH__JWT_SECRET": "airflow_jwt_secret"})["jwt_secret_ready"]
    result = readiness.check_secrets({"AIRFLOW__API_AUTH__JWT_SECRET": "test-only-random-shape-" * 3,
                                     "FERNET_KEY": base64.urlsafe_b64encode(b"0" * 32).decode()})
    assert result == {"jwt_secret_ready": True, "fernet_key_ready": True}


def api_response(status=200, payload=None, retry_after=None):
    response = Mock(status_code=status)
    response.headers = {} if retry_after is None else {"Retry-After": retry_after}
    response.json.return_value = payload or {"errors": [], "response": []}
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
    return response


@pytest.mark.parametrize("failure", [requests.Timeout(), requests.ConnectionError(), api_response(503)])
def test_transient_api_failures_retry_then_succeed(monkeypatch, failure):
    monkeypatch.setenv("API_KEY", "test-only-key")
    get = Mock(side_effect=[failure, api_response()])
    sleep = Mock()
    monkeypatch.setattr(etl.requests, "get", get)
    monkeypatch.setattr(etl, "sleep", sleep)
    assert etl.request_api("fixtures", {}) == []
    assert get.call_count == 2
    sleep.assert_called_once_with(1)


def test_rate_limit_respects_retry_after(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-only-key")
    get = Mock(side_effect=[api_response(429, retry_after="5"), api_response()])
    sleep = Mock()
    monkeypatch.setattr(etl.requests, "get", get)
    monkeypatch.setattr(etl, "sleep", sleep)
    assert etl.request_api("fixtures", {}) == []
    sleep.assert_called_once_with(5)


@pytest.mark.parametrize("status,wait", [(401, None), (403, None), (429, "120")])
def test_permanent_or_long_wait_errors_are_left_for_operator_or_task_retry(monkeypatch, status, wait):
    monkeypatch.setenv("API_KEY", "test-only-key")
    get = Mock(return_value=api_response(status, retry_after=wait))
    sleep = Mock()
    monkeypatch.setattr(etl.requests, "get", get)
    monkeypatch.setattr(etl, "sleep", sleep)
    with pytest.raises(requests.HTTPError):
        etl.request_api("fixtures", {})
    get.assert_called_once()
    sleep.assert_not_called()


def test_transport_retry_is_bounded(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-only-key")
    get = Mock(side_effect=requests.Timeout())
    sleep = Mock()
    monkeypatch.setattr(etl.requests, "get", get)
    monkeypatch.setattr(etl, "sleep", sleep)
    with pytest.raises(requests.Timeout):
        etl.request_api("fixtures", {})
    assert get.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]


def test_api_error_does_not_echo_account_secrets_or_retry(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-only-key")
    get = Mock(return_value=api_response(payload={"errors": {"plan": "sensitive-provider-text"}, "response": []}))
    monkeypatch.setattr(etl.requests, "get", get)
    with pytest.raises(etl.APIResponseError) as exc:
        etl.request_api("fixtures", {})
    assert exc.value.category == "plan_or_season_access"
    assert "sensitive-provider-text" not in str(exc.value)
    get.assert_called_once()


def test_invalid_date_does_not_echo_untrusted_input():
    with pytest.raises(ValueError) as exc:
        etl.utc_datetime("sensitive-untrusted-input")
    assert "sensitive-untrusted-input" not in str(exc.value)


def test_api_readiness_keeps_partial_subscription_evidence_without_exposing_response(monkeypatch):
    monkeypatch.setattr(etl, "request_payload", Mock(return_value={"response": {
        "subscription": {"active": True}, "requests": {"current": 10, "limit_day": 100}}}))
    get = Mock(side_effect=etl.APIResponseError("plan_or_season_access"))
    monkeypatch.setattr(etl, "request_api", get)
    with pytest.raises(etl.APIResponseError) as exc:
        readiness.check_api([2026])
    assert exc.value.readiness_details == {"subscription_active": True, "quota_remaining_before_probes": 90, "verified_seasons": []}


def test_readiness_does_not_probe_seasons_when_quota_is_low(monkeypatch):
    monkeypatch.setattr(etl, "request_payload", Mock(return_value={"response": {
        "subscription": {"active": True}, "requests": {"current": 99, "limit_day": 100}}}))
    get = Mock()
    monkeypatch.setattr(etl, "request_api", get)
    with pytest.raises(RuntimeError, match="quota"):
        readiness.check_api([2026])
    get.assert_not_called()


def test_successful_readiness_probe_never_claims_or_loads_a_run(monkeypatch):
    monkeypatch.setattr(etl, "request_payload", Mock(return_value={"response": {
        "subscription": {"active": True}, "requests": {"current": 0, "limit_day": 100}}}))
    sample = {"fixture": {"id": 2000001, "date": "2026-11-01T16:30:00Z",
                          "status": {"short": "NS", "long": "Not Started", "elapsed": None}},
              "league": {"id": 39, "season": 2026},
              "teams": {"home": {"id": 33, "name": "Manchester United"}, "away": {"id": 34, "name": "Newcastle"}},
              "goals": {"home": None, "away": None}}
    monkeypatch.setattr(etl, "request_api", Mock(side_effect=[
        [{"league": {"id": 39}, "seasons": [{"year": 2026}]}], [sample]]))
    claim = Mock(side_effect=AssertionError("Readiness must not claim a run"))
    load = Mock(side_effect=AssertionError("Readiness must not load a batch"))
    monkeypatch.setattr(etl.store, "extraction_state", claim)
    monkeypatch.setattr(etl.store, "load_match_batch", load)
    assert readiness.check_api([2026])["verified_seasons"] == [2026]
    claim.assert_not_called()
    load.assert_not_called()
