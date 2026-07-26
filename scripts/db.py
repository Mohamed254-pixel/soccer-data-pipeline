"""Shared MySQL connection configuration."""

import os

import mysql.connector
from dotenv import load_dotenv


def get_connection():
    """Create a MySQL connection using values from the local .env file."""
    load_dotenv()

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

    return mysql.connector.connect(
        host=os.environ["DB_HOST"],
        port=port,
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
    )
