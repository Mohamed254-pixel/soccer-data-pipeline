from pathlib import Path

import pandas as pd

from db import get_connection

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "data" / "results.csv"

UPSERT_SQL = """
    INSERT INTO results
        (match_date, home_team, away_team, home_score, away_score,
         tournament, city, country, id)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        match_date = VALUES(match_date),
        home_team = VALUES(home_team),
        away_team = VALUES(away_team),
        home_score = VALUES(home_score),
        away_score = VALUES(away_score),
        tournament = VALUES(tournament),
        city = VALUES(city),
        country = VALUES(country)
"""


def optional_text(value):
    return None if pd.isna(value) else str(value).strip()


def prepare_rows(df):
    required = {
        "date",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "tournament",
        "city",
        "country",
        "id",
    }
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Missing CSV columns: {', '.join(missing)}")

    cleaned = df.copy()
    cleaned["date"] = pd.to_datetime(cleaned["date"], errors="coerce")
    for column in ("home_score", "away_score", "id"):
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    cleaned["home_team"] = cleaned["home_team"].astype("string").str.strip()
    cleaned["away_team"] = cleaned["away_team"].astype("string").str.strip()
    cleaned = cleaned.dropna(
        subset=[
            "date",
            "home_team",
            "away_team",
            "home_score",
            "away_score",
            "id",
        ]
    )
    cleaned = cleaned[
        cleaned["home_team"].ne("") & cleaned["away_team"].ne("")
    ]

    rows = []
    for row in cleaned.itertuples(index=False):
        rows.append(
            (
                row.date.date(),
                row.home_team,
                row.away_team,
                int(row.home_score),
                int(row.away_score),
                optional_text(row.tournament),
                optional_text(row.city),
                optional_text(row.country),
                int(row.id),
            )
        )
    return rows


def main():
    rows = prepare_rows(pd.read_csv(INPUT_PATH))
    if not rows:
        raise RuntimeError(f"No valid historical results found in {INPUT_PATH}.")

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.executemany(UPSERT_SQL, rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    print(f"Loaded or updated {len(rows)} historical results.")


if __name__ == "__main__":
    main()
