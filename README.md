# Soccer Data Pipeline

## Overview

This project is an end-to-end data engineering pipeline that collects, transforms, stores, and analyzes football data using Python, Pandas, MySQL, SQL, and API-FOOTBALL.

The project combines historical international match data with live football data retrieved from a football API to demonstrate ETL (Extract, Transform, Load) workflows and database analytics.

## Dataset

### Historical Dataset

- 43,281 international football matches
- 43,277 completed-score records pass the current validation rules
- Historical data from 1872 to present
- Match dates, teams, scores, tournaments, cities, and countries

### Live API Data

- Premier League 2024 season data
- Retrieved from API-FOOTBALL
- 380 match records loaded into MySQL

## Tech Stack

- Python
- Pandas
- MySQL
- SQL
- API-FOOTBALL
- Jupyter Notebook
- Git
- GitHub

## Architecture

```text
API-FOOTBALL
      ↓
Python Requests
      ↓
Pandas Transformations
      ↓
CSV Storage
      ↓
MySQL Database
      ↓
SQL Analytics
```

## Setup

### 1. Rotate the exposed database password

An earlier version of this project contained a MySQL password in tracked Python
files. Change that password in MySQL before using the project again. Removing it
from the latest code does not make the old password safe because Git history is
public.

Log in to MySQL with the current root password and replace it:

```sql
ALTER USER 'root'@'localhost'
IDENTIFIED BY 'choose-a-new-private-root-password';
```

### 2. Create a Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

### 3. Create the MySQL database and tables

```bash
mysql -u root -p < sql/schema.sql
mysql -u root -p < sql/create_teams_table.sql
```

Then create a dedicated application user instead of connecting as `root`:

```sql
CREATE USER IF NOT EXISTS 'soccer_app'@'localhost'
IDENTIFIED BY 'choose-a-different-app-password';

GRANT SELECT, INSERT, UPDATE, DELETE
ON soccer_db.*
TO 'soccer_app'@'localhost';
```

### 4. Configure local environment variables

Copy the safe example without overwriting an existing `.env`:

```bash
cp -n .env.example .env
```

If `.env` already exists, copy the missing `DB_` settings from `.env.example`
into it. Use the new `soccer_app` password. The real `.env` file is ignored by
Git and must never be committed.

### 5. Run the live-match pipeline

```bash
python3 run_pipeline.py
```

The pipeline retrieves API data, writes `data/live_matches.csv`, and safely
inserts or updates the corresponding MySQL records.

### 6. Load the historical dataset

```bash
python3 scripts/load_results_to_mysql.py
```

## Project Structure

```text
soccer-data-pipeline/
├── .env.example
├── requirements.txt
├── data/
│   ├── results.csv
│   └── live_matches.csv
├── scripts/
│   ├── api_matches.py
│   ├── db.py
│   ├── load_live_matches.py
│   ├── load_results_to_mysql.py
│   └── api_teams.py
├── sql/
│   ├── analytics.sql
│   ├── create_teams_table.sql
│   └── schema.sql
├── run_pipeline.py
└── README.md
```

## ETL Workflow

1. Extract football data from API-FOOTBALL
2. Transform JSON responses using Pandas
3. Save processed data to CSV
4. Load data into MySQL
5. Run SQL analytics queries

## Analysis Performed

- Top tournaments by match count
- Match activity trends over time
- Data quality checks
- Team performance analysis
- SQL analytics on live match data

## Results

- Validated 43,277 completed historical matches for MySQL
- Loaded 380 live Premier League matches from API-FOOTBALL
- Built an automated ETL workflow using Python and SQL
- Performed database analytics using MySQL queries

## Future Improvements

- Power BI dashboard
- Tableau visualizations
- Automated scheduling with GitHub Actions
- Additional API endpoints (standings, player statistics)
- Match prediction models
