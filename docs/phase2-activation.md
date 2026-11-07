# Phase 2 activation investigation

**Current status:** this is a dated investigation. See the [final activation preflight](phase2-activation-status.md) for current access, backup, migration rehearsals and approval gates. PRs #6 and #7 are merged; application activation remains pending.

Follow-up to review commit `bc493b9`, 4 November 2026 (Pacific time), on `feature/phase2-incremental-etl`. This report supersedes the earlier review's JWT/configuration blocker. PR [#6](https://github.com/Mohamed254-pixel/premier-league-data-pipeline/pull/6) remains subject to owner approval and must not be merged automatically.

## API access: blocked by the account plan

Four read-only requests were made with the existing key, with no retries, data staging, or database writes:

| Request | HTTP result | Provider result |
| --- | --- | --- |
| `/status` | 200 | Active **Free** subscription, daily limit 100; usage reported as 0 before probes |
| `/leagues?id=39&season=2026` | 200 | `errors.plan`; Free plan excludes this season, allowed range 2022–2024 |
| `/fixtures?league=39&season=2026&date=2026-11-01&timezone=UTC` | 200 | Same `errors.plan` season restriction |
| `/leagues?id=39&season=2024` | 200 | One Premier League result with season 2024, no API errors |

These requests confirm that authentication works and league 39 is correct. The integration correctly uses `https://v3.football.api-sports.io/` with the key in the `x-apisports-key` header, not a URL query string. Season values are starting years: **2026 means 2026–27**. The problem is provider entitlement, not a typo, wrong host/header, expired key, HTTP authentication rejection, or exhausted quota. HTTP 200 is not success when the JSON contains `errors`.

The provider's [official league guide](https://www.api-football.com/news/post/how-to-get-all-data-from-a-league-with-api-football) confirms league 39, starting-year seasons, and the Free-plan window of Year−4 through Year−2 (2022–2024 in 2026). Its [pricing page](https://www.api-football.com/pricing) states that Free plans have season limitations. These are time-dependent restrictions; recheck the actual account response before activation.

The existing subscription **cannot currently supply 2026–27**. Available solutions:

- Keep the Free subscription and leave Phase 2 ingestion inactive while using mocks and the preserved archive for development. Do not change the pipeline to refresh the protected 2024 season.
- Ask API-SPORTS support through the account dashboard to confirm entitlement/2026 availability if the account should already have paid access. No support message was sent.
- If the owner chooses, purchase/activate an appropriate plan with explicit approval, then repeat the same read-only access checks. Confirm fixture and team endpoints for league 39/season 2026 before approving ingestion. No purchase, upgrade, key replacement, alternate account, or restriction bypass was attempted.

The readiness tool now reports only known public subscription-plan labels on failures. It never echoes raw provider error strings or arbitrary account text. It still fails before fixture probes when the league request is denied. No fallback treats an API denial as an empty valid season.

## Private configuration and environment verification

- Generated a fresh independent 48-byte random JWT secret (`secrets.token_urlsafe(48)`) in the **existing private runtime `.env`**, outside this worktree. The secret was never printed and is not part of a commit.
- Preserved all other environment values, including the existing API key and Fernet key. The private file is gitignored in its checkout and has mode `0600`.
- Verified Fernet construction plus an in-memory encryption/decryption round trip. This verifies the configured key works cryptographically; it is not a claim that stored Airflow encrypted values were read or that the key was rotated.
- Verified JWT shape and that it differs from both API and Fernet keys. Added regression tests so readiness rejects reused credential values.
- Private runtime `docker compose config --quiet` now **passes**. The example configuration also passes with temporary in-memory keys. Neither command starts services. Use an explicit private environment file and matching `ENV_FILE_PATH` when operating from this worktree; it has no committed/local copy of those secrets.
- Docker CLI/Compose are installed, but the daemon remains **stopped**. Container startup, Mac-host MySQL access from containers, image build, Airflow task execution, worker health, and existing volume identity still require operational verification after approval.
- Read-only application checks connected successfully and compared every original match/team/venue value with the archive. Counts remain **380 matches / 380 unique fixture IDs; 20 teams / 20 unique team IDs; 20 venues / 20 unique venue IDs**. Migration 003 schema/archive preflight passes; metadata is absent and Phase 2 remains disabled. No migration, checkpoint, or fixture write occurred.

## Automated verification

On this Mac, Python 3.13.5 offline tests: **211 passed, 17 skipped** (explicit test-server opt-in required). Full suite on a separate socket-only MySQL 9.3.0 server: **228 passed**, with API responses mocked and no application credentials. The disposable tests exercise migrations without applying them to the application server.

