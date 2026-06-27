import pandas as pd
import random

teams = [
    # Premier League
    "Arsenal", "Liverpool", "Manchester City", "Chelsea",

    # La Liga
    "Real Madrid", "Barcelona", "Atletico Madrid",

    # Bundesliga
    "Bayern Munich", "Borussia Dortmund",

    # Serie A
    "Inter Milan", "Juventus", "AC Milan",

    # Ligue 1
    "PSG", "Marseille",

    # MLS
    "LAFC", "Inter Miami", "Seattle Sounders",

    # International
    "Argentina", "Brazil", "France", "England"
]

data = []

for i in range(1000):
    home_team = random.choice(teams)
    away_team = random.choice(teams)

    while home_team == away_team:
        away_team = random.choice(teams)

    home_goals = random.randint(0, 5)
    away_goals = random.randint(0, 5)

    data.append([
        home_team,
        away_team,
        home_goals,
        away_goals
    ])

df = pd.DataFrame(
    data,
    columns=[
        "home_team",
        "away_team",
        "home_goals",
        "away_goals"
    ]
)

df.to_csv("data/matches.csv", index=False)

print(f"Created {len(df)} matches")