"""Static DAG contract and real child-process logging checks without Airflow installed.

Full DagBag import verification is a separate check in the Airflow environment.
"""

import ast
from datetime import timedelta
import logging
from pathlib import Path
import subprocess
import sys
from time import perf_counter

import pytest


DAG_PATH = Path(__file__).resolve().parents[1] / "dags" / "soccer_pipeline_dag.py"


def test_dag_schedule_and_retries():
    tree = ast.parse(DAG_PATH.read_text())
    definition = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "premier_league_etl")
    config = {kw.arg: kw.value for kw in definition.decorator_list[0].keywords}
    assert ast.literal_eval(config["schedule"]) == "0 6 * * 1"
    assert ast.literal_eval(config["catchup"]) is False
    assert ast.literal_eval(config["max_active_runs"]) == 1
    defaults = eval(compile(ast.Expression(config["default_args"]), str(DAG_PATH), "eval"), {"timedelta": timedelta})
    assert defaults["retries"] == 2
    assert defaults["retry_delay"] == timedelta(minutes=5)
    assert any(kw.arg == "tz" and ast.literal_eval(kw.value) == "UTC" for kw in config["start_date"].keywords)
    tasks = [node for node in definition.body if isinstance(node, ast.FunctionDef)]
    assert len(tasks) == 5
    assert [node.name for node in tasks] == [
        "extract_matches", "extract_teams_and_venues", "load_teams_and_venues", "load_matches", "validate_data_quality"
    ]


@pytest.mark.parametrize("exit_code", [0, 7])
def test_task_process_logs_and_failure(tmp_path, caplog, exit_code):
    # Execute the actual helper function with an isolated project root.
    tree = ast.parse(DAG_PATH.read_text())
    helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_script")
    namespace = {"PROJECT_ROOT": tmp_path, "sys": sys, "subprocess": subprocess,
                 "perf_counter": perf_counter, "LOGGER": logging.getLogger("dag-test")}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(DAG_PATH), "exec"), namespace)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "child.py").write_text(
        f"import sys\nprint('task output')\nprint('task stderr', file=sys.stderr)\nsys.exit({exit_code})\n"
    )
    with caplog.at_level(logging.INFO):
        if exit_code:
            with pytest.raises(subprocess.CalledProcessError) as exc:
                namespace["run_script"]("child.py")
            assert exc.value.returncode == exit_code
            assert "FAIL" in caplog.text
        else:
            namespace["run_script"]("child.py")
            assert "SUCCESS" in caplog.text
    assert "task output" in caplog.text
    assert "task stderr" in caplog.text
    assert "duration=" in caplog.text
