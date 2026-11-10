"""Shared MySQL connection configuration."""

import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv


def get_connection():
    """Create a MySQL connection using values from the local .env file."""
    load_dotenv(os.getenv("PIPELINE_ENV_FILE", Path(__file__).resolve().parents[1] / ".env"))

    required = ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"Missing database configuration: {names}. "
            "Copy .env.example to .env and add your local values."
        )

    try:
        port = int(os.getenv("DB_PORT", "3306"))
    except ValueError as exc:
        raise RuntimeError("DB_PORT must be a number.") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("DB_PORT must be between 1 and 65535.")

    tls = {}
    mode = os.getenv("DB_SSL_MODE", "PREFERRED")
    if mode not in {"PREFERRED", "VERIFY_IDENTITY"}:
        raise RuntimeError("DB_SSL_MODE must be PREFERRED or VERIFY_IDENTITY.")
    if mode == "VERIFY_IDENTITY":
        ca = os.getenv("DB_SSL_CA")
        if not ca or not Path(ca).is_file():
            raise RuntimeError("DB_SSL_CA must name an existing trusted CA bundle.")
        tls = {"ssl_ca": ca, "ssl_verify_cert": True, "ssl_verify_identity": True,
               "ssl_disabled": False, "tls_versions": ["TLSv1.2", "TLSv1.3"]}
    elif os.getenv("DB_SSL_CA"):
        raise RuntimeError("Set DB_SSL_MODE=VERIFY_IDENTITY when supplying DB_SSL_CA.")

    return mysql.connector.connect(
        host=os.environ["DB_HOST"],
        port=port,
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        connection_timeout=15,
        read_timeout=60,
        write_timeout=60,
        **tls,
    )
