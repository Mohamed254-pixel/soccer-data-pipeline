"""Validate the final Premier League data stored in MySQL."""

from db import get_connection


EXPECTED_MATCHES = 380
EXPECTED_TEAMS = 20
EXPECTED_VENUES = 20


def get_count(cursor, query):
    """Run a count query and return the result as an integer."""
    cursor.execute(query)
    return int(cursor.fetchone()[0])


def main():
    connection = get_connection()
    cursor = connection.cursor()

    try:
        checks = [
            (
                "match row count",
                get_count(
                    cursor,
                    "SELECT COUNT(*) FROM live_matches",
                ),
                EXPECTED_MATCHES,
            ),
            (
                "team row count",
                get_count(
                    cursor,
                    "SELECT COUNT(*) FROM teams",
                ),
                EXPECTED_TEAMS,
            ),
            (
                "venue row count",
                get_count(
                    cursor,
                    "SELECT COUNT(*) FROM venues",
                ),
                EXPECTED_VENUES,
            ),
            (
                "duplicate fixture IDs",
                get_count(
                    cursor,
                    """
                    SELECT COUNT(*) - COUNT(DISTINCT fixture_id)
                    FROM live_matches
                    """,
                ),
                0,
            ),
            (
                "missing fixture IDs",
                get_count(
                    cursor,
                    """
                    SELECT COUNT(*)
                    FROM live_matches
                    WHERE fixture_id IS NULL
                    """,
                ),
                0,
            ),
            (
                "missing team API IDs",
                get_count(
                    cursor,
                    """
                    SELECT COUNT(*)
                    FROM teams
                    WHERE api_team_id IS NULL
                    """,
                ),
                0,
            ),
            (
                "missing match scores",
                get_count(
                    cursor,
                    """
                    SELECT COUNT(*)
                    FROM live_matches
                    WHERE home_goals IS NULL
                       OR away_goals IS NULL
                    """,
                ),
                0,
            ),
            (
                "negative match scores",
                get_count(
                    cursor,
                    """
                    SELECT COUNT(*)
                    FROM live_matches
                    WHERE home_goals < 0
                       OR away_goals < 0
                    """,
                ),
                0,
            ),
            (
                "broken team-to-venue relationships",
                get_count(
                    cursor,
                    """
                    SELECT COUNT(*)
                    FROM teams AS t
                    LEFT JOIN venues AS v
                        ON t.venue_id = v.venue_id
                    WHERE t.venue_id IS NOT NULL
                      AND v.venue_id IS NULL
                    """,
                ),
                0,
            ),
        ]

        failures = []

        for name, actual, expected in checks:
            if actual == expected:
                print(
                    f"PASS | {name} | "
                    f"actual={actual} | expected={expected}"
                )
            else:
                print(
                    f"FAIL | {name} | "
                    f"actual={actual} | expected={expected}"
                )
                failures.append(
                    f"{name}: expected {expected}, received {actual}"
                )

        if failures:
            details = "; ".join(failures)
            raise RuntimeError(
                f"Data quality checks failed: {details}"
            )

        print("All data quality checks passed.")

    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()