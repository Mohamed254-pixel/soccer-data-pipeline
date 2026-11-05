import logging
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

import run_pipeline


SCRIPTS = ["api_matches.py", "api_teams.py", "load_teams.py", "load_live_matches.py", "validate_data_quality.py"]


def test_pipeline_order_and_logging(monkeypatch, caplog):
    run = Mock()
    monkeypatch.setattr(run_pipeline.subprocess, "run", run)
    with caplog.at_level(logging.INFO):
        run_pipeline.main()
    assert [Path(call.args[0][-1]).name for call in run.call_args_list] == SCRIPTS
    assert all(call.kwargs["check"] for call in run.call_args_list)
    for label in ("START", "SUCCESS", "duration="):
        assert caplog.text.count(label) == 5


@pytest.mark.parametrize("failed_index", range(5))
def test_failure_stops_downstream_steps(monkeypatch, failed_index, caplog):
    run = Mock(side_effect=[None] * failed_index + [subprocess.CalledProcessError(7, "script")])
    monkeypatch.setattr(run_pipeline.subprocess, "run", run)
    with caplog.at_level(logging.INFO), pytest.raises(SystemExit) as exc:
        run_pipeline.main()
    assert exc.value.code == 7
    assert run.call_count == failed_index + 1
    assert "FAIL" in caplog.text
    assert "duration=" in caplog.text
    assert "Pipeline completed successfully" not in caplog.text


def test_failed_process_launch(monkeypatch):
    monkeypatch.setattr(run_pipeline.subprocess, "run", Mock(side_effect=OSError("cannot launch")))
    with pytest.raises(SystemExit) as exc:
        run_pipeline.main()
    assert exc.value.code == 1


def test_runner_preserves_child_output_and_exit_status(tmp_path):
    success = tmp_path / "success.py"
    success.write_text("print('child output')\n")
    failure = tmp_path / "failure.py"
    failure.write_text("raise SystemExit(9)\n")
    run_pipeline.run_step("test success", success)
    with pytest.raises(SystemExit) as exc:
        run_pipeline.run_step("test failure", failure)
    assert exc.value.code == 9
