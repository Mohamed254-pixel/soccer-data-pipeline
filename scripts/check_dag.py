"""Import the real DAG with Airflow installed; never starts services or tasks."""

from datetime import timedelta
from pathlib import Path

import airflow
from airflow.dag_processing.dagbag import DagBag


def main():
    if airflow.__version__ != "3.3.1":
        raise RuntimeError("Run this check with the deployed Airflow 3.3.1 version.")
    path = Path(__file__).resolve().parents[1] / "dags" / "soccer_pipeline_dag.py"
    bag = DagBag(dag_folder=str(path))
    if bag.import_errors:
        raise RuntimeError("Airflow DAG import failed; inspect local import diagnostics.")
    dag = bag.dags["premier_league_etl"]
    names = ["extract_matches", "extract_teams_and_venues", "load_teams_and_venues",
             "load_matches", "validate_data_quality"]
    assert set(dag.task_ids) == set(names)
    assert dag.schedule == "0 6 * * 1"
    assert str(dag.timezone) == "UTC"
    assert not dag.catchup and dag.max_active_runs == 1
    for index, name in enumerate(names):
        task = dag.get_task(name)
        assert task.downstream_task_ids == ({names[index + 1]} if index < 4 else set())
        assert task.retries == 2
        assert task.retry_delay == timedelta(minutes=5)
        assert task.execution_timeout == timedelta(hours=1)
    print("Airflow 3.3.1: import, five-task dependencies, UTC schedule, retries and timeouts verified.")


if __name__ == "__main__":
    main()
