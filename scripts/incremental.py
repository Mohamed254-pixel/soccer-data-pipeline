"""Five-stage incremental Premier League ETL with run-scoped staging.

The 2024 snapshot is protected. Season identifiers are starting years (2026 =
2026-27). MySQL schema changes are an explicit, separately reviewed operation.
"""

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from time import sleep

from dotenv import load_dotenv
import mysql.connector
import pandas as pd
import requests

from api_teams import parse_teams_and_venues
import season_store as store
import source_ids


ROOT = Path(__file__).resolve().parents[1]
FINISHED = {"FT", "AET", "PEN"}
STATUSES = {"TBD", "NS", "1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT",
            "FT", "AET", "PEN", "PST", "CANC", "ABD", "AWD", "WO", "LIVE"}
STAGES = ("extract_matches", "extract_teams_and_venues", "load_teams_and_venues",
          "load_matches", "validate_data_quality")


class APIResponseError(RuntimeError):
    """Safe category only: upstream error values may contain account secrets."""
    def __init__(self, category):
        self.category = category
        super().__init__(f"API-FOOTBALL rejected the request ({category}).")


def integer(value, name, minimum=0, nullable=False, maximum=4294967295):
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer.")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if not number.is_finite() or number != number.to_integral_value() or not minimum <= number <= maximum:
        raise ValueError(f"{name} is outside its allowed integer range.")
    return int(number)


def utc_datetime(value):
    if not isinstance(value, (str, datetime)):
        raise ValueError("A timestamp string or datetime is required.")
    try:
        parsed = pd.to_datetime(value, errors="raise", utc=True)
    except (ValueError, TypeError, OverflowError):
        # pandas errors can echo the source value. Never log untrusted payloads.
        raise ValueError("Invalid UTC timestamp.") from None
    if pd.isna(parsed):
        raise ValueError("A valid timestamp is required.")
    return parsed.to_pydatetime().replace(tzinfo=None)


def settings():
    load_dotenv(os.getenv("PIPELINE_ENV_FILE", ROOT / ".env"))
    provider = os.getenv("FOOTBALL_SOURCE", source_ids.API)
    if provider not in {source_ids.API, source_ids.FD}:
        raise ValueError("FOOTBALL_SOURCE must be api_football or football_data.")
    seasons = tuple(sorted({integer(x.strip(), "season", 2000, maximum=2100)
                            for x in os.getenv("FOOTBALL_SEASONS", "2026").split(",")}))
    if 2024 in seasons:
        raise ValueError("Season 2024 is a protected archive and cannot be refreshed.")
    league = integer(os.getenv("FOOTBALL_LEAGUE_ID", "39"), "league", 1)
    if league != 39:
        raise ValueError("This pipeline is scoped to Premier League league 39.")
    run_id = os.getenv("PIPELINE_RUN_ID")
    if not run_id:
        raise ValueError("PIPELINE_RUN_ID is required. Use run_pipeline.py or the Airflow DAG.")
    if len(run_id) > 250:
        raise ValueError("PIPELINE_RUN_ID must fit VARCHAR(250).")
    staging = Path(os.getenv("PIPELINE_STAGING_DIR", ROOT / "data/staging"))
    return {"seasons": list(seasons), "league": league, "run_id": run_id, "provider": provider,
            "path": staging / (hashlib.sha256(run_id.encode()).hexdigest() + ".json"),
            "overlap_days": integer(os.getenv("INCREMENTAL_OVERLAP_DAYS", "14"), "overlap days", 7, maximum=365),
            "reconcile_days": integer(os.getenv("FULL_RECONCILE_DAYS", "28"), "reconciliation days", 7, maximum=365)}


def request_payload(endpoint, params):
    """Bounded retries for transient transport/HTTP failures, never API errors."""
    key = os.getenv("API_KEY")
    if not key:
        raise RuntimeError("API_KEY is missing.")
    for attempt in range(3):
        try:
            response = requests.get("https://v3.football.api-sports.io/" + endpoint,
                                    headers={"x-apisports-key": key}, params=params, timeout=30)
            response.raise_for_status()
            break
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            failed_response = getattr(exc, "response", None)
            if isinstance(exc, requests.HTTPError) and (
                failed_response is None or failed_response.status_code not in {429, 500, 502, 503, 504}
            ):
                raise
            delay = retry_delay(attempt, failed_response)
            if attempt == 2 or delay is None:
                raise
            sleep(delay)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("API-FOOTBALL returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("API-FOOTBALL returned an error or an invalid response object.")
    errors = payload.get("errors")
    if errors:
        keys = set(errors) if isinstance(errors, dict) else set()
        category = "api_error"
        for names, label in [({"plan", "season", "subscription"}, "plan_or_season_access"),
                             ({"requests", "rateLimit"}, "quota_or_rate_limit"),
                             ({"token", "key", "apikey"}, "authentication")]:
            if keys.intersection(names):
                category = label
                break
        raise APIResponseError(category)
    return payload


def retry_delay(attempt, response):
    delay = 2 ** attempt
    if response is not None:
        value = response.headers.get("Retry-After")
        if value:
            try:
                delay = max(0, float(value))
            except (TypeError, ValueError):
                try:
                    date = parsedate_to_datetime(value)
                    delay = max(0, (date - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    pass
    # Longer provider waits are left to Airflow's five-minute task retry.
    return delay if delay <= 30 else None


def request_api(endpoint, params):
    payload = request_payload(endpoint, params)
    values = payload.get("response")
    if not isinstance(values, list):
        raise RuntimeError("API-FOOTBALL response must be a list.")
    if "results" in payload and payload["results"] != len(values):
        raise RuntimeError("API result count does not match the returned list.")
    paging = payload.get("paging")
    if paging is not None and (not isinstance(paging, dict) or paging.get("total") != 1 or paging.get("current") != 1):
        raise RuntimeError("Unexpected pagination. Refusing an incomplete API response.")
    return values


def parse_fixture(entry, season):
    try:
        fixture = entry["fixture"]
        league = entry["league"]
        teams = entry["teams"]
        goals = entry["goals"]
        status = fixture["status"]
        if integer(league["id"], "league", 1) != 39 or integer(league["season"], "season", 2000) != season:
            raise ValueError("Fixture belongs to a different league or season.")
        short = status["short"]
        if short not in STATUSES:
            raise ValueError("Unknown fixture status.")
        date = fixture["date"]
        if date is None and short not in {"TBD", "PST"}:
            raise ValueError("A kickoff date is required for this fixture status.")
        if date is not None:
            date = utc_datetime(date).isoformat()
        home = teams["home"]
        away = teams["away"]
        if not all(isinstance(team["name"], str) and team["name"].strip() for team in [home, away]):
            raise ValueError("Both team names are required.")
        home_id = integer(home["id"], "home team ID", 1)
        away_id = integer(away["id"], "away team ID", 1)
        if home_id == away_id:
            raise ValueError("A fixture must have two different teams.")
        home_goals = integer(goals["home"], "home goals", nullable=True, maximum=65535)
        away_goals = integer(goals["away"], "away goals", nullable=True, maximum=65535)
        if short in FINISHED and (home_goals is None or away_goals is None):
            raise ValueError("Finished fixtures require both scores.")
        long = status.get("long")
        if not isinstance(long, str) or not long.strip() or len(long) > 100:
            raise ValueError("Fixture status description is required and must fit VARCHAR(100).")
        if any(len(team["name"].strip()) > 100 for team in [home, away]):
            raise ValueError("Team names must fit VARCHAR(100).")
        return {"fixture_id": integer(fixture["id"], "fixture ID", 1, maximum=18446744073709551615),
                "match_date": date, "home_team": home["name"].strip(), "away_team": away["name"].strip(),
                "home_goals": home_goals, "away_goals": away_goals, "season": season,
                "status_short": short, "status_long": long,
                "elapsed": integer(status.get("elapsed"), "elapsed", nullable=True, maximum=65535),
                "home_api_team_id": home_id, "away_api_team_id": away_id}
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Fixture is missing required nested fields.") from exc


def plan_requests(season, state, pending, now, overlap_days=14, reconcile_days=28):
    last_full = state and state["last_full_sync_at"]
    full = not state or not last_full or now - last_full >= timedelta(days=reconcile_days)
    if full:
        return {"full": True, "requests": [{"league": 39, "season": season, "timezone": "UTC"}]}
    start = min(state["last_success_at"], now) - timedelta(days=overlap_days)
    requests = [{"league": 39, "season": season, "from": start.date().isoformat(),
                 "to": (now + timedelta(days=14)).date().isoformat(), "timezone": "UTC"}]
    ids = sorted({row["fixture_id"] for row in pending if row["season"] == season})
    requests.extend({"ids": "-".join(map(str, ids[index:index + 20])), "timezone": "UTC"}
                    for index in range(0, len(ids), 20))
    return {"full": False, "requests": requests}


def extract_batch(config, states, pending, now):
    plans, matches = {}, {}
    for season in config["seasons"]:
        plan = plan_requests(season, states[season], pending, now,
                             config["overlap_days"], config["reconcile_days"])
        plans[str(season)] = plan
        for params in plan["requests"]:
            values = request_api("fixtures", params)
            if plan["full"] and not values:
                raise ValueError("Empty bootstrap/reconciliation response. Check season access before retrying.")
            parsed = [parse_fixture(entry, season) for entry in values]
            ids = [row["fixture_id"] for row in parsed]
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate fixture IDs within one API response.")
            if plan["full"]:
                known = set((states[season] or {}).get("known_fixture_ids", []))
                if known.difference(ids):
                    raise ValueError("Full reconciliation omitted a known fixture. Check API completeness before retrying.")
            if "ids" in params and set(ids) != set(map(int, params["ids"].split("-"))):
                raise ValueError("ID lookup omitted or added fixtures. Refusing an incomplete batch.")
            # Later ID lookups are newer observations of live/moved fixtures.
            # Across seasons, the same ID must never acquire another identity.
            for row in parsed:
                old = matches.get(row["fixture_id"])
                if old and old["season"] != row["season"]:
                    raise ValueError("A fixture ID appeared in multiple seasons.")
                matches[row["fixture_id"]] = row
    return {"version": 2, "provider": source_ids.API, "run_id": config["run_id"], "league": config["league"],
            "seasons": config["seasons"], "started_at": now.isoformat(), "plans": plans,
            "matches": sorted(matches.values(), key=lambda row: row["fixture_id"]), "stage": "extract_matches"}


def save_manifest(config, manifest):
    path = config["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    # One complete batch replaces the previous manifest only after validation.
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(manifest, handle, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(path)


def read_manifest(config):
    manifest = json.loads(config["path"].read_text())
    if any(manifest.get(key) != config[key] for key in ("run_id", "league", "seasons")) or manifest.get("version") != 2:
        raise ValueError("Staging identity/configuration does not match this run.")
    if manifest.get("provider", source_ids.API) != config.get("provider", source_ids.API):
        raise ValueError("Staged provider differs from this run's source configuration.")
    if manifest.get("provider") == source_ids.FD:
        from football_data import validate_manifest
        validate_manifest(manifest)
    return manifest


@contextmanager
def stage_lock(config):
    """Serialize retries sharing a run manifest on macOS/Linux and Docker volumes."""
    import fcntl
    path = config["path"].with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def match_rows(matches, observed_at):
    rows, ids = [], set()
    for record in matches:
        # Validate serialized staging again, rather than trusting an edited file.
        entry = {"fixture": {"id": record["fixture_id"], "date": record["match_date"],
                             "status": {"short": record["status_short"], "long": record["status_long"], "elapsed": record["elapsed"]}},
                 "league": {"id": 39, "season": record["season"]},
                 "teams": {"home": {"id": record["home_api_team_id"], "name": record["home_team"]},
                           "away": {"id": record["away_api_team_id"], "name": record["away_team"]}},
                 "goals": {"home": record["home_goals"], "away": record["away_goals"]}}
        parsed = parse_fixture(entry, record["season"])
        if parsed["season"] == 2024 or parsed["fixture_id"] in ids:
            raise ValueError("Protected season or duplicate fixture ID in staging.")
        ids.add(parsed["fixture_id"])
        rows.append(tuple(utc_datetime(parsed[key]) if key == "match_date" and parsed[key] is not None
                          else parsed[key] for key in store.MATCH_COLUMNS[:-1]) + (observed_at,))
    return rows


def execute_stage(stage, config):
    with stage_lock(config):
        _execute_stage(stage, config)


def _execute_stage(stage, config):
    provider = config.get("provider", source_ids.API)
    if stage == "extract_matches":
        if config["path"].exists():
            # Airflow retries retain one frozen run observation, not a mixture of
            # old teams/committed rows and freshly refetched matches.
            read_manifest(config)
            print("Reusing this run's validated extraction batch.")
            return
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if provider == source_ids.FD:
            import football_data
            states, pending, started_at = store.extraction_state(config["seasons"], config["run_id"], started_at, provider)
            manifest = football_data.extract_batch(config, states, pending, started_at, football_data.Client())
        else:
            states, pending, started_at = store.extraction_state(config["seasons"], config["run_id"], started_at)
            manifest = extract_batch(config, states, pending, started_at)
        save_manifest(config, manifest)
        print(f"Staged {len(manifest['matches'])} fixtures for {config['seasons']}.")
        return
    manifest = read_manifest(config)
    started_at = utc_datetime(manifest["started_at"])
    stage_index = STAGES.index(stage)
    previous_index = STAGES.index(manifest["stage"])
    if previous_index < stage_index - 1:
        raise ValueError("A preceding stage has not completed.")
    if previous_index >= stage_index:
        print(f"Stage {stage} already completed for this run.")
        return
    if stage == "extract_teams_and_venues":
        batches = []
        if provider == source_ids.FD:
            import football_data
            client = football_data.Client()
        for season in config["seasons"]:
            if provider == source_ids.FD:
                batches.append(football_data.team_batch(client.request("competitions/PL/teams", {"season":season}),season))
                continue
            values = request_api("teams", {"league": 39, "season": season})
            teams, venues = parse_teams_and_venues({"response": values})
            if len(teams) != 20:
                raise ValueError("Premier League season extraction requires 20 unique teams.")
            batches.append({"season": season, "teams": json.loads(teams.to_json(orient="records")),
                            "venues": json.loads(venues.to_json(orient="records"))})
        memberships = {batch["season"]: {team["api_team_id"] for team in batch["teams"]} for batch in batches}
        if any(row[key] not in memberships[row["season"]] for row in manifest["matches"]
               for key in ("home_api_team_id", "away_api_team_id")):
            raise ValueError("Fixture team IDs do not belong to the extracted season membership.")
        manifest["team_batches"] = batches
    elif stage == "load_teams_and_venues":
        store.load_team_batches(manifest, manifest["team_batches"], started_at)
    elif stage == "load_matches":
        if any(row["season"] not in config["seasons"] for row in manifest["matches"]):
            raise ValueError("Staged fixture belongs to an unrequested season.")
        store.load_match_batch(manifest, match_rows(manifest["matches"], started_at), started_at)
    elif stage == "validate_data_quality":
        store.finish_run(manifest, started_at, ROOT)
    manifest["stage"] = stage
    save_manifest(config, manifest)


def main(stage=None):
    try:
        if stage is None and len(sys.argv) == 3 and sys.argv[1] == "release-run":
            load_dotenv(os.getenv("PIPELINE_ENV_FILE", ROOT / ".env"))
            store.release_run(sys.argv[2])
            return
        execute_stage(stage or sys.argv[1], settings())
    except mysql.connector.Error as exc:
        # Avoid connection diagnostics containing account details or SQL values.
        print(f"Database operation failed ({type(exc).__name__}, errno={exc.errno}). Check configuration/migration and task logs.", file=sys.stderr)
        raise SystemExit(1) from None
    except (ValueError, RuntimeError, OSError, KeyError, requests.RequestException) as exc:
        print(f"Pipeline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
