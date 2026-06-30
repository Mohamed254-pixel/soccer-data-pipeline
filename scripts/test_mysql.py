import mysql.connector

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Kadaa_930",
    database="soccer_db"
)

print("Connected!")

conn.close()