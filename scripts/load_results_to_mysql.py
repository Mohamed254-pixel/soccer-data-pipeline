import pandas as pd
import mysql.connector

# Read the CSV
df = pd.read_csv("data/results.csv")

df["home_score"] = pd.to_numeric(df["home_score"], errors="coerce")
df["away_score"] = pd.to_numeric(df["away_score"], errors="coerce")
df["id"] = pd.to_numeric(df["id"], errors="coerce")

df = df.dropna(subset=["home_score", "away_score", "id"])

# Connect to MySQL
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Kadaa_930",
    database="soccer_db"
)

cursor = conn.cursor()

# Insert rows
for _, row in df.iterrows():
    cursor.execute("""
        INSERT INTO results
        (match_date, home_team, away_team, home_score, away_score,
         tournament, city, country, id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        row["date"],
        row["home_team"],
        row["away_team"],
        int(row["home_score"]),
        int(row["away_score"]),
        row["tournament"],
        row["city"],
        row["country"],
        int(row["id"])
    ))

conn.commit()

print(f"Loaded {len(df)} rows")

cursor.close()
conn.close()