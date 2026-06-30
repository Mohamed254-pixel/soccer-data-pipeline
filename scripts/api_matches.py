import requests
import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("API_KEY")

url = "https://v3.football.api-sports.io/fixtures"

headers = {
    "x-apisports-key": API_KEY
}

params = {
    "league": 39,
    "season": 2024
}

response = requests.get(
    url,
    headers=headers,
    params=params
)

data = response.json()

print("Matches returned:", len(data["response"]))

matches = []

for match in data["response"]:
    matches.append({
        "date": match["fixture"]["date"],
        "home_team": match["teams"]["home"]["name"],
        "away_team": match["teams"]["away"]["name"],
        "home_goals": match["goals"]["home"],
        "away_goals": match["goals"]["away"]
    })

df = pd.DataFrame(matches)

print(df.head())

df.to_csv("data/live_matches.csv", index=False)

print(f"Saved {len(df)} matches")