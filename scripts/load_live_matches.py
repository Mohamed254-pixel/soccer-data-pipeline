from pathlib import Path

import pandas as pd

from db import get_connection

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "data" / "live_matches.csv"

UPSERT_SQL = """
    INSERT INTO live_matches
        (match_date, home_team, away_team, home_goals, away_goals)
    VALUES (%s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        home_goals = VALUES(home_goals),
        away_goals = VALUES(away_goals)
"""


def prepare_rows(df):
    required = {
        "date",
        "home_team",
        "away_team",
        "home_goals",
        "away_goals",
    }
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Missing CSV columns: {', '.join(missing)}")

    cleaned = df.copy()
    cleaned["date"] = pd.to_datetime(cleaned["date"], errors="coerce", utc=True)
    cleaned["home_goals"] = pd.to_numeric(
        cleaned["home_goals"], errors="coerce"
    )
    cleaned["away_goals"] = pd.to_numeric(
        cleaned["away_goals"], errors="coerce"
    )
    cleaned["home_team"] = cleaned["home_team"].astype("string").str.strip()
    cleaned["away_team"] = cleaned["away_team"].astype("string").str.strip()
    cleaned = cleaned.dropna(subset=["date", "home_team", "away_team"])
    cleaned = cleaned[
        cleaned["home_team"].ne("") & cleaned["away_team"].ne("")
    ]

    rows = []
    for row in cleaned.itertuples(index=False):
        rows.append(
            (
                row.date.to_pydatetime().replace(tzinfo=None),
                row.home_team,
                row.away_team,
                None if pd.isna(row.home_goals) else int(row.home_goals),
                None if pd.isna(row.away_goals) else int(row.away_goals),
            )
        )
    return rows


def main():
    rows = prepare_rows(pd.read_csv(INPUT_PATH))
    if not rows:
        raise RuntimeError(f"No valid live matches found in {INPUT_PATH}.")

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

    print(f"Loaded or updated {len(rows)} live matches.")


if __name__ == "__main__":
    main()
