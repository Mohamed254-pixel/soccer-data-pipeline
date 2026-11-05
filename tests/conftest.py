"""Offline test fixtures: never read local secrets or use real services."""

from unittest.mock import Mock

import dotenv
import pandas as pd
import pytest
import requests
import mysql.connector


# Extraction modules call load_dotenv on import. Disable it before collection.
dotenv.load_dotenv = lambda *args, **kwargs: False


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    for name in (
        "API_KEY", "DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME", "DB_PORT",
        "FOOTBALL_LEAGUE_ID", "FOOTBALL_SEASON",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(requests, "get", Mock(side_effect=AssertionError("Unmocked HTTP request")))
    monkeypatch.setattr(mysql.connector, "connect", Mock(side_effect=AssertionError("Unmocked DB connection")))


@pytest.fixture
def match_payload():
    return {"errors": [], "response": [{
        "fixture": {"id": 1208021, "date": "2024-08-16T20:00:00+01:00"},
        "teams": {"home": {"name": " Manchester United "}, "away": {"name": "Fulham"}},
        "goals": {"home": 1, "away": 0},
    }]}


@pytest.fixture
def match_df(match_payload):
    from api_matches import parse_matches
    return parse_matches(match_payload)


@pytest.fixture
def team_payload():
    return {"errors": [], "response": [{
        "team": {"id": 33, "name": "Manchester United", "code": "MUN",
                 "country": "England", "founded": 1878, "national": False},
        "venue": {"id": 556, "name": "Old Trafford", "capacity": 76212},
    }]}


@pytest.fixture
def team_frames(team_payload):
    from api_teams import parse_teams_and_venues
    return parse_teams_and_venues(team_payload)


@pytest.fixture
def database():
    connection = Mock()
    cursor = connection.cursor.return_value
    return connection, cursor
