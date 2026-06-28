# Soccer Data Pipeline

A data engineering project that ingests, processes, stores, and analyzes over 43,000 international football matches using Python, Pandas, MySQL, and SQL.

## Overview

This project demonstrates an end-to-end data pipeline built with real-world soccer data. Historical international match results are processed with Python, loaded into a MySQL database, and analyzed using SQL queries to generate insights on teams, tournaments, scoring trends, and match history.

## Tech Stack

* Python
* Pandas
* MySQL
* SQL
* Git
* GitHub

## Dataset

**International Football Results (1872–Present)**

* 43,277 match records loaded into MySQL
* 150+ years of international football history
* Includes match dates, teams, scores, tournaments, cities, and countries

## Project Architecture

```text
CSV Dataset
    ↓
Python (Pandas)
    ↓
Data Cleaning & Transformation
    ↓
MySQL Database
    ↓
SQL Analytics
    ↓
GitHub Version Control
```

## Features

* Imported and processed 43,277 real football matches
* Loaded data into a MySQL relational database
* Created reusable Python ETL scripts
* Built analytical SQL queries for reporting
* Managed source control with Git and GitHub

## Example Analytics

### Most Common Tournaments

```sql
SELECT tournament,
       COUNT(*) AS matches
FROM results
GROUP BY tournament
ORDER BY matches DESC;
```

### Teams With Most Matches Played

```sql
SELECT home_team,
       COUNT(*) AS matches_played
FROM results
GROUP BY home_team
ORDER BY matches_played DESC;
```

### Highest Scoring Matches

```sql
SELECT home_team,
       away_team,
       home_score + away_score AS total_goals
FROM results
ORDER BY total_goals DESC;
```

## Repository Structure

```text
soccer-data-pipeline/
├── data/
│   └── results.csv
├── scripts/
│   ├── api_matches.py
│   ├── get_matches.py
│   ├── real_matches.py
│   └── load_results_to_mysql.py
├── sql/
│   ├── analytics.sql
│   └── create_teams_table.sql
└── README.md
```

## Future Improvements

* Integrate live football APIs
* Automate scheduled data ingestion
* Build dashboards with Power BI
* Deploy the pipeline to cloud infrastructure
* Add data quality validation checks

## Author

Mohamed Ibrahim

Management Information Systems (MIS) Student
San José State University
