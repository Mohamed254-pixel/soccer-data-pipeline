# Phase 2 — migration, activation, and recovery

See the [preflight and approval scope](phase2-activation-status.md) and the [successful application migration results](phase2-migration-results.md). football-data.org requires **003 followed by 004**; both are now applied to the existing application database. The [source-registry guide](football-data-source.md) describes 004. Do not reinitialize the database or run migrations automatically during ETL/service startup.

## Scope and preflight

Migration 003 upgrades the existing Phase 1 database. It never drops the original three tables or deletes fixture rows. The original `sql/schema.sql` and migrations 001/002 remain unchanged. Do not reapply old migrations to an already migrated database.

Before changing a database, pause the DAG, stop other pipeline writers, and take a verified backup outside the repository. Use a separate administrator account/environment file; the application account does not need DDL permissions. Avoid passwords in shell arguments, screenshots, or committed files. For example, configure a private MySQL login path and use `mysqldump --login-path=your_admin_login --single-transaction soccer_db > /private/path/before-phase2.sql`.

Run the read-only preflight:

```bash
PIPELINE_ENV_FILE=/private/path/admin.env python scripts/migrate_phase2.py
```

Initial migration requires the verified 2024-only snapshot: all 380 fixture/date/team/score tuples must match the committed CSV, and the original 20 team/venue rows and complete starting counts must match. A mismatch fails before DDL. The script never guesses that every arbitrary existing row belongs to 2024.

## Apply

Review `sql/migrations/003_incremental_etl.up.sql`, then:

```bash
PIPELINE_ENV_FILE=/private/path/admin.env python scripts/migrate_phase2.py --apply
```

The named SQL steps:

1. Create `season_teams`, `season_sync_state`, and `pipeline_control`, with Phase 2 disabled initially.
2. Add nullable season/status/source-ID/observation metadata to matches, a season/status/date index, and membership foreign keys. Widen `match_date` to nullable DATETIME(6) to retain unknown/fractional kickoff timestamps; original dates remain unchanged.
3. Snapshot the verified historical memberships and team/venue descriptions.
4. Backfill only the verified legacy dataset with season 2024, finished status, and team source IDs. All original six fixture fields remain unchanged.
5. Verify all metadata was backfilled and historical values still match, then set the database control's `enabled=TRUE`. This does not start ETL, unpause Airflow, or authorize ingestion.

Each named up step can be resumed. The match metadata ALTER is one atomic statement; on a retry it is skipped only when the full expected metadata column set is present. Incomplete/unexpected column sets fail for inspection. Reapplying an already enabled migration verifies the protected snapshot and performs no further writes.

Apply and rollback hold a database-scoped advisory lock, preventing two migration commands from racing. Preflight/reapply validate InnoDB engines, column types, supporting primary keys, foreign keys, and the season/status/date index. Drift fails for inspection rather than being silently repaired. The SQL template's `__ARCHIVE_FIXTURE_IDS__` is bound to parameters from the verified CSV by the Python runner; do not substitute arbitrary IDs or execute the template directly.

These safeguards require all ETL and external writers to remain stopped during migration. An advisory migration lock does not stop unrelated clients that ignore it. If an older draft of 003 has already been applied, including one without `pending_started_at`, the revised preflight deliberately rejects it. Review that schema and plan a separate approved repair; do not blindly replay DDL.

