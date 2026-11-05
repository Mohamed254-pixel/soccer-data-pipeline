from datetime import timedelta
from pathlib import Path
import logging
import subprocess
import sys
from time import perf_counter

import pendulum
from airflow.sdk import dag, task


PROJECT_ROOT = Path("/opt/soccer")
LOGGER = logging.getLogger(__name__)


def run_script(script_name):
    script_path = PROJECT_ROOT / "scripts" / script_name

    started = perf_counter()
    LOGGER.info("START | %s", script_name)
    try:
        # Stream child output into the Airflow task log; propagate failures for retries.
        with subprocess.Popen(
            [sys.executable, "-u", str(script_path)],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        ) as process:
            for line in process.stdout:
                LOGGER.info("%s | %s", script_name, line.rstrip())
            returncode = process.wait()
            if returncode:
                raise subprocess.CalledProcessError(returncode, process.args)
    except (subprocess.CalledProcessError, OSError):
        LOGGER.exception("FAIL | %s | duration=%.2fs", script_name, perf_counter() - started)
        raise
    LOGGER.info("SUCCESS | %s | duration=%.2fs", script_name, perf_counter() - started)


@dag(
    dag_id="premier_league_etl",
    description="Premier League Data Engineering Pipeline: extract, load, and validate",
    schedule="0 6 * * 1",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "mohamed",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["soccer", "etl", "mysql"],
)
def premier_league_etl():

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

    @task
    def validate_data_quality():
        run_script("validate_data_quality.py")

    matches_ready = extract_matches()
    teams_ready = extract_teams_and_venues()
    teams_loaded = load_teams_and_venues()
    matches_loaded = load_matches()
    quality_checked = validate_data_quality()

    (
        matches_ready
        >> teams_ready
        >> teams_loaded
        >> matches_loaded
        >> quality_checked
    )


dag = premier_league_etl()
