# Phase 2 scheduling activation and completion

Verified **7 November 2026 UTC** (6 November Pacific). Approval explicitly
covered enabling `premier_league_etl`, including at most one immediate scheduled
incremental run. Phase 2 is operational on the existing Mac; no cloud services
or Phase 3 components were introduced.

## Code and automated verification

- PR #8 was merged normally into `main` at
  `381747c8b13d87939fcb643a0a805c6a20125704`; the original local main checkout
  was synchronized and clean before activation.
- [Merged-main GitHub Actions](https://github.com/Mohamed254-pixel/premier-league-data-pipeline/actions/runs/42340984140)
  succeeded. Python 3.11 unit tests reported 267 passed and 28 expected integration
  skips; the separate MySQL integration job passed all **295 tests**, without
  skips. The actual Airflow 3.3.1 import job also passed.
- A fresh import inside the running Airflow 3.3.1 scheduler verified all five
  dependencies, Monday 06:00 UTC, two five-minute retries, one-hour task
  timeouts, `catchup=False` and `max_active_runs=1`.
- Activation changed the saved DAG pause state through Airflow's CLI. It did
  not change application code, schema, credentials or historical data.

## Preflight and backups

The DAG was paused with no queued/running tasks, active DAG runs, broker work,
pipeline subprocesses or pending MySQL owner. All seven persistent containers
were healthy. Application credentials selected `soccer_db`, source
`football_data`, Premier League PL / competition 2021, season 2026.

Both seasons contained 380 fixtures. Original historical rows across all eight
pre-Phase-2 tables matched saved pre-bootstrap fingerprints. Migrations 003/004,
provider registries, constraints and archive CSV validation passed.

The existing complete 15-table backup was rehashed and its previous isolated
restore evidence checked:

```text
before-phase2-repeat-20261107T033744Z.sql
SHA-256: 26dfe63132387abf62f12d714ad3e2af613e5f36e0ac288993d8ed23545c77aa
```

That backup predates observation-only changes from the approved repeat, rather
than claiming to capture the exact activation-time state. Full activation-time
row fingerprints and checkpoints were saved privately. A fresh PostgreSQL
metadata dump was also saved before unpause; it is additional evidence, not a
claim of another successful restore test. Existing backups were retained.

## Controlled scheduler execution

The November 2 slot was an overdue timetable entry, not a queued DagRun.
Unpausing created exactly one scheduler-controlled run:

```text
scheduled__2026-11-02T06:00:00+00:00
Actual execution: 2026-11-07 05:08:58.787267 → 05:09:22.394577 UTC
```

Its logical date identifies the schedule slot. Extraction used the normal
checkpoint-based incremental window, not the historical logical date. No
manual trigger, historical backfill, history deletion or second run occurred.

| Task, in dependency order | Result | Attempts |
| --- | --- | ---: |
| `extract_matches` | Success | 1 |
| `extract_teams_and_venues` | Success | 1 |
| `load_teams_and_venues` | Success | 1 |
| `load_matches` | Success | 1 |
| `validate_data_quality` | Success | 1 |

Each task log contained start/success markers without failure markers. The final
task logged archive preservation and checkpoint commit. No automatic retry was
needed. Supervision was configured to pause scheduling on an unexpected run,
task failure/retry or failed verification; no such pause was necessary.

| Incremental outcome | Count |
| --- | ---: |
| Fixtures retrieved and verified against staging | 36 |
| Fixtures inserted | 0 |
| Fixtures with score/status/date/relationship changes | 0 |
| Fixtures with unchanged business values | 36 |
| Observation-only timestamp updates | 36 |
| Rejected fixtures | 0 |
| Duplicate fixtures / source-ID collisions | 0 / 0 |

The other 724 fixture rows were completely unchanged. Current memberships and
provider-specific identities matched the staged team response. All staged
fixture values matched MySQL exactly; relationships and source mappings passed.

## Final database and checkpoint state

| Data | Verified count |
| --- | ---: |
| Season-2024 fixtures | 380 unique |
| Season-2026 fixtures | 380 unique: 91 FT, 289 NS |
| Total fixtures / fixture mappings | 760 / 760 |
| Teams / team mappings | 40 / 40 |
| Historical teams / venues, original values preserved | 20 / 20 |
| Memberships | 20 per season, 40 total |
| Global venues | 20 |
| Application tables | 15 |

Every original historical row across all eight original tables remained intact.
Unrelated table rows and provider ID sets were unchanged. No AUTO_INCREMENT
counter was reset to force equality.

| Checkpoint field | Before | After, UTC |
| --- | --- | --- |
| `last_success_at` | `2026-11-07 03:44:12.781256` | `2026-11-07 05:09:02.750078` |
| `last_full_sync_at` | `2026-11-07 03:20:26.787877` | Unchanged |
| Pending run / observation / lease | Null | All null |
| Last completed run | Approved repeat | Scheduled run ID above |

The success value is the run's frozen source-observation timestamp. Monitoring
confirmed it remained unchanged after loading and before final validation.
Validation committed it successfully, then the task and DAG reached success.
No checkpoint was edited manually.

## Enabled schedule and operating limitations

- `premier_league_etl` is **unpaused**.
- Both `next_dagrun` and `next_dagrun_create_after` were verified as
  **Monday, 9 November 2026 at 06:00 UTC**—Sunday, 8 November at 22:00 PST.
- No additional catch-up run, queued/running task or queued broker work remained.
  Previous DAG history was preserved, including one old failed manual run;
  there were no newly failed runs or tasks.
- The five persistent Airflow services, PostgreSQL and Redis were healthy.
  `airflow-init` is a one-shot initialization service, not a sixth persistent
  Airflow service.
- A future Monday execution has not yet happened and is not claimed successful.

Keep the Mac powered on and awake with native MySQL, Docker Desktop and the
Airflow stack running. Restart policies do not prevent laptop sleep or provide
cloud availability. Local UI/metadata access settings need further hardening
before any public hosting. API outages, rate limits and subscription changes
can still interrupt runs; monitor failures and preserve staged batches.
Automated alerting, backup retention and AWS deployment remain future work.

## Checking future runs

Open [local Airflow](http://localhost:8080), select `premier_league_etl`, and check
the latest run's five task states and logs. For the existing Compose project:

```bash
export COMPOSE_PROJECT_NAME=soccer-data-pipeline
export AIRFLOW_PROJ_DIR=/Users/mohamedibrahim/Desktop/soccer-data-pipeline
export ENV_FILE_PATH="$AIRFLOW_PROJ_DIR/.env"
docker compose --env-file "$ENV_FILE_PATH" ps
docker compose --env-file "$ENV_FILE_PATH" exec airflow-scheduler airflow dags list-runs premier_league_etl
```

In MySQL Workbench, use the existing private application connection:

```sql
SELECT season, COUNT(*) AS fixtures, COUNT(DISTINCT fixture_id) AS unique_fixtures
FROM live_matches GROUP BY season;
SELECT season, status_short, COUNT(*) AS fixtures
FROM live_matches GROUP BY season, status_short;
SELECT * FROM season_sync_state;
SELECT enabled, pending_run_id, last_completed_run_id, last_completed_at
FROM pipeline_control;
```

On an unexpected run or validation failure, pause the DAG first:

```bash
docker compose --env-file "$ENV_FILE_PATH" exec airflow-scheduler airflow dags pause premier_league_etl
```

Pausing prevents further scheduling; it does not cancel an already running task.
Inspect its state before intervention. Preserve logs, staging and the run ID;
follow [guarded checkpoint recovery](phase2-migrations.md). Never manually advance
checkpoints, delete history, reset metadata or restore over live data to make a
check pass. Application writes and destructive recovery require explicit approval.

Sanitized evidence, fingerprints and the metadata backup are retained outside
Git under `pipeline-private/phase2-schedule-activation`. This documentation-only
follow-up records the completed activation. Publishing it does not change
runtime configuration or trigger another ingestion.
