from datetime import datetime
from unittest.mock import Mock

import pandas as pd
import pytest

import load_live_matches as matches
import load_teams as teams


def test_match_upsert_preparation(match_df):
    assert matches.prepare_rows(match_df) == [
        (1208021, datetime(2024, 8, 16, 19), "Manchester United", "Fulham", 1, 0)
    ]


@pytest.mark.parametrize("column", ["fixture_id", "date", "home_team", "away_team", "home_goals", "away_goals"])
def test_missing_match_columns(match_df, column):
    with pytest.raises(ValueError, match="Missing CSV columns"):
        matches.prepare_rows(match_df.drop(columns=column))


@pytest.mark.parametrize("column,value", [
    ("fixture_id", None), ("fixture_id", "bad"), ("fixture_id", -1), ("fixture_id", 1.5),
    ("date", "not-a-date"), ("date", None), ("home_team", "  "), ("away_team", None),
    ("home_goals", -1), ("away_goals", -2), ("home_goals", 1.5),
    ("away_goals", "bad"), ("home_goals", float("inf")), ("away_goals", 65536),
])
def test_invalid_match_values(match_df, column, value):
    match_df[column] = value
    with pytest.raises(ValueError):
        matches.prepare_rows(match_df)


def test_duplicate_fixture_ids(match_df):
    with pytest.raises(ValueError, match="duplicate fixture"):
        matches.prepare_rows(pd.concat([match_df, match_df]))


def test_empty_matches(match_df):
    with pytest.raises(ValueError, match="empty"):
        matches.prepare_rows(match_df.iloc[:0])


def test_nullable_scores_preserve_schema_support(match_df):
    match_df["home_goals"] = None
    assert matches.prepare_rows(match_df)[0][4] is None


def test_team_and_venue_upsert_preparation(team_frames):
    team_df, venue_df = team_frames
    venue_row = teams.prepare_venue_rows(venue_df)[0]
    team_row = teams.prepare_team_rows(team_df)[0]
    assert venue_row == (556, "Old Trafford", None, None, 76212, None, None)
    assert team_row == (33, "Manchester United", "MUN", "England", "Premier League",
                        "Old Trafford", 1878, 0, None, 556)


@pytest.mark.parametrize("frame_index,prepare", [(0, teams.prepare_team_rows), (1, teams.prepare_venue_rows)])
def test_missing_team_or_venue_columns(team_frames, frame_index, prepare):
    frame = team_frames[frame_index]
    for column in frame.columns:
        with pytest.raises(ValueError, match="missing columns"):
            prepare(frame.drop(columns=column))


@pytest.mark.parametrize("frame_index,prepare", [(0, teams.prepare_team_rows), (1, teams.prepare_venue_rows)])
def test_duplicate_team_or_venue_ids(team_frames, frame_index, prepare):
    frame = team_frames[frame_index]
    with pytest.raises(ValueError, match="duplicate"):
        prepare(pd.concat([frame, frame]))


@pytest.mark.parametrize("value", [-1, 1.5, "bad", float("inf")])
def test_invalid_team_integer(value):
    with pytest.raises(ValueError):
        teams.clean_int(value)


def mock_loader_inputs(monkeypatch, team_frames, match_df):
    team_df, venue_df = team_frames
    monkeypatch.setattr(pd, "read_csv", lambda path: {
        teams.TEAMS_PATH: team_df, teams.VENUES_PATH: venue_df, matches.INPUT_PATH: match_df,
    }[path])


def test_missing_venue_fails_before_database(monkeypatch, team_frames, match_df):
    team_frames[0]["venue_id"] = 999
    mock_loader_inputs(monkeypatch, team_frames, match_df)
    connect = Mock()
    monkeypatch.setattr(teams, "get_connection", connect)
    with pytest.raises(ValueError, match="missing venues"):
        teams.main()
    connect.assert_not_called()


@pytest.mark.parametrize("module", [matches, teams])
def test_loader_commits_upserts(module, monkeypatch, team_frames, match_df, database):
    mock_loader_inputs(monkeypatch, team_frames, match_df)
    connection, cursor = database
    cursor.fetchall.return_value = []
    monkeypatch.setattr(module, "get_connection", lambda: connection)
    module.main()
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    expected = [(matches.UPSERT_SQL, matches.prepare_rows(match_df))] if module is matches else [
        (teams.VENUE_UPSERT_SQL, teams.prepare_venue_rows(team_frames[1])),
        (teams.TEAM_UPSERT_SQL, teams.prepare_team_rows(team_frames[0])),
    ]
    assert [call.args for call in cursor.executemany.call_args_list] == expected
    for sql, rows in expected:
        assert "ON DUPLICATE KEY UPDATE" in sql
        assert sql.count("%s") == len(rows[0])
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("module,fail_on", [(matches, 1), (teams, 1), (teams, 2)])
def test_loader_rolls_back_and_propagates_failure(module, fail_on, monkeypatch, team_frames, match_df, database):
    mock_loader_inputs(monkeypatch, team_frames, match_df)
    connection, cursor = database
    cursor.fetchall.return_value = []
    cursor.executemany.side_effect = [None] * (fail_on - 1) + [RuntimeError("database unavailable")]
    monkeypatch.setattr(module, "get_connection", lambda: connection)
    with pytest.raises(RuntimeError, match="database unavailable"):
        module.main()
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("module", [matches, teams])
def test_cursor_creation_failure_closes_connection(module, monkeypatch, team_frames, match_df, database):
    mock_loader_inputs(monkeypatch, team_frames, match_df)
    connection, _ = database
    connection.cursor.side_effect = RuntimeError("cursor failed")
    monkeypatch.setattr(module, "get_connection", lambda: connection)
    with pytest.raises(RuntimeError, match="cursor failed"):
        module.main()
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()
