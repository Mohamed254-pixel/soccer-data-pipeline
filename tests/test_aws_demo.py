"""Offline checks for the separate demo artifacts."""
import json
import os
from pathlib import Path
import runpy
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "deploy/aws/demo"


def test_demo_template_matches_reviewed_generator():
    template = json.loads((DEMO / "infrastructure.json").read_text())
    assert template == runpy.run_path(str(DEMO / "generate-template.py"))["render"]()
    resources = template["Resources"]
    assert len(resources) == 14
    host = resources["AirflowHost"]["Properties"]
    assert host["InstanceType"] == "c7i-flex.large"
    assert host["InstanceInitiatedShutdownBehavior"] == "stop"
    assert host["BlockDeviceMappings"][0]["Ebs"] == {
        "VolumeSize": 20, "VolumeType": "gp3", "Encrypted": True, "DeleteOnTermination": True,
    }
    assert "SecurityGroupIngress" not in resources["HostSecurityGroup"]["Properties"]
    assert host["MetadataOptions"]["HttpTokens"] == "required"
    assert not any(item["Type"].startswith("AWS::RDS::") for item in resources.values())
    actions = resources["HostRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    assert {action for statement in actions for action in statement["Action"]} == {
        "s3:GetObject", "s3:PutObject", "secretsmanager:GetSecretValue"
    }


@pytest.mark.parametrize(("deadline", "stop"), [
    ("1800000100", False), ("1800000000", True), ("1799999999", True), ("", True), ("broken", True),
])
def test_shutdown_check_in_sandbox(tmp_path, deadline, stop):
    deadline_file = tmp_path / "deadline"
    if deadline:
        deadline_file.write_text(deadline)
    marker = tmp_path / "stop"
    for name, command in {
        "date": "printf '1800000000\\n'",
        "systemctl": 'printf "%s\\n" "$*" > "$STOP_MARKER"',
    }.items():
        tool = tmp_path / name
        tool.write_text(f"#!/bin/sh\n{command}\n")
        tool.chmod(0o755)
    subprocess.run(["bash", str(DEMO / "shutdown-check.sh"), str(deadline_file)], check=True,
                   env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "STOP_MARKER": str(marker)})
    assert marker.exists() is stop
    if stop:
        assert marker.read_text().strip() == "--no-block poweroff"


def test_demo_dag_has_the_same_tasks_and_disables_schedule():
    source = (ROOT / "dags/soccer_pipeline_dag.py").read_text()
    rendered = runpy.run_path(str(DEMO / "demo_dag.py"))["render"](source)
    assert rendered.replace('dag_id="premier_league_demo"', 'dag_id="premier_league_etl"').replace(
        "schedule=None", 'schedule="0 6 * * 1"'
    ) == source
    compile(rendered, "premier_league_demo.py", "exec")


def test_private_runtime_does_not_overwrite(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    runtime = runpy.run_path(str(DEMO / "runtime.py"))
    secrets = {key: f"{i:064x}" for i, key in enumerate(runtime["PASSWORDS"], start=1)}
    secrets.update(DEMO_FERNET_KEY=Fernet.generate_key().decode(), DEMO_FOOTBALL_TOKEN="fake-token")
    settings = {
        "DEMO_IMAGE": "premier-league-demo:012abcd",
        "DEMO_MYSQL_IMAGE": "mysql@sha256:" + "1" * 64,
        "DEMO_POSTGRES_IMAGE": "postgres@sha256:" + "2" * 64,
        "DEMO_RAW_BUCKET": "isolated-test-bucket",
        "DEMO_AWS_ACCOUNT_ID": "123456789012",
    }
    with pytest.raises(ValueError, match="verified AWS account"):
        runtime["validate"](secrets, {**settings, "DEMO_AWS_ACCOUNT_ID": "invalid"})
    folder = tmp_path / "demo"
    runtime["prepare"](folder, secrets, settings)
    assert folder.stat().st_mode & 0o777 == 0o700
    private_json = folder / "runtime.json"
    assert private_json.stat().st_mode & 0o777 == 0o600
    assert "DEMO_ROOT_PASSWORD" not in json.loads(private_json.read_text())
    with pytest.raises(FileExistsError):
        runtime["prepare"](folder, secrets, settings)

    def capture(args, *, env):
        assert args[1:5] == ["--host", "unix:///var/run/docker.sock", "compose", "--env-file"]
        assert "premier-league-aws-demo" in args
        assert env["DEMO_RAW_BUCKET"] == settings["DEMO_RAW_BUCKET"]
        assert "DB_HOST" not in env and "AWS_PROFILE" not in env
        return 0

    monkeypatch.setenv("DB_HOST", "production")
    monkeypatch.setenv("AWS_PROFILE", "production")
    monkeypatch.setattr(subprocess, "call", capture)
    assert runtime["run_compose"](folder, ["config", "--quiet"]) == 0
