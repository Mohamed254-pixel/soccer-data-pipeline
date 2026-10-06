# Soccer Data Pipeline

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![MySQL 8.0+](https://img.shields.io/badge/MySQL-8.0%2B-orange)
![Apache Airflow 3.3.1](https://img.shields.io/badge/Apache%20Airflow-3.3.1-017CEE)
![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

An end-to-end data engineering pipeline for the 2024 Premier League season.

The project extracts match, team, and venue data from API-FOOTBALL, transforms and validates it with Python and Pandas, stages it in CSV files, and loads it into MySQL using repeatable UPSERT operations.

Apache Airflow orchestrates the ETL workflow, while Docker Compose provides a consistent environment for running Airflow and its supporting services.

## Current Output

| Data | Rows | Unique IDs |
| --- | ---: | ---: |
| Matches | 380 | 380 fixture IDs |
| Teams | 20 | 20 API team IDs |
| Venues | 20 | 20 venue IDs |

The completed pipeline produced:

- Zero duplicate fixture IDs
- Zero broken team-to-venue relationships
- One successful four-task Airflow DAG run
- Repeatable MySQL loads using UPSERT logic

This project is scoped to the Premier League. Old international and mixed-league prototype data has been removed.

## Architecture

```text
API-FOOTBALL
      ↓
Python extraction
      ↓
Pandas transformation and validation
      ↓
CSV staging
      ↓
MySQL UPSERT loaders
      ↓
Premier League relational tables
```

Apache Airflow controls the order in which the pipeline scripts run:

```text
extract_matches
      ↓
extract_teams_and_venues
      ↓
load_teams_and_venues
      ↓
load_matches
```

Docker Compose runs the Airflow services, including the API server, scheduler, worker, DAG processor, triggerer, PostgreSQL metadata database, and Redis.

The project uses a shared Docker volume for staged CSV data so every Airflow task can access the same files.

See [Architecture](docs/architecture.md) and [Data Model](docs/data-model.md) for more detail.

## Technology

- Python
- Pandas
- Requests
- MySQL
- API-FOOTBALL
- Apache Airflow 3.3.1
- Docker and Docker Compose
- PostgreSQL for Airflow metadata
- Redis for Airflow task messaging
- python-dotenv
- Git and GitHub

## Database Tables

| Table | Purpose | Main key |
| --- | --- | --- |
| `live_matches` | Fixture dates, teams, and scores | `fixture_id` |
| `teams` | Club identity and details | `team_id`, unique `api_team_id` |
| `venues` | Stadium information | `venue_id` |

`teams.venue_id` is a foreign key referencing `venues.venue_id`.

The match table currently stores home and away team names. Replacing them with team foreign keys is a planned normalization step.

## Reliability Features

- API timeouts and HTTP error handling
- API response validation
- Required CSV-column validation
- Duplicate-ID checks
- Team-to-venue relationship validation
- Transaction rollback after failed database loads
- Primary keys, unique keys, foreign keys, and indexes
- UPSERT loading that prevents duplicate records
- Airflow task dependencies
- Airflow retries and task-level logs
- Shared Docker storage for staged pipeline data
- Credentials stored outside the source code
- Separate administrator and application database permissions

Before loading teams, the pipeline checks that every non-null `venue_id` in `teams.csv` exists in `venues.csv`. Missing referenced IDs stop the load before any database write.

## Prerequisites

Before running the project, install:

- Python 3.11 or newer
- MySQL 8.0 or newer
- Git
- Docker Desktop with Docker Compose
- An API-FOOTBALL account and API key

Confirm the main tools are available:

```bash
python3 --version
mysql --version
docker --version
docker compose version
```

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Mohamed254-pixel/soccer-data-pipeline.git
cd soccer-data-pipeline
```

### 2. Create the Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

### 3. Configure credentials

Copy the example environment file:

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

AIRFLOW_UID=50000
FERNET_KEY=your_generated_fernet_key
```

Never commit the `.env` file.

When the pipeline runs inside Docker on macOS, the Airflow services connect to the host MySQL server through `host.docker.internal`.

### 4. Create the MySQL database

Run `sql/schema.sql` using a MySQL administrator account.

For an existing older database, apply these migrations in order:

```text
sql/migrations/001_align_live_matches_schema.sql
sql/migrations/002_add_team_and_venue_schema.sql
```

The pipeline account only needs `SELECT`, `INSERT`, `UPDATE`, and `DELETE` permissions on `soccer_db`.

## Run Locally With Python

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Run the complete pipeline:

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

## Run With Docker and Airflow

### 1. Validate the Docker Compose file

```bash
docker compose config --quiet
```

No output means the configuration is valid.

### 2. Build the custom Airflow image

```bash
docker compose build
```

The first build can take several minutes because Docker must download and install the required packages.

### 3. Initialize Airflow

```bash
docker compose up airflow-init
```

A successful initialization ends with:

```text
airflow-init-1 exited with code 0
```

### 4. Start the Airflow services

```bash
docker compose up -d
```

Check their status:

```bash
docker compose ps
```

Wait until the main Airflow services show `healthy`.

### 5. Open the Airflow interface

Open:

[http://localhost:8080](http://localhost:8080)

Default local credentials:

```text
Username: airflow
Password: airflow
```

Find the `premier_league_etl` DAG and select **Trigger** to start a manual pipeline run.

The DAG currently uses manual triggering and does not have an automatic schedule.

### 6. Check for DAG import errors

```bash
docker compose exec airflow-scheduler airflow dags list-import-errors
```

A correctly loaded DAG returns:

```text
No data found
```

In this command, `No data found` means Airflow found no import errors.

### 7. Check previous DAG runs

```bash
docker compose exec airflow-scheduler airflow dags list-runs premier_league_etl
```

### 8. Stop Airflow

```bash
docker compose down
```

The named Docker volumes preserve Airflow metadata and staged pipeline data.

Avoid using `docker compose down -v` unless you intentionally want to delete the stored Docker volume data.

## Verification

Verify the final MySQL row counts:

```sql
SELECT COUNT(*), COUNT(DISTINCT fixture_id)
FROM live_matches;

SELECT COUNT(*), COUNT(DISTINCT api_team_id)
FROM teams;

SELECT COUNT(*), COUNT(DISTINCT venue_id)
FROM venues;
```

Expected results:

```text
Matches: 380 total, 380 unique fixture IDs
Teams:   20 total, 20 unique API team IDs
Venues:  20 total, 20 unique venue IDs
```

## Troubleshooting

### Docker daemon connection error

If Docker reports that it cannot connect to the Docker daemon, open Docker Desktop and wait until the engine finishes starting.

Confirm it is running:

```bash
docker ps
```

### Docker Compose YAML error

Validate the file:

```bash
docker compose config --quiet
```

Check the reported line for duplicate YAML keys or incorrect indentation.

### Airflow DAG does not appear

Check for import errors:

```bash
docker compose exec airflow-scheduler airflow dags list-import-errors
```

Confirm the DAG exists:

```bash
docker compose exec airflow-scheduler airflow dags list | grep premier_league_etl
```

### Airflow task fails

Open the failed task in the Airflow interface and select **Logs**.

You can also check container logs:

```bash
docker compose logs airflow-worker
docker compose logs airflow-scheduler
```

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
├── config/
├── dags/
│   └── soccer_pipeline_dag.py
├── data/
│   ├── live_matches.csv
│   ├── teams.csv
│   └── venues.csv
├── docs/
│   ├── architecture.md
│   └── data-model.md
├── logs/
├── plugins/
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
├── .gitignore
├── docker-compose.yaml
├── Dockerfile
├── LICENSE
├── requirements-airflow.txt
├── requirements.txt
├── run_pipeline.py
└── README.md
```

The `config/airflow.cfg` file and Airflow `logs/` directory are generated locally and ignored by Git.

## Roadmap

- Add an Airflow data-quality validation task
- Replace match team names with team foreign keys
- Add incremental loading
- Add a weekly Airflow schedule
- Add automated tests and GitHub Actions
- Add pipeline freshness monitoring
- Store raw API responses in Amazon S3
- Deploy the database to Amazon RDS
- Add standings, player statistics, and match events
- Build a Power BI dashboard

## License

This project is licensed under the [MIT License](LICENSE).