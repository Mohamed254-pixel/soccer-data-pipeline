import os
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from load_teams import prepare_team_rows, prepare_venue_rows

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

    return parse_teams_and_venues(payload)


def parse_teams_and_venues(payload):
    """Parse teams and optional venues, retaining a stable CSV schema."""
    if not isinstance(payload, dict):
        raise RuntimeError("API-FOOTBALL response must be a JSON object.")
    if payload.get("errors"):
        raise RuntimeError("API-FOOTBALL reported an error. Check API access and quota.")

    api_results = payload.get("response")
    if not isinstance(api_results, list) or not api_results:
        raise RuntimeError("API response must contain a nonempty team list.")

    teams = []
    venues = []

    for result in api_results:
        if not isinstance(result, dict):
            raise RuntimeError("Each team result must be a JSON object.")
        team = result.get("team") or {}
        venue = result.get("venue") or {}
        if not isinstance(team, dict) or not isinstance(venue, dict):
            raise RuntimeError("Team and venue fields must be JSON objects.")

        if team.get("id") is None or not team.get("name"):
            raise RuntimeError("A team is missing its ID or name.")

        venue_id = venue.get("id")
        national = team.get("national", False)
        if not isinstance(national, bool):
            raise RuntimeError("Team national flag must be a boolean.")

        teams.append(
            {
                "api_team_id": team["id"],
                "team_name": team["name"],
                "team_code": team.get("code"),
                "country": team.get("country"),
                "league": "Premier League",
                "stadium": venue.get("name"),
                "founded": team.get("founded"),
                "is_national": int(national),
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
        pd.DataFrame(venues, columns=[
            "venue_id", "venue_name", "address", "city", "capacity", "surface", "image_url"
        ])
        .drop_duplicates(subset=["venue_id"])
        .sort_values("venue_id")
    )
    prepare_team_rows(teams_df)
    prepare_venue_rows(venues_df)

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
