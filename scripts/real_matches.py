import pandas as pd

matches = [
    ["Argentina", "France", 3, 3],
    ["Spain", "Brazil", 2, 1],
    ["England", "Croatia", 4, 2],
    ["Germany", "Curacao", 7, 1],
    ["Portugal", "Uzbekistan", 5, 0]
]

df = pd.DataFrame(
    matches,
    columns=["home_team", "away_team", "home_goals", "away_goals"]
)

df.to_csv("data/matches.csv", index=False)

print("Updated matches.csv")