from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "premier_league_teams.csv"
API_URL = (
    "https://www.thesportsdb.com/api/v1/json/3/"
    "search_all_teams.php?l=English%20Premier%20League"
)


def fetch_teams():
    response = requests.get(API_URL, timeout=30)
    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("TheSportsDB returned invalid JSON.") from exc

    api_teams = payload.get("teams")
    if not isinstance(api_teams, list):
        raise RuntimeError("TheSportsDB response did not contain a team list.")

    teams = []
    for team in api_teams:
        teams.append(
            {
                "team_name": team["strTeam"],
                "stadium": team["strStadium"],
                "country": team["strCountry"],
            }
        )

    return pd.DataFrame(teams, columns=["team_name", "stadium", "country"])


def main():
    df = fetch_teams()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print(df.head())
    print(f"Saved {len(df)} teams to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
