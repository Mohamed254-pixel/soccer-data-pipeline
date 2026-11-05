from unittest.mock import Mock

import pytest

import db


def test_missing_database_configuration():
    with pytest.raises(RuntimeError, match="Missing database configuration"):
        db.get_connection()


@pytest.mark.parametrize("port", ["3306", "3307", "invalid"])
def test_connection_configuration(monkeypatch, port):
    for key, value in {"DB_HOST": "localhost", "DB_USER": "test-user", "DB_PASSWORD": "test-only-password",
                       "DB_NAME": "test-db", "DB_PORT": port}.items():
        monkeypatch.setenv(key, value)
    connect = Mock()
    monkeypatch.setattr(db.mysql.connector, "connect", connect)
    if port == "invalid":
        with pytest.raises(RuntimeError, match="DB_PORT must be a number"):
            db.get_connection()
        connect.assert_not_called()
    else:
        db.get_connection()
        connect.assert_called_once_with(host="localhost", port=int(port), user="test-user",
                                        password="test-only-password", database="test-db",
                                        connection_timeout=15, read_timeout=60, write_timeout=60)


@pytest.mark.parametrize("port", ["0", "-1", "65536"])
def test_invalid_port_range_never_connects(monkeypatch, port):
    for key in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME"):
        monkeypatch.setenv(key, "test-only")
    monkeypatch.setenv("DB_PORT", port)
    connect = Mock()
    monkeypatch.setattr(db.mysql.connector, "connect", connect)
    with pytest.raises(RuntimeError, match="between 1 and 65535"):
        db.get_connection()
    connect.assert_not_called()