MySQL DDL commits implicitly. This is **not** a transaction wrapping the entire migration; `ROLLBACK` cannot undo prior ALTER/CREATE statements. Do not run the SQL file directly and bypass the Python guards. See [MySQL's atomic-DDL explanation](https://dev.mysql.com/doc/refman/8.0/en/atomic-ddl.html).

## Rollback before ingestion

Only before any incremental writes, and after separate rollback approval, the guarded down migration can restore the original schema. If 004 exists, roll it back first through `scripts/migrate_sources.py --rollback`; 003 refuses while the registry remains:

```bash
PIPELINE_ENV_FILE=/private/path/admin.env python scripts/migrate_phase2.py --rollback
```

It verifies the exact original snapshot and refuses if there are nonhistorical fixtures, new season memberships, changed canonical counts, sync checkpoints, or a pending run. It disables Phase 2, removes only the added metadata/constraints and the three migration-owned supporting tables, and verifies the original archive again. No original match/team/venue row is deleted. Original SQL schema files are not rewritten.

After ingestion, destructive rollback is deliberately refused. Pause the DAG and retain the additive schema and imported records. Do not drop new columns/tables or delete other seasons to make the guard pass. A separately designed export/restore is needed for a later structural rollback. The old Phase 1 fixed-380 validator is not appropriate for a mixed-season database.

An interrupted rollback can be resumed even when its metadata ALTER committed but supporting tables remain. The same snapshot/state guards must pass before cleanup continues. Test backup restoration separately before an approved application migration; passing disposable integration tests does not prove your application backup can be restored.

## Activate weekly updates

These are separate approval gates, not a single activation command:

1. Set `FOOTBALL_SEASONS=2026` and `FOOTBALL_SOURCE=football_data` in private runtime configuration for the approved provider. Keep its token separate from the original API-FOOTBALL key. Apply 003 and then 004 only after migration approval.
2. Confirm the API account has access to the requested league/season and sufficient quota. A key being present is not a coverage guarantee. No real refresh is needed to run the automated tests.
3. After service-start approval, bring up the existing Compose project with the DAG paused, preserving metadata and storage. Verify no queued work before starting scheduler/workers.
4. After first-ingestion approval, run `python run_pipeline.py` or trigger one supervised DAG run; inspect all five stages and season counts/statuses/checkpoints. Bootstrap the full available season, not just the readiness sample.
5. Obtain separate approval for a repeat write-capable run and verify idempotency, UPSERTs, mappings and the unchanged archive.
6. After scheduling approval, unpause `premier_league_etl` and verify its actual next execution. Scheduling remains Monday 06:00 UTC. The Mac must stay awake with MySQL, Docker Desktop, scheduler and workers running.

Original CSVs stay unchanged. Container validation reads the read-only archive mount separately from the existing named staging volume. The stage scripts perform no DDL, and no schema migration is triggered by an Airflow retry.

## Failed runs and concurrency

Extraction acquires a singleton database owner before API requests. The owner has a six-hour lease, renewed by write stages. Only a fresh extraction can replace an expired owner; every later write checks ownership, so a surviving old worker is fenced out. This lets a later scheduled run recover after a dead process without permanently blocking weekly updates. A currently running owner cannot be replaced before expiry. This design does not rely solely on Airflow's DAG concurrency limit.

After a transient failure, retry the original run ID to use the same frozen validated batch. Airflow retries do this automatically. Local execution:

```bash
PIPELINE_RUN_ID=the_original_run_id python run_pipeline.py
```

The claim binds the original observation timestamp in `pipeline_control.pending_started_at`, even if extraction fails before publishing a manifest. Retrying cannot change the meaning of that same observation. A filesystem lock serializes stage operations for one manifest in the shared Mac/Linux staging directory. Use the same staging storage when retrying; independent storage and uncoordinated external database writers are not supported.

If a batch is invalid or a run is abandoned, stop its workers before explicitly releasing it:

```bash
python scripts/incremental.py release-run the_original_run_id
```

Release requires the exact current owner ID. It does not delete records or advance a success checkpoint. Use a new run ID to refetch; do not edit a pending manifest. Records committed by a previous loader remain, and the unchanged checkpoint ensures overlap/reconciliation can refresh them safely.

Each loader has its own transaction. A final quality failure cannot undo already committed loads. Instead it prevents checkpoint advancement, retains the pending owner, and fails the run. Successful validation commits all requested season checkpoints and releases ownership together. If the process dies after that commit but before updating the manifest, validation retry recognizes the completed run ID.

## Integration-test isolation

The real MySQL tests seed fresh, randomly named `pl_test_...` databases, run migration up/down/resume and incremental scenarios, and clean up only those exact test databases. CI uses a disposable MySQL 8.0 service and a test-only password, with no application secrets. The normal offline suite skips these tests unless a test host/socket is explicitly configured. Locally, use a separate MySQL instance/socket rather than the application database.
