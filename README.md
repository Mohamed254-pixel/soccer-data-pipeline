# Soccer Data Pipeline

## Overview

This project is an end-to-end data engineering pipeline that collects, transforms, stores, and analyzes football data using Python, Pandas, MySQL, SQL, and API-FOOTBALL.

The project combines historical international match data with live football data retrieved from a football API to demonstrate ETL (Extract, Transform, Load) workflows and database analytics.

## Dataset

### Historical Dataset

- 43,281 international football matches
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

## Project Structure

```text
soccer-data-pipeline/
├── data/
│   ├── results.csv
│   └── live_matches.csv
├── scripts/
│   ├── api_matches.py
│   ├── load_live_matches.py
│   ├── load_results_to_mysql.py
│   └── api_teams.py
├── sql/
│   ├── analytics.sql
│   └── create_teams_table.sql
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

- Loaded 43,281 historical matches into MySQL
- Loaded 380 live Premier League matches from API-FOOTBALL
- Built an automated ETL workflow using Python and SQL
- Performed database analytics using MySQL queries

## Future Improvements

- Power BI dashboard
- Tableau visualizations
- Automated scheduling with GitHub Actions
- Additional API endpoints (standings, player statistics)
- Match prediction models
