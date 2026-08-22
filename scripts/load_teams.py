from pathlib import Path

import pandas as pd

from db import get_connection

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEAMS_PATH = PROJECT_ROOT / "data" / "teams.csv"
VENUES_PATH = PROJECT_ROOT / "data" / "venues.csv"

VENUE_UPSERT_SQL = """
    INSERT INTO venues (
        venue_id,
        venue_name,
        address,
        city,
        capacity,
        surface,
        image_url
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        venue_name = VALUES(venue_name),
        address = VALUES(address),
        city = VALUES(city),
        capacity = VALUES(capacity),
        surface = VALUES(surface),
        image_url = VALUES(image_url)
"""

TEAM_UPSERT_SQL = """
    INSERT INTO teams (
        api_team_id,
        team_name,
        team_code,
        country,
        league,
        stadium,
        founded,
        is_national,
        logo_url,
        venue_id
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        api_team_id = VALUES(api_team_id),
        team_name = VALUES(team_name),
        team_code = VALUES(team_code),
        country = VALUES(country),
        league = VALUES(league),
        stadium = VALUES(stadium),
        founded = VALUES(founded),
        is_national = VALUES(is_national),
        logo_url = VALUES(logo_url),
        venue_id = VALUES(venue_id)
"""


def clean_text(value):
    if pd.isna(value):
        return None

    value = str(value).strip()
    return value or None


def clean_int(value):
    if pd.isna(value):
        return None

    return int(value)


def require_columns(df, required, file_name):
    missing = sorted(required.difference(df.columns))

    if missing:
        raise ValueError(
            f"{file_name} is missing columns: {', '.join(missing)}"
        )


def prepare_venue_rows(df):
    required = {
        "venue_id",
        "venue_name",
        "address",
        "city",
        "capacity",
        "surface",
        "image_url",
    }
    require_columns(df, required, "venues.csv")

    rows = []

    for record in df.to_dict(orient="records"):
        venue_id = clean_int(record["venue_id"])
        venue_name = clean_text(record["venue_name"])

        if venue_id is None or venue_name is None:
            raise ValueError("Every venue requires an ID and name.")

        rows.append(
            (
                venue_id,
                venue_name,
                clean_text(record["address"]),
                clean_text(record["city"]),
                clean_int(record["capacity"]),
                clean_text(record["surface"]),
                clean_text(record["image_url"]),
            )
        )

    if len(rows) != len({row[0] for row in rows}):
        raise ValueError("venues.csv contains duplicate venue IDs.")

    return rows


def prepare_team_rows(df):
    required = {
        "api_team_id",
        "team_name",
        "team_code",
        "country",
        "league",
        "stadium",
        "founded",
        "is_national",
        "logo_url",
        "venue_id",
    }
    require_columns(df, required, "teams.csv")

    rows = []

    for record in df.to_dict(orient="records"):
        api_team_id = clean_int(record["api_team_id"])
        team_name = clean_text(record["team_name"])
        league = clean_text(record["league"])
        is_national = clean_int(record["is_national"])

        if api_team_id is None or team_name is None or league is None:
            raise ValueError(
                "Every team requires an API ID, name, and league."
            )

        if is_national not in (0, 1):
            raise ValueError(
                f"Invalid is_national value for {team_name}."
            )

        rows.append(
            (
                api_team_id,
                team_name,
                clean_text(record["team_code"]),
                clean_text(record["country"]),
                league,
                clean_text(record["stadium"]),
                clean_int(record["founded"]),
                is_national,
                clean_text(record["logo_url"]),
                clean_int(record["venue_id"]),
            )
        )

    if len(rows) != len({row[0] for row in rows}):
        raise ValueError("teams.csv contains duplicate API team IDs.")

    return rows


def main():
    venues = prepare_venue_rows(pd.read_csv(VENUES_PATH))
    teams = prepare_team_rows(pd.read_csv(TEAMS_PATH))

    venue_ids = {row[0] for row in venues}
    team_venue_ids = {row[9] for row in teams if row[9] is not None}
    missing_venue_ids = team_venue_ids - venue_ids

    if missing_venue_ids:
        raise ValueError(
            f"Teams reference missing venues: {sorted(missing_venue_ids)}"
        )

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.executemany(VENUE_UPSERT_SQL, venues)
        cursor.executemany(TEAM_UPSERT_SQL, teams)
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()

    print(f"Loaded or updated {len(venues)} venues.")
    print(f"Loaded or updated {len(teams)} Premier League teams.")


if __name__ == "__main__":
    main()