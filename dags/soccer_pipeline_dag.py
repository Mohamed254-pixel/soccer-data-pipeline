from datetime import timedelta
from pathlib import Path
import subprocess
import sys

import pendulum
from airflow.sdk import dag, task


PROJECT_ROOT = Path("/opt/soccer")

def run_script(script_name):
    script_path = PROJECT_ROOT / "scripts" / script_name

    subprocess.run(
        [sys.executable, str(script_path)],
        cwd=PROJECT_ROOT,
        check=True,
    )

@dag(
    dag_id="premier_league_etl",
    schedule=None,
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    default_args={
        "owner": "mohamed",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["soccer", "etl", "mysql"],
)
def premier_league_etl():
    pass

    @task
    def extract_matches():
        run_script("api_matches.py")

    @task
    def extract_teams_and_venues():
        run_script("api_teams.py")

    @task
    def load_teams_and_venues():
        run_script("load_teams.py")

    @task
    def load_matches():
        run_script("load_live_matches.py")

    matches_ready = extract_matches()
    teams_ready = extract_teams_and_venues()

    teams_loaded = load_teams_and_venues()
    matches_loaded = load_matches()

    matches_ready >> teams_ready >> teams_loaded >> matches_loaded


premier_league_etl()