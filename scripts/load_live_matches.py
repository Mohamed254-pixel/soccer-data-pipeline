import pandas as pd
import mysql.connector

df = pd.read_csv("data/live_matches.csv")

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Kadaa_930",
    database="soccer_db"
)

cursor = conn.cursor()

for _, row in df.iterrows():
    cursor.execute("""
        INSERT INTO live_matches
        (match_date, home_team, away_team, home_goals, away_goals)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        row["date"],
        row["home_team"],
        row["away_team"],
        row["home_goals"],
        row["away_goals"]
    ))

conn.commit()
conn.close()