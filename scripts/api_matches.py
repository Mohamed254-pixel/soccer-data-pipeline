import os
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from load_live_matches import prepare_rows

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "live_matches.csv"
API_URL = "https://v3.football.api-sports.io/fixtures"


def fetch_matches():
    load_dotenv(PROJECT_ROOT / ".env")
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

    return parse_matches(payload)


def parse_matches(payload):
    """Parse and validate API fixtures before replacing staged data."""
    if not isinstance(payload, dict):
        raise RuntimeError("API-FOOTBALL response must be a JSON object.")
    if payload.get("errors"):
        # Do not echo external error payloads, which may contain credentials.
        raise RuntimeError("API-FOOTBALL reported an error. Check API access and quota.")

    fixtures = payload.get("response")
    if not isinstance(fixtures, list) or not fixtures:
        raise RuntimeError("API-FOOTBALL response must contain a nonempty fixture list.")

    matches = []
    for match in fixtures:
        try:
            record = {
                "fixture_id": match["fixture"]["id"],
                "date": match["fixture"]["date"],
                "home_team": match["teams"]["home"]["name"],
                "away_team": match["teams"]["away"]["name"],
                "home_goals": match["goals"]["home"],
                "away_goals": match["goals"]["away"]
            }
        except (KeyError, TypeError) as exc:
            raise RuntimeError("A fixture is missing required fields.") from exc
        matches.append(record)

    df = pd.DataFrame(
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
    prepare_rows(df)
    return df


def main():
    df = fetch_matches()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"Matches returned: {len(df)}")
    print(df.head())
    print(f"Saved {len(df)} matches to {OUTPUT_PATH}")


if __name__ == "__main__":
    from incremental import main as run_incremental_stage
    run_incremental_stage("extract_matches")
