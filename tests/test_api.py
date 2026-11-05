from copy import deepcopy
from unittest.mock import Mock

import pandas as pd
import pytest
import requests

import api_matches
import api_teams


ENDPOINTS = [
    (api_matches, "fetch_matches", "parse_matches"),
    (api_teams, "fetch_teams_and_venues", "parse_teams_and_venues"),
]


@pytest.mark.parametrize("module,fetch,parse", ENDPOINTS)
def test_missing_api_key(module, fetch, parse):
    with pytest.raises(RuntimeError, match="API_KEY"):
        getattr(module, fetch)()


@pytest.mark.parametrize("module,fetch,parse", ENDPOINTS)
@pytest.mark.parametrize("payload", [None, [], {}, {"response": None}, {"response": []}, {"errors": ["quota"]}])
def test_invalid_api_payload(module, fetch, parse, payload):
    with pytest.raises(RuntimeError):
        getattr(module, parse)(payload)


@pytest.mark.parametrize("module,fetch,parse", ENDPOINTS)
@pytest.mark.parametrize("failure", ["json", "http", "timeout"])
def test_request_failures(module, fetch, parse, failure, monkeypatch):
    monkeypatch.setenv("API_KEY", "test-only-key")
    response = Mock()
    get = Mock(return_value=response)
    if failure == "json":
        response.json.side_effect = ValueError("invalid JSON")
        expected = RuntimeError
    elif failure == "http":
        response.raise_for_status.side_effect = requests.HTTPError("HTTP 429")
        expected = requests.HTTPError
    else:
        get.side_effect = requests.Timeout("timeout")
        expected = requests.Timeout
    monkeypatch.setattr(module.requests, "get", get)
    with pytest.raises(expected):
        getattr(module, fetch)()


@pytest.mark.parametrize("module,fetch,parse", ENDPOINTS)
def test_request_configuration(module, fetch, parse, match_payload, team_payload, monkeypatch):
    monkeypatch.setenv("API_KEY", "test-only-key")
    response = Mock()
    response.json.return_value = match_payload if module is api_matches else team_payload
    get = Mock(return_value=response)
    monkeypatch.setattr(module.requests, "get", get)
    result = getattr(module, fetch)()
    assert result is not None
    get.assert_called_once_with(module.API_URL, headers={"x-apisports-key": "test-only-key"},
                                params={"league": 39, "season": 2024}, timeout=30)
    response.raise_for_status.assert_called_once()


def test_match_response_parsing(match_df):
    assert match_df.iloc[0].to_dict() == {
        "fixture_id": 1208021, "date": "2024-08-16T20:00:00+01:00",
        "home_team": " Manchester United ", "away_team": "Fulham",
        "home_goals": 1, "away_goals": 0,
    }


@pytest.mark.parametrize("fixture", [None, {}, {"fixture": None}])
def test_incomplete_fixture(fixture):
    with pytest.raises(RuntimeError, match="required fields"):
        api_matches.parse_matches({"response": [fixture]})


def test_duplicate_api_fixtures(match_payload):
    match_payload["response"] *= 2
    with pytest.raises(ValueError, match="duplicate fixture"):
        api_matches.parse_matches(match_payload)


def test_team_and_venue_parsing(team_frames):
    teams, venues = team_frames
    assert teams.iloc[0]["api_team_id"] == 33
    assert teams.iloc[0]["venue_id"] == venues.iloc[0]["venue_id"] == 556
    assert teams.iloc[0]["is_national"] == 0
    assert teams.iloc[0]["league"] == "Premier League"


def test_shared_venue_is_deduplicated(team_payload):
    second = deepcopy(team_payload["response"][0])
    second["team"].update(id=34, name="Another Club")
    team_payload["response"].append(second)
    teams, venues = api_teams.parse_teams_and_venues(team_payload)
    assert len(teams) == 2
    assert len(venues) == 1


def test_absent_venue_keeps_csv_columns(team_payload):
    team_payload["response"][0]["venue"] = None
    teams, venues = api_teams.parse_teams_and_venues(team_payload)
    assert pd.isna(teams.iloc[0]["venue_id"])
    assert venues.empty
    assert "venue_id" in venues.columns


@pytest.mark.parametrize("entry", [None, {}, {"team": []}, {"team": "invalid"},
                                     {"team": {"id": 33}},
                                     {"team": {"id": 33, "name": "Club", "national": "false"}}])
def test_invalid_team_entry(entry):
    with pytest.raises(RuntimeError):
        api_teams.parse_teams_and_venues({"response": [entry]})


def test_extraction_failure_preserves_staged_files(tmp_path, monkeypatch):
    output = tmp_path / "matches.csv"
    output.write_text("existing dataset\n")
    monkeypatch.setattr(api_matches, "OUTPUT_PATH", output)
    monkeypatch.setattr(api_matches, "fetch_matches", Mock(side_effect=RuntimeError("API failure")))
    with pytest.raises(RuntimeError):
        api_matches.main()
    assert output.read_text() == "existing dataset\n"
