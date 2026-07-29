# Soccer Data Pipeline

An end-to-end data engineering project that extracts football data from APIs,
cleans and validates it with Pandas, stores it in MySQL, and supports SQL and
notebook-based analysis.

## Highlights

- Extracts Premier League fixtures from API-FOOTBALL
- Collects Premier League team and stadium information from TheSportsDB
- Processes 43,281 historical international match records
- Validates 43,277 completed historical results for database loading
- Uses CSV files as a transparent staging layer
- Loads data with batch upserts so pipeline reruns do not create duplicates
- Keeps API and database credentials outside the source code
- Stops clearly when an API, configuration, or pipeline step fails

## Architecture

```text
Football APIs
      │
      ▼
Python extraction
      │
      ▼
Pandas validation and transformation
      │
      ▼
CSV staging files
      │
      ▼
MySQL tables
      │
      ▼
SQL and Jupyter analysis
```

## Data

| Source | Scope | Records used |
| --- | --- | ---: |
| Historical results CSV | International matches from 1872 onward | 43,277 completed matches |
| API-FOOTBALL | Premier League 2024 fixtures | 380 matches |
| TheSportsDB | Premier League teams and stadiums | 10 teams in the current CSV |

Four historical fixtures without final scores remain in the source data but are
excluded by the loader's validation rules.

## Technology

- Python 3.11+
- Pandas
- Requests
- MySQL
- SQL
- API-FOOTBALL
- TheSportsDB
- Jupyter Notebook

## Quick Start

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

The versions in `requirements.txt` match the environment used to validate this
project.

### 3. Create the database

Run the schema and team seed files with a MySQL administrator account:

```bash
mysql -u root -p < sql/schema.sql
mysql -u root -p < sql/create_teams_table.sql
```

Create a dedicated pipeline account:

```sql
CREATE USER IF NOT EXISTS 'soccer_app'@'localhost'
IDENTIFIED BY 'choose-a-private-app-password';

GRANT SELECT, INSERT, UPDATE, DELETE
ON soccer_db.*
TO 'soccer_app'@'localhost';
```

### 4. Configure environment variables

Create your private local configuration:

```bash
cp .env.example .env
```

Edit `.env` and supply your API key and MySQL app password:

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

The `.env` file is ignored by Git. Never commit real API keys or passwords.

### 5. Run the live pipeline

```bash
python3 run_pipeline.py
```

This extracts the configured league season, refreshes
`data/live_matches.csv`, and inserts or updates the corresponding database
records.

### 6. Load historical results

```bash
python3 scripts/load_results_to_mysql.py
```

### 7. Verify the load

```sql
SELECT COUNT(*) AS live_matches FROM soccer_db.live_matches;
SELECT COUNT(*) AS historical_results FROM soccer_db.results;
```

The included data produces 380 live-match rows and 43,277 historical-result
rows. Repeating either loader leaves these counts unchanged.

## Database Tables

| Table | Purpose | Duplicate protection |
| --- | --- | --- |
| `live_matches` | API fixture dates, teams, and scores | Unique date/home/away fixture key |
| `results` | Historical international match results | Primary key on source `id` |
| `teams` | Team, country, league, and stadium details | Unique team/league key |

## Project Structure

```text
soccer-data-pipeline/
├── data/                       # CSV source and staging data
├── scripts/
│   ├── api_matches.py          # Extract API-FOOTBALL fixtures
│   ├── api_teams.py            # Extract TheSportsDB teams
│   ├── db.py                   # Shared environment-based DB connection
│   ├── load_live_matches.py    # Validate and upsert API fixtures
│   ├── load_results_to_mysql.py
│   └── soccer_analysis.ipynb
├── sql/
│   ├── analytics.sql           # Example analytical queries
│   ├── create_teams_table.sql  # Team seed data
│   └── schema.sql              # Database and table definitions
├── .env.example                # Safe configuration template
├── requirements.txt            # Reproducible Python environment
├── run_pipeline.py             # Live ETL entry point
└── README.md
```

## Analytics

The SQL and notebook analysis cover:

- Highest-scoring matches
- Goals by team
- Average home goals
- Home and away scoring comparisons
- Team and league joins
- Tournament and match-volume trends
- Data-quality checks

## Reliability and Security

- Required configuration is validated before database connections are created.
- API requests use timeouts, HTTP error checks, and response validation.
- Database writes are committed only after a successful batch.
- Failed writes are rolled back and connections are closed safely.
- Unique database keys and upserts make repeat loads idempotent.
- Secrets are loaded from `.env`, which is excluded from version control.

## Roadmap

- Interactive Streamlit dashboard
- Automated tests and GitHub Actions
- Scheduled pipeline runs
- Additional leagues, standings, and player statistics
- Match-prediction experiments