The actual Airflow 3.3.1 import check passed, including all five dependencies, Monday 06:00 UTC scheduling, two retries with five-minute delay, one-hour timeouts, catchup false, and one active run. Private/example Compose configuration, compilation, dependency consistency, and credential scans were checked separately. Python 3.11, MySQL 8.0, and Airflow import jobs run in [PR CI](https://github.com/Mohamed254-pixel/premier-league-data-pipeline/pull/6/checks); require the latest commit's checks to pass before merging.

Changes in this follow-up are limited to readiness diagnostics/tests and documentation. No SQL migration, DAG, extraction/loading strategy, archive dataset, database schema, or Phase 3 feature changed.

## Backup and restore verification procedure — prepared, not executed

No application backup/restore was run in this follow-up. Use this procedure before requesting approval to migrate. A successful test migration on synthetic/disposable data is not proof that an application backup restores.

1. Identify the actual application database, MySQL server version, private admin environment, and **existing Compose project name/volumes**. Arrange a maintenance window with all writers stopped and the DAG paused. Do not start services merely to pause a stack that is already stopped. Confirm all source tables use InnoDB and preserve the trusted CSVs. Inspect any unexpected tables/views/routines before choosing dump options.
2. Configure a private MySQL login path interactively (`mysql_config_editor set --login-path=pl_backup --host=localhost --user=YOUR_BACKUP_USER --password`). Do not put passwords on command lines or into Git. The login path and backup belong outside the repository. Use a restricted account with sufficient backup permissions.
3. In a private shell, choose a new timestamped filename in a restricted backup directory. For the current InnoDB application database, an example dump is:

   ```bash
   umask 077
   mysqldump --login-path=pl_backup --single-transaction --skip-lock-tables \
     --no-tablespaces --set-gtid-purged=OFF soccer_db \
     > /private/path/phase2-before-TIMESTAMP.sql
   ```

   Replace the example database/path with verified names; use a new file, not an existing backup. Require exit status zero, nonempty output, owner-only permissions, and a SHA-256 checksum (`shasum -a 256 /private/path/phase2-before-TIMESTAMP.sql`). Retain the server version and read-only baseline report. A partial dump must not be used. The example covers the current application tables; if additional routines/events are present, design and verify their backup explicitly before proceeding.
4. Prepare a **separate disposable MySQL server** compatible with the source version. Require a unique explicit socket, networking disabled (`--skip-networking` and `--mysqlx=OFF`), and a fresh isolated data directory. Confirm its socket/PID/datadir are different from the application server. This restore is permitted only on that isolated server, never on the application connection. Do not use a default socket/host.
5. Inspect the dump's database-selection statements/qualified references and ensure they can affect only this isolated server. On its unique socket, create a fresh empty restore database, then import. Example commands (after replacing socket and paths):

   ```bash
   mysql --no-defaults --socket=/private/path/isolated/mysql.sock -u root \
     -e 'CREATE DATABASE phase2_restore_check'
   mysql --no-defaults --socket=/private/path/isolated/mysql.sock -u root \
     --database=phase2_restore_check < /private/path/phase2-before-TIMESTAMP.sql
   ```

   Require successful exit codes. A socket-only disposable server may use a local test root account; application credentials must not be copied into it. Never restore over the source database or use any application socket in these commands.
6. Point the read-only verifier at **only the restore connection** in memory. From the repository root with the virtual environment active, replace the isolated socket and run:

   ```bash
   PYTHONPATH=scripts python - <<'PY'
   import json
   import mysql.connector
   import check_readiness
   check_readiness.get_connection = lambda: mysql.connector.connect(
       unix_socket='/private/path/isolated/mysql.sock', user='root',
       database='phase2_restore_check')
   print(json.dumps(check_readiness.check_database(), default=str, indent=2))
   PY
   ```

   Require exact archive equality, the 380/20/20 distinct counts, and migration preflight success. Compare restored `SHOW CREATE TABLE` definitions with source definitions, including fixture PK/unique keys, foreign keys, engines, types, and collation. Record checksum, test outcomes, and private backup location. Keep the backup; shut down only the isolated server when finished. No application rollback or deletion is part of this procedure.

## Remaining approval gates and activation order

1. Resolve 2026 API entitlement with the owner/provider. No purchase is authorized. Repeat limited read-only probes and confirm both fixtures and teams, plus adequate quota. Keep `FOOTBALL_SEASONS=2026`; do not refresh the protected archive to work around access limits.
2. Review/approve merging PR #6 separately. Keep the verified private environment available, preserve the Fernet key and existing Docker volumes/project identity, and verify private Airflow admin credentials before hosting. The existing Compose stack retains local-development metadata credentials and is not a hardened public deployment.
3. Complete the backup/restore procedure and record read-only source integrity/preflight. Obtain **explicit approval for migration 003** before running `PIPELINE_ENV_FILE=/private/path/admin.env python scripts/migrate_phase2.py --apply`. Use the reviewed commit and a separate administrator account. Recheck archive equality and schema afterward. Follow guarded resume/recovery if interrupted; do not bypass drift checks or delete records.
4. Obtain **explicit approval for service startup**, then start Docker Desktop/build/init the existing Airflow stack with the established Compose project and private configuration. Keep the DAG paused. Verify imports, health, volumes, and `host.docker.internal` database connectivity without triggering ETL.
5. Obtain **explicit approval for live ingestion**. Execute one supervised five-stage run using the restricted application account, verify 2024 values unchanged, new 2026 fixtures/statuses/memberships, unique IDs, validation success, and checkpoint advancement. Inspect a supported rerun for idempotency. Do not call activation successful before these checks actually run.
6. After the supervised run is accepted, rerun read-only readiness and unpause the Monday 06:00 UTC schedule. Inspect the first scheduled run. Until then, the pipeline remains unactivated. No Phase 3 work is included.
