# Soccer Data Pipeline

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![MySQL 8.0+](https://img.shields.io/badge/MySQL-8.0%2B-orange)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

An end-to-end data engineering pipeline for the 2024 Premier League season.

The project extracts fixtures, teams, and venues from API-FOOTBALL, validates the data with Pandas, stages it in CSV files, and loads it into MySQL using repeatable UPSERT operations.

## Current Output

| Data    | Rows |      Unique IDs |
| ------- | ---: | --------------: |
| Matches |  380 | 380 fixture IDs |
| Teams   |   20 | 20 API team IDs |
| Venues  |   20 |    20 venue IDs |

Zero broken team-to-venue relationships.

This project is scoped only to the Premier League. Old international and mixed-league prototype data has been removed.

## Architecture

```text
API-FOOTBALL
      ↓
Python extraction
      ↓
Pandas validation
      ↓
CSV staging
      ↓
MySQL UPSERT loaders
      ↓
Premier League tables
```

The pipeline runs four steps:

1. Extract match data.
2. Extract team and venue data.
3. Load venues, then teams.
4. Load matches.

See [Architecture](docs/architecture.md) and [Data Model](docs/data-model.md) for more detail.

## Technology

* Python
* Pandas
* Requests
* MySQL
* API-FOOTBALL
* python-dotenv
* Git and GitHub

## Prerequisites

Before you start, make sure you have:

* Python 3.11+ installed (`python3 --version`)
* MySQL 8.0+ running locally or accessible remotely
* An API-FOOTBALL account and API key from [api-football.com](https://www.api-football.com/)
* Git installed to clone the repository

## Database Tables

| Table          | Purpose                          | Main key                        |
| -------------- | -------------------------------- | ------------------------------- |
| `live_matches` | Fixture dates, teams, and scores | `fixture_id`                    |
| `teams`        | Club identity and details        | `team_id`, unique `api_team_id` |
| `venues`       | Stadium information              | `venue_id`                      |

`teams.venue_id` is a foreign key referencing `venues.venue_id`.

The match table currently stores home and away team names. Replacing them with team foreign keys is a planned normalization step.

## Reliability Features

* API timeouts and HTTP error handling
* API response validation
* Required CSV-column validation
* Duplicate-ID checks
* Team-to-venue relationship validation: before loading, the pipeline verifies that every non-null `venue_id` referenced by a team exists in `venues.csv`. Missing referenced IDs stop the load before any database write.
* Transaction rollback after failed loads
* Primary keys, unique keys, foreign keys, and indexes
* UPSERT loading that prevents duplicates
* Credentials stored outside source code
* Separate administrator and application database permissions

## Quick Start

### 1. Clone the project

```bash
git clone https://github.com/Mohamed254-pixel/soccer-data-pipeline.git
cd soccer-data-pipeline
```

### 2. Create the environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

### 3. Configure credentials

```bash
cp .env.example .env
```

Add your API and MySQL values:

```dotenv
API_KEY=your_api_football_key
FOOTBALL_LEAGUE_ID=39
FOOTBALL_SEASON=2024

DB_HOST=localhost
DB_PORT=3306
DB_USER=soccer_app
DB_PASSWORD=your_private_app_password
DB_NAME=soccer_db
```

Never commit the `.env` file.

### 4. Create the database

Run `sql/schema.sql` with a MySQL administrator account.

For an existing older database, apply these migrations in order:

```text
sql/migrations/001_align_live_matches_schema.sql
sql/migrations/002_add_team_and_venue_schema.sql
```

The pipeline account only needs `SELECT`, `INSERT`, `UPDATE`, and `DELETE` permissions.

### 5. Run the pipeline

```bash
python3 run_pipeline.py
```

A successful run refreshes:

```text
data/live_matches.csv
data/teams.csv
data/venues.csv
```

It then inserts or updates the related MySQL records.

### Sample Console Output

```text
Step 1: Pulling match data from API-FOOTBALL...
Matches returned: 380
Saved 380 matches to data/live_matches.csv

Step 2: Pulling team and venue data from API-FOOTBALL...
Saved 20 teams to data/teams.csv
Saved 20 venues to data/venues.csv

Step 3: Loading teams and venues into MySQL...
Loaded or updated 20 venues.
Loaded or updated 20 Premier League teams.

Step 4: Loading matches into MySQL...
Loaded or updated 380 live matches.

Pipeline completed successfully.
```

## Verification

```sql
SELECT COUNT(*), COUNT(DISTINCT fixture_id)
FROM live_matches;

SELECT COUNT(*), COUNT(DISTINCT api_team_id)
FROM teams;

SELECT COUNT(*), COUNT(DISTINCT venue_id)
FROM venues;
```

Expected results match the [Current Output](#current-output) table above.

## Troubleshooting

### API authentication failure

The `API_KEY` in `.env` is missing or invalid. Compare it with the key in your API-FOOTBALL dashboard.

### API rate-limit error

Wait for the API limit to reset before running the extraction again.

### MySQL access denied

Confirm that `sql/schema.sql` was run with an administrator account and that `soccer_app` has `SELECT`, `INSERT`, `UPDATE`, and `DELETE` permissions on `soccer_db`.

### Team-to-venue validation failure

A non-null venue ID in `data/teams.csv` is missing from `data/venues.csv`. Compare the IDs in both files and correct the incomplete extraction before rerunning the loader.

### Schema mismatch

Apply both migration files in order before running the pipeline against an older database.

## Project Structure

```text
soccer-data-pipeline/
├── data/
│   ├── live_matches.csv
│   ├── teams.csv
│   └── venues.csv
├── docs/
│   ├── architecture.md
│   └── data-model.md
├── scripts/
│   ├── api_matches.py
│   ├── api_teams.py
│   ├── db.py
│   ├── load_live_matches.py
│   └── load_teams.py
├── sql/
│   ├── migrations/
│   ├── analytics.sql
│   └── schema.sql
├── .env.example
├── LICENSE
├── requirements.txt
├── run_pipeline.py
└── README.md
```

## Roadmap

* Replace match team names with team foreign keys
* Add incremental loading
* Add automated data-quality tests
* Add pipeline logging, retries, and freshness checks
* Schedule runs with Airflow
* Containerize the pipeline with Docker
* Store raw API data in Amazon S3
* Deploy MySQL to Amazon RDS
* Add standings, player statistics, and match events

## License

This project is licensed under the [MIT License](LICENSE).
