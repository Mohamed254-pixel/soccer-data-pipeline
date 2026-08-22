import os
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

TEAMS_OUTPUT_PATH = PROJECT_ROOT / "data" / "teams.csv"
VENUES_OUTPUT_PATH = PROJECT_ROOT / "data" / "venues.csv"
API_URL = "https://v3.football.api-sports.io/teams"


def fetch_teams_and_venues():
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError("API_KEY is missing from the .env file.")

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

    api_results = payload.get("response")
    if not isinstance(api_results, list):
        raise RuntimeError("API response did not contain a team list.")

    teams = []
    venues = []

    for result in api_results:
        team = result.get("team") or {}
        venue = result.get("venue") or {}

        if team.get("id") is None or not team.get("name"):
            raise RuntimeError("A team is missing its ID or name.")

        venue_id = venue.get("id")

        teams.append(
            {
                "api_team_id": team["id"],
                "team_name": team["name"],
                "team_code": team.get("code"),
                "country": team.get("country"),
                "league": "Premier League",
                "stadium": venue.get("name"),
                "founded": team.get("founded"),
                "is_national": int(bool(team.get("national"))),
                "logo_url": team.get("logo"),
                "venue_id": venue_id,
            }
        )

        if venue_id is not None:
            venues.append(
                {
                    "venue_id": venue_id,
                    "venue_name": venue.get("name"),
                    "address": venue.get("address"),
                    "city": venue.get("city"),
                    "capacity": venue.get("capacity"),
                    "surface": venue.get("surface"),
                    "image_url": venue.get("image"),
                }
            )

    teams_df = pd.DataFrame(teams).sort_values("team_name")
    venues_df = (
        pd.DataFrame(venues)
        .drop_duplicates(subset=["venue_id"])
        .sort_values("venue_id")
    )

    return teams_df, venues_df


def main():
    teams_df, venues_df = fetch_teams_and_venues()

    TEAMS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    teams_df.to_csv(TEAMS_OUTPUT_PATH, index=False)
    venues_df.to_csv(VENUES_OUTPUT_PATH, index=False)

    print(teams_df.head())
    print(f"Saved {len(teams_df)} teams to {TEAMS_OUTPUT_PATH}")
    print(f"Saved {len(venues_df)} venues to {VENUES_OUTPUT_PATH}")


if __name__ == "__main__":
    main()