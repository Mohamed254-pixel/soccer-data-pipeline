import pytest

import validate_data_quality as quality


SUCCESS = [380, 20, 20, 0, 0, 0, 0, 0, 0]


def test_quality_checks_pass(monkeypatch, database, capsys):
    connection, cursor = database
    cursor.fetchone.side_effect = [(value,) for value in SUCCESS]
    monkeypatch.setattr(quality, "get_connection", lambda: connection)
    quality.main()
    assert capsys.readouterr().out.count("PASS |") == 9
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


@pytest.mark.parametrize("failed_check", range(9))
def test_each_quality_failure_propagates(monkeypatch, database, failed_check):
    connection, cursor = database
    counts = SUCCESS.copy()
    counts[failed_check] += 1
    cursor.fetchone.side_effect = [(value,) for value in counts]
    monkeypatch.setattr(quality, "get_connection", lambda: connection)
    with pytest.raises(RuntimeError, match="Data quality checks failed"):
        quality.main()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_quality_query_failure_closes_connection(monkeypatch, database):
    connection, cursor = database
    cursor.execute.side_effect = RuntimeError("query failed")
    monkeypatch.setattr(quality, "get_connection", lambda: connection)
    with pytest.raises(RuntimeError, match="query failed"):
        quality.main()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_cursor_creation_failure_closes_connection(monkeypatch, database):
    connection, _ = database
    connection.cursor.side_effect = RuntimeError("cursor failed")
    monkeypatch.setattr(quality, "get_connection", lambda: connection)
    with pytest.raises(RuntimeError, match="cursor failed"):
        quality.main()
    connection.close.assert_called_once()
