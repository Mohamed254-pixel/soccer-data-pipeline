# Phase 2 engineering review and activation runbook

Reviewed 4 November 2026 (Pacific time), on `feature/phase2-incremental-etl`, PR [#6](https://github.com/Mohamed254-pixel/premier-league-data-pipeline/pull/6). Review scope covered repository source, the complete PR changes, schemas/migrations, API and SQL boundaries, tests, DAG, Compose, CI, environment handling, and recovery documentation. No Phase 3 work is included.

## Findings and fixes

| Finding | Consequence | Fix and verification |
| --- | --- | --- |
| Full season reconciliation accepted a response omitting previously stored fixtures | Could advance reconciliation checkpoints despite an incomplete source response | Check all known IDs before staging; regression test rejects omissions |
| A retry before manifest publication could change a run's observation timestamp; same-run stages had no manifest lock | Recovery could mix the meaning of one run across retries or race manifest updates | Persist `pending_started_at` with the owner; reject changed observations; lock each manifest; unit and real MySQL recovery tests |
| Migration reapply trusted column names without validating types/keys | Drifted schemas could appear enabled/safe despite missing integrity constraints | Validate column types, InnoDB engines, support primary keys, foreign keys, and season index; test missing FK/PK and incorrect metadata type |
| Down migration stopped recovering after metadata removal, leaving supporting tables | A partially committed rollback could falsely report completion | Resume guarded cleanup of remaining migration-owned tables; real MySQL interruption test |
| Migration commands were not mutually exclusive | Two operators could race partially committed DDL | Database-scoped advisory lock; real MySQL two-connection test |
| Archive backfill did not explicitly bind the trusted fixture IDs | Guarded code relied on the preflight being the sole bound on the update | Parameterize the exact trusted archive ID list and update only unclassified rows; preserve six original fixture fields |
| No bounded in-process retries for transient HTTP failures, and no DB I/O timeouts | Short outages wasted task retries; blocked DB reads/writes could hang | Three transport/HTTP attempts; capped Retry-After/backoff; explicit connection/read/write timeouts; mock failure tests |
| Fixture season membership was checked only after a load-stage boundary | Invalid fixture/team combinations could be discovered after team writes committed | Verify staged fixture membership immediately after team extraction |
| Task cancellation could leave a child running; no task execution timeout | Orphan work could keep writing while Airflow retried | Terminate/wait/kill on cancellation; one-hour task limit; cancellation tests |
| Repeated local runner calls inherited a generated run ID | A fresh invocation in the same Python process could reuse a completed ID | Clean up generated IDs on success/failure while retaining explicit resume IDs |
| Compose allowed a known JWT fallback and missing Fernet configuration; UI ports bound publicly | Unsafe defaults could be used accidentally | Require private keys and bind UI/Flower to loopback; document remaining local-development defaults |
| Deployment readiness lacked a safe diagnostic command | A configured key or passing unit tests could be mistaken for a working deployment | Add read-only secret-shape, DB/archive, API entitlement/quota, Docker/Compose, and service-health checks |

The existing fixture-ID UPSERT, archive preservation, per-season snapshots, postponed-ID polling, overlap window, periodic reconciliation, transactional loaders, and checkpoint-after-quality design were retained. No original dataset, schema file, migration 001/002, or existing application database record was changed.

## Executed verification

| Check | Observed result |
| --- | --- |
| Initial offline baseline | 180 passed, 10 integration tests skipped |
| Final offline suite, local Python 3.13.5 | **207 passed, 17 skipped**; skips require a designated test server |
| Final full suite, local isolated MySQL 9.3.0 | **224 passed**, no skips, 4.83 seconds; API mocked |
| Actual Airflow 3.3.1 import | Passed through DagBag; five tasks and exact dependencies; Monday 06:00 UTC; catchup false; two retries/five minutes; one-hour task timeout; one active run |
| Compose syntax with disposable example keys | Passed; no daemon or services needed |
| Current private runtime Compose configuration | Failed as expected: required JWT secret is missing |
| Dependency consistency | `pip check` passed |
| Secrets | Private credential values/common credential patterns absent from tracked/new files and reachable text diffs; private environment not tracked; no secrets printed |
| Protected files | All three archive CSVs, `sql/schema.sql`, and migrations 001/002 byte-identical to main |

The 17 real MySQL tests cover migration up/down/reapply, partial-up and partial-down recovery, drift and mutual exclusion, inserts, corrections, nullable postponed fixtures, duplicate and alternate-key protection, transactional failures, checkpoint recovery, multi-season behavior, read-only diagnostics, and the five-stage flow with a mocked API. MySQL 8.0 and Python 3.11 are verified by the PR's CI jobs rather than claimed from this Mac's Python 3.13/MySQL 9.3 environment. CI additionally performs a real Airflow 3.3.1 import on Python 3.11. Check the current commit's [PR checks](https://github.com/Mohamed254-pixel/premier-league-data-pipeline/pull/6/checks) before merging.

## Application database integrity

Two read-only checks connected successfully to the existing application database and compared every original match/team/venue field with the trusted committed CSVs. Both found:

| Table | Rows | Distinct source IDs |
| --- | ---: | ---: |
| live_matches | 380 | 380 |
| teams | 20 | 20 |
| venues | 20 | 20 |

Migration 003 remains **unapplied**. There is no Phase 2 owner/checkpoint state in this database. Readiness checks used a read-only transaction and rollback. Tests modified only random databases on a separate socket-only disposable MySQL server with no application credentials. No application backup was created/restored, because no application migration or write was approved or performed. A verified backup is an activation prerequisite.

## Activation blockers and remaining limits

1. The private API key exists and `/status` reported an active subscription with quota remaining. The 2026 league access probe returned a provider plan/season-access error. **2026–27 access is not verified and activation is blocked.** No fixture ingestion was attempted. Do not infer that purchasing a specific plan will fix this without checking the provider's actual coverage.
2. Docker Desktop's daemon is stopped. No containers were started; running Airflow task results, container networking, image build, worker health, and real task execution remain unverified.
3. The existing Fernet key has valid shape, but the required independent JWT secret is absent. Runtime Compose configuration is blocked until this is configured privately. Retain the existing Fernet key; arbitrary rotation can make encrypted Airflow values unreadable.
4. Migration 003 requires explicit owner approval, stopped writers, an administrator account, and a restore-tested backup before application. Revision of an already applied draft 003 requires separate inspection/repair; the guarded migration deliberately refuses schema drift.
5. Compose retains the existing local-development Airflow/Postgres credentials and architecture. Loopback binding reduces exposure but does not turn this into a hardened public production deployment. Configure private admin credentials and suitable access controls before hosting outside the Mac.
6. Weekly refresh is not real-time scoring. Corrections outside the overlap wait for reconciliation (default 28 days). Missing *known* IDs are detected; an API response silently omitting only unknown fixtures cannot be proven complete from this API contract alone. Source coverage still requires operational checks.
7. Loads commit by stage. A final quality failure prevents checkpoints but does not undo earlier committed loads. Same-run retry/release and the six-hour fenced lease support recovery. Keep shared staging durable and do not manually edit pending batches. External writers must be controlled; the owner lock is an application convention, not a ban on all database access.
8. Staging retention and monitoring remain manual. Automated backup scheduling, alerting, infrastructure hardening, and Phase 3 services are outside this PR.

The code is eligible for merge review after all checks on the latest PR commit pass. It is **not ready for live activation** until the blockers and approval gates below are resolved. PR #6 must remain unmerged until owner approval.

## Exact safe activation sequence — requires approval

These are operator instructions, not actions already performed. Obtain explicit approval before applying migration 003, writing to the application database, ingesting fixtures, or starting production services.

1. Resolve API league-39/season-2026 access with the provider. Keep `FOOTBALL_SEASONS=2026`, sufficient quota for bootstrap/teams/retries, and the existing 2024 CSVs unchanged. Configure a private JWT secret (README generation command), retain the existing Fernet key, and choose private Airflow admin credentials. Use a private runtime environment file with restricted permissions. Do not print or commit it.
2. Approve/review PR #6 separately from deployment. For activation, use the reviewed commit and the **existing Compose project name and named volumes**. A renamed checkout can otherwise select new empty Airflow/staging volumes. Do not use `down -v` or remove volumes. Confirm Mac MySQL accepts the intended application connection from `host.docker.internal` once containers are approved to start.
3. Ensure the DAG is paused and all local/worker/external writers are stopped. Take a timestamped backup outside the repository with restrictive permissions, using a private login path rather than a password argument. Example: `umask 077` followed by `mysqldump --login-path=your_admin_login --single-transaction soccer_db > /private/path/before-phase2.sql`. Include any additional database objects your deployment uses. Restore into a separate isolated server and verify all 380 match tuples, 20 teams, 20 venues, and schema before proceeding. A dump file existing is not proof of recovery.
4. Run the read-only preflight using the approved administrator environment: `PIPELINE_ENV_FILE=/private/path/admin.env python scripts/migrate_phase2.py`. Record baseline counts/archive comparison and inspect any drift. Do not bypass a guard.
5. **After migration approval**, run `PIPELINE_ENV_FILE=/private/path/admin.env python scripts/migrate_phase2.py --apply`. Run preflight again, then `python scripts/check_readiness.py --env-file /private/path/runtime.env --api`. Check archive equality, original counts, enabled schema, empty pending run, and actual season access. The readiness command remains nonzero while Docker/services are stopped. MySQL DDL commits implicitly; follow the guarded resumable recovery instructions in [phase2-migrations.md](phase2-migrations.md) if interrupted. Down migration is allowed only before ingestion and only when all guards pass.
6. **After service-start approval**, start Docker Desktop. Validate private Compose configuration (`docker compose --env-file /private/path/runtime.env config --quiet` with matching `ENV_FILE_PATH` and the established project name), build the image, run `airflow-init`, and start the existing stack. Keep the DAG paused. Check `docker compose ps`, Airflow import errors, worker health, and Mac-host MySQL connectivity. Do not trigger ETL as a connectivity test.
7. **After live-ingestion approval**, use the restricted application account and run one manual DAG trigger (or one local `PIPELINE_ENV_FILE=/private/path/runtime.env python run_pipeline.py`, with Airflow still paused). Record the run ID. Verify all five stages succeeded, 2024 values still exactly match the archive, season-2026 fixtures/statuses/memberships are valid, IDs are unique, and checkpoints advanced only at validation. Rerun through the supported path to verify idempotency and inspect counts; do not assume an empty current season means success if API coverage is absent.
8. Run read-only readiness again with `--api`; require healthy services, valid configuration, enabled schema, no pending owner, and verified season access. Unpause `premier_league_etl` only after approval of the manual run. Confirm its next Monday 06:00 UTC schedule and inspect the first scheduled run and logs. Retain backup and run evidence outside Git.

Do not merge or activate automatically when tests pass. No AWS, Kafka, Spark, dbt, or other Phase 3 changes are part of this review.
