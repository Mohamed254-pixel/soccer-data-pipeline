import requests
import pandas as pd

url = "https://www.thesportsdb.com/api/v1/json/3/search_all_teams.php?l=English%20Premier%20League"

response = requests.get(url)
data = response.json()

teams = []

for team in data["teams"]:
    teams.append({
        "team_name": team["strTeam"],
        "stadium": team["strStadium"],
        "country": team["strCountry"]
    })

df = pd.DataFrame(teams)

df.to_csv("data/premier_league_teams.csv", index=False)

print(df.head())
print(f"Saved {len(df)} teams")

for team in data["teams"]:
    print(team["strTeam"])