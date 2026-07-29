import os
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "live_matches.csv"
API_URL = "https://v3.football.api-sports.io/fixtures"


def fetch_matches():
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError(
            "API_KEY is missing. Copy .env.example to .env and add your API key."
        )

    headers = {"x-apisports-key": api_key}
    params = {
        "league": int(os.getenv("FOOTBALL_LEAGUE_ID", "39")),
        "season": int(os.getenv("FOOTBALL_SEASON", "2024")),
    }

    response = requests.get(
        API_URL,
        headers=headers,
        params=params,
        timeout=30,
    )
    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("API-FOOTBALL returned invalid JSON.") from exc

    if payload.get("errors"):
        raise RuntimeError(f"API-FOOTBALL error: {payload['errors']}")

    fixtures = payload.get("response")
    if not isinstance(fixtures, list):
        raise RuntimeError("API-FOOTBALL response did not contain a fixture list.")

    matches = []
    for match in fixtures:
        matches.append(
            {
                "fixture_id": match["fixture"]["id"],
                "date": match["fixture"]["date"],
                "home_team": match["teams"]["home"]["name"],
                "away_team": match["teams"]["away"]["name"],
                "home_goals": match["goals"]["home"],
                "away_goals": match["goals"]["away"]
            }
        )

    return pd.DataFrame(
        matches,
        columns=[
            "fixture_id",
            "date",
            "home_team",
            "away_team",
            "home_goals",
            "away_goals",
        ],
    )


def main():
    df = fetch_matches()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"Matches returned: {len(df)}")
    print(df.head())
    print(f"Saved {len(df)} matches to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
