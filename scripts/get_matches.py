import csv

with open("data/matches.csv", "w", newline="") as file:
    writer = csv.writer(file)

    writer.writerow(["home_team", "away_team", "home_goals", "away_goals"])

    writer.writerow(["Argentina", "France", 3, 3])
    writer.writerow(["Spain", "Brazil", 2, 1])

print("CSV file created")