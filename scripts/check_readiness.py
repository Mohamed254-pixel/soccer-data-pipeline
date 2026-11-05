"""Read-only deployment checks. Never claims a run, migrates, loads, or starts services.

--api makes small HTTP permission/coverage probes and consumes API quota.
--compose-example checks Compose syntax with throwaway keys, without any services.
"""

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess

from dotenv import load_dotenv
import mysql.connector
import requests

from db import get_connection
import incremental as etl
import migrate_phase2 as migration
from season_store import assert_historical_snapshot


ROOT = Path(__file__).resolve().parents[1]


def check_secrets(values):
    jwt = values.get("AIRFLOW__API_AUTH__JWT_SECRET", "")
    jwt_ok = (len(jwt) >= 32 and not jwt.startswith(("replace_", "your_"))
              and jwt not in {"airflow_jwt_secret", values.get("FERNET_KEY"), values.get("API_KEY")})
    try:
        fernet_ok = len(base64.b64decode(values.get("FERNET_KEY", ""), altchars=b"-_", validate=True)) == 32
    except (ValueError, TypeError):
        fernet_ok = False
    return {"jwt_secret_ready": jwt_ok, "fernet_key_ready": fernet_ok}


def check_database():
    connection = get_connection()
    cursor = None
    try:
        connection.start_transaction(readonly=True)
        cursor = connection.cursor(dictionary=True)
        metadata = "season" in migration.column_names(cursor)
        assert_historical_snapshot(cursor, ROOT, metadata=metadata)
        counts = {}
        for table, key in [("live_matches", "fixture_id"), ("teams", "api_team_id"), ("venues", "venue_id")]:
            cursor.execute(f"SELECT COUNT(*) AS total,COUNT(DISTINCT {key}) AS unique_ids FROM {table}")
            counts[table] = cursor.fetchone()
        migration.preflight(cursor)
        enabled = False
        pending = False
        if metadata:
            migration.validate_schema(cursor, metadata=True, complete=True)
            cursor.execute("SELECT enabled,pending_run_id FROM pipeline_control WHERE control_id=1")
            row = cursor.fetchone()
            enabled = bool(row and row["enabled"])
            pending = bool(row and row["pending_run_id"])
        return {"connected": True, "archive_matches": True, "counts": counts,
                "migration_003_applied": metadata, "pipeline_enabled": enabled, "pending_run": pending}
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            try:
                connection.rollback()
            finally:
                connection.close()


def check_api(seasons):
    status = etl.request_payload("status", {}).get("response")
    if (not isinstance(status, dict) or not isinstance(status.get("subscription"), dict)
            or status["subscription"].get("active") is not True):
        raise RuntimeError("API subscription is inactive or could not be verified.")
    usage = status.get("requests", {})
    if not isinstance(usage, dict):
        raise RuntimeError("API quota could not be verified.")
    current = etl.integer(usage.get("current"), "API quota usage")
    limit = etl.integer(usage.get("limit_day"), "API daily quota", 1)
    remaining = limit - current
    if remaining < 6 * len(seasons):
        raise RuntimeError("Insufficient remaining API quota for the read-only season probes.")
    verified = []
    # Emit only known public plan labels, never arbitrary provider/account text.
    plan = status["subscription"].get("plan")
    plan = plan if isinstance(plan, str) and plan in {"Free", "Pro", "Ultra", "Mega", "Custom"} else "unreported"
    details = {"subscription_active": True, "subscription_plan": plan,
               "quota_remaining_before_probes": remaining, "verified_seasons": verified}
    for season in seasons:
        try:
            leagues = etl.request_api("leagues", {"id": 39, "season": season})
            if not any(row.get("league", {}).get("id") == 39 and
                       any(item.get("year") == season for item in row.get("seasons", [])) for row in leagues):
                raise RuntimeError("Requested Premier League season is not available from the API.")
            # One sample tests endpoint entitlement, not a refresh. No payload
            # is staged and no run-owner/checkpoint operation is called.
            sample = etl.request_api("fixtures", {"league": 39, "season": season, "next": 1, "timezone": "UTC"})
            if not sample:
                raise RuntimeError("Fixture probe returned no sample; data availability is unconfirmed.")
            for fixture in sample:
                etl.parse_fixture(fixture, season)
            verified.append(season)
        except (requests.RequestException, ValueError, RuntimeError, KeyError, TypeError) as exc:
            exc.readiness_details = details
            raise
    return details


def check_docker():
    try:
        result = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True, timeout=15)
        return {"daemon_running": result.returncode == 0}
    except (OSError, subprocess.TimeoutExpired):
        return {"daemon_running": False}


def check_compose(env_file, example=False):
    env = {**os.environ, "ENV_FILE_PATH": str(env_file), "AIRFLOW_UID": os.getenv("AIRFLOW_UID", "50000")}
    if example:
        env.update(FERNET_KEY=base64.urlsafe_b64encode(os.urandom(32)).decode(),
                   AIRFLOW__API_AUTH__JWT_SECRET=secrets.token_urlsafe(48))
    try:
        result = subprocess.run(["docker", "compose", "--env-file", str(env_file), "config", "--quiet"],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def check_services(env_file):
    """Read health metadata only; never create or start a container."""
    expected = {"postgres", "redis", "airflow-apiserver", "airflow-scheduler",
                "airflow-dag-processor", "airflow-worker", "airflow-triggerer"}
    env = {**os.environ, "ENV_FILE_PATH": str(env_file)}
    try:
        result = subprocess.run(["docker", "compose", "--env-file", str(env_file), "ps", "--all", "--format", "json"],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)
        if result.returncode:
            return {"checked": False, "all_healthy": False}
        output = result.stdout.strip()
        rows = json.loads(output) if output.startswith("[") else [json.loads(line) for line in output.splitlines()]
        healthy = {row["Service"] for row in rows if row.get("State") == "running" and row.get("Health") == "healthy"}
        return {"checked": True, "all_healthy": expected <= healthy, "healthy_services": sorted(expected & healthy)}
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError):
        return {"checked": False, "all_healthy": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--api", action="store_true")
    parser.add_argument("--compose-example", action="store_true")
    args = parser.parse_args()
    if args.compose_example:
        valid = check_compose(ROOT / ".env.example", example=True)
        print(json.dumps({"compose_example_valid": valid, "production_services_started": False}))
        return 0 if valid else 1
    os.environ["PIPELINE_ENV_FILE"] = str(args.env_file)
    load_dotenv(args.env_file)
    report = {"environment_file_present": args.env_file.is_file(), **check_secrets(os.environ)}
    report["api_key_configured"] = bool(os.getenv("API_KEY"))
    report["docker"] = check_docker()
    report["compose_runtime_config_valid"] = check_compose(args.env_file)
    report["airflow_services"] = (check_services(args.env_file) if report["docker"]["daemon_running"]
                                  and report["compose_runtime_config_valid"] else {"checked": False, "all_healthy": False})
    try:
        report["database"] = check_database()
    except (mysql.connector.Error, ValueError, RuntimeError, OSError) as exc:
        report["database"] = {"ready": False, "error_type": type(exc).__name__}
    if args.api:
        try:
            seasons = sorted({etl.integer(value.strip(), "season", 2000, maximum=2100)
                              for value in os.getenv("FOOTBALL_SEASONS", "2026").split(",")})
            if 2024 in seasons or os.getenv("FOOTBALL_LEAGUE_ID", "39") != "39":
                raise ValueError("Invalid refresh season or league configuration.")
            report["api"] = check_api(seasons)
        except (requests.RequestException, ValueError, RuntimeError, KeyError, TypeError) as exc:
            # Never print HTTP response bodies, account records, or key values.
            report["api"] = {**getattr(exc, "readiness_details", {}), "ready": False, "error_type": type(exc).__name__}
            if isinstance(exc, etl.APIResponseError):
                report["api"]["reason"] = exc.category
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                report["api"]["http_status"] = exc.response.status_code
    else:
        report["api"] = {"checked": False}
    report["production_services_started"] = False
    report["live_ingestion_run"] = False
    print(json.dumps(report, indent=2, default=str))
    database = report.get("database", {})
    ready = all(report[key] for key in ("environment_file_present", "jwt_secret_ready", "fernet_key_ready", "compose_runtime_config_valid"))
    ready = ready and report["docker"]["daemon_running"] and database.get("pipeline_enabled") and not database.get("pending_run")
    ready = ready and report["airflow_services"]["all_healthy"]
    ready = ready and bool(report["api"].get("verified_seasons"))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
