# Phase 2 activation preflight

**Approved follow-up:** migrations 003/004, [service startup](phase2-service-startup.md), [real bootstrap](phase2-bootstrap-results.md), [incremental repeat](phase2-repeat-results.md) and [weekly scheduling activation](phase2-scheduling-results.md) have since succeeded. The DAG is enabled, and its first scheduler-created run passed all five tasks. The preflight record below describes the earlier state before those approved changes.

Verified 7 November 2026 UTC (6 November Pacific), against GitHub `main`
`fde57c074b85f6516929dd039bb33c9c505de94a`. Local preparation branch:
`feature/phase2-activation-preflight`. This record supersedes deployment-status
claims in the older engineering review and activation investigation.

**Phase 2 is implemented but not activated.** No application migrations, live
ingestion, Docker startup, or weekly scheduling were performed in this preflight.

## Executed checks

| Check | Result |
| --- | --- |
| Application MySQL | 9.3.0, `soccer_db`, local port 3306, normal networking, no recovery startup file |
| Administrator login | Passed using the protected external file; required migration privileges present |
| Application login | Passed; used for read-only archive checks and the logical backup |
| Archive | 380 fixtures, 20 teams, 20 venues; original values match the committed CSVs |
| Pre-recovery baseline | All rows in all eight tables match; seven definitions match exactly; only the documented team counter differs |
| Writers at preflight | No active write statements, other InnoDB transactions, local pipeline processes, enabled database events, or triggers found |
| Migration state | Neither 003 nor 004 applied; no current-season fixtures |
| Full automated suite | **295 passed, no skips**, Python 3.13 with isolated socket-only MySQL 9.3.0; API mocked |
| Actual Airflow 3.3.1 import | Passed; five tasks, dependencies, UTC cron, retries and timeouts verified |
| Private Compose/secrets | Valid; independent JWT passes; Fernet round-trip also passes through Airflow 3.3.1 `get_fernet()` |
| Read-only API probes | football-data.org fixture sample and team parsing succeeded for season 2026; nothing staged or loaded |
| Docker | Daemon stopped; no services started |
| GitHub Actions on existing main | Successful [Tests run](https://github.com/Mohamed254-pixel/premier-league-data-pipeline/actions/runs/41979111492); Python 3.11, MySQL 8.0 integration and Airflow import jobs |
| Security and protected files | Credential-value/pattern scans of tracked/new files and reachable text history pass; archive CSVs and original schema/migrations unchanged |

A future CI run on new commits remains unverified until a push is approved.

`teams.AUTO_INCREMENT` remains **403**, compared with 422 before recovery.
`SHOW CREATE TABLE` confirms 403. Cached `information_schema.TABLES` statistics
reported 402 with a 24-hour cache lifetime; this is not proof of a counter change.
Definitions match after removing only the counter option. No counter was altered.

### Backup and migration rehearsal

A fresh private logical backup was made using a consistent InnoDB snapshot,
restrictive permissions, no table locks, and no overwrite of earlier backups:

`before-phase2-activation-20261107T020936Z.sql`

SHA-256: `183322f95f226924bfdb7180d2979851d5abcc60ff102dcb36f9871ca3b818e7`

Its adjacent private `.verification.json` records restoration and comparison of
all eight tables' rows and `SHOW CREATE TABLE` definitions. Migrations 003 then
004 passed on that restored copy, producing fifteen tables. Historical values
and IDs stayed intact; unrelated tables were unchanged. The source was compared
before and after and remained unchanged. Earlier backup checksums and successful
restore evidence were verified too. The protected offline recovery backup was
retained, not restored or overwritten in this preflight.

The migrated copy passed both schema/registry validators, including its eight
foreign keys. It contains 20 historical memberships, 20 team source mappings,
380 fixture source mappings, one season/provider binding, no checkpoints and no
pending run. The existing application account has database-wide DML grants that
cover the new tables; no grants or users were changed. Saved pause evidence and
the logical/physical Airflow metadata backup checksums also remain valid.

| Existing table | Rows before activation |
| --- | ---: |
| `live_matches` | 380 |
| `live_matches_backup_20260725` | 1,140 |
| `live_matches_backup_20260821` | 380 |
| `matches` | 1,000 |
| `results` | 43,277 |
| `teams` | 20 |
| `teams_backup_20260821` | 42 |
| `venues` | 20 |

These are existing application objects; none are disposable test tables.

### Private recovery-helper fix

The helper assigned the `_mysql` operating-system account to a local variable
named `mysql`. A startup connection refusal then made `except mysql.connector.Error`
raise `AttributeError`, concealing the original error. The variable is now
`mysql_os_account`. Seven private regression tests exercise both actual retry
loops using mocked connections: retry temporary refusals, stop on authentication
errors, and respect retry bounds. They never invoke recovery. Helper, tests,
credentials and backups stay outside Git. **Do not rerun recovery or reset root.**

## Exact migration approval scope

Target: the existing local MySQL 9.3.0 `soccer_db`. Use the private administrator
connection only for DDL. Recheck backup checksums, stopped writers, exact archive
and schema immediately before application; stop on unexplained drift.

1. Apply guarded **003** using `scripts/migrate_phase2.py --apply`. It creates
   `season_teams`, `season_sync_state`, and `pipeline_control`; adds season/status,
   team-reference and observation metadata, an index and membership FKs; widens
   kickoff to nullable `DATETIME(6)`; seeds 20 historical memberships; and backfills
   only new metadata on the trusted 380 fixture IDs as season 2024 and finished.
   Original fixture fields, team/venue values and IDs remain intact. It sets
   `pipeline_control.enabled=TRUE` after verification. This is a database ETL gate,
   **not** permission to run ETL or unpause Airflow.
2. Verify 003 before continuing: eleven tables, exact archive, schema/types/indexes/FKs,
   20 historical memberships, enabled control with no pending run or checkpoint.
3. Apply guarded **004** using `scripts/migrate_sources.py --apply`. It creates
   `source_registry_state`, `season_sources`, `team_source_ids`, and
   `fixture_source_ids`; adds the team provider discriminator; replaces the team
   name/league unique key with one scoped by provider; and adds composite keys,
   FKs and CHECK constraints. It registers the original 20 team IDs and 380 fixture
   IDs as API-FOOTBALL and binds season 2024 before marking the registry ready.
4. Verify fifteen tables, original data, mappings, uniqueness/FKs, empty checkpoint
   and owner state, and application-account access. No season-2026 ingestion is
   included in this approval.

football-data.org canonical IDs are `2^31 + source_team_id` and
`2^63 + source_fixture_id`. API-FOOTBALL IDs remain unchanged. Never join raw IDs
across providers or convert canonical fixture IDs to floating point. Missing
stable venue IDs remain null; stadium text stays in season snapshots.

### Risks and rollback

DDL commits implicitly and can acquire metadata locks. This is not one
rollback-capable transaction. Keep writers stopped; inspect errors rather than
automatically restoring or dropping anything. Named guarded steps support
resuming interrupted up migrations after review.

Before ingestion only, a separately approved structural rollback runs **004 down
before 003 down**, through the Python `--rollback` guards. This removes
migration-owned additions only after verifying the archive and absence of new
source data, memberships, checkpoints or pending runs. After ingestion, retain
the additive schema; never delete data to force rollback guards. Restoring a
backup replaces data and needs a separate recovery plan and explicit approval.

## Remaining approval gates

1. **Application migrations 003 → 004**, scoped above.
2. **Docker/Airflow startup**, including any metadata upgrades/user setup from
   `airflow-init`. Preserve volumes and keys. Verify saved pause and no queued
   tasks before scheduler/worker startup.
3. **First supervised ingestion** using application credentials, football-data.org
   PL / competition 2021, season 2026, and the full available fixture bootstrap.
   Show coverage and target first; record actual retrieved, inserted, updated,
   skipped and rejected counts and validation results.
4. **Repeat write-capable run** for idempotency and archive verification.
5. **Weekly scheduling** after those checks pass. Unpause explicitly and verify
   the actual next run; do not claim a future scheduled run succeeded.

The saved original-metadata pause report identifies `premier_league_etl` and
confirms the pause was committed. Offline Docker inspection found the original
PostgreSQL 16 volume and only stopped audit/unrelated containers, with no saved
Airflow worker/scheduler containers. A fresh SQL check of pause/run state must
still precede scheduler startup; Docker remains stopped now.

Use Compose project **`soccer-data-pipeline`** to preserve
`soccer-data-pipeline_postgres-db-volume` and staging storage. A renamed checkout
or worktree can otherwise select different empty volumes. Point `AIRFLOW_PROJ_DIR`
at the reviewed checkout and `ENV_FILE_PATH` at the protected runtime file. Use
`docker compose config --quiet` rather than displaying expanded secrets. Readiness
must use the same project identity:

```bash
COMPOSE_PROJECT_NAME=soccer-data-pipeline \
python scripts/check_readiness.py --env-file /private/path/runtime.env --api
```

There are five persistent Airflow processes plus the one-shot `airflow-init`,
PostgreSQL and Redis. Readiness requires all seven persistent services healthy;
initialization is not a sixth running Airflow process. Container-to-host MySQL
access and real task execution remain unverified until approved startup.

## Read-only checks after approved ingestion

In MySQL Workbench, use an appropriate private connection. These queries require
the migrations to have completed:

```sql
SELECT season, COUNT(*) AS fixtures FROM live_matches GROUP BY season;
SELECT season, status_short, COUNT(*) AS fixtures
FROM live_matches GROUP BY season, status_short ORDER BY season, status_short;
SELECT season, COUNT(*) AS memberships FROM season_teams GROUP BY season;
SELECT fixture_id, COUNT(*) AS copies FROM live_matches
GROUP BY fixture_id HAVING COUNT(*) > 1;
SELECT provider, source_id, COUNT(*) AS copies FROM fixture_source_ids
GROUP BY provider, source_id HAVING COUNT(*) > 1;
SELECT COUNT(*) AS broken_memberships FROM live_matches m
LEFT JOIN season_teams h ON h.season=m.season AND h.api_team_id=m.home_api_team_id
LEFT JOIN season_teams a ON a.season=m.season AND a.api_team_id=m.away_api_team_id
WHERE h.api_team_id IS NULL OR a.api_team_id IS NULL;
SELECT * FROM season_sync_state;
SELECT enabled, pending_run_id, last_completed_at FROM pipeline_control;
```

Counts alone do not prove archive integrity: also execute the existing quality
stage's exact CSV comparison. For failed runs, inspect the five tasks and logs,
preserve staging and the run ID, then follow [guarded retry/release guidance](phase2-migrations.md).
Never advance checkpoints manually. Create backups under new protected names
and verify restores only on an isolated server, never on `soccer_db`.

The cron is Monday **06:00 UTC**, catchup disabled, two retries five minutes apart,
one-hour task timeouts and one active run. The next run has not been verified
because scheduling is disabled. The Mac must stay awake with MySQL and Docker
Desktop running. This is not an always-on cloud deployment. Alerts, automated
backup retention and cloud infrastructure remain future work.
