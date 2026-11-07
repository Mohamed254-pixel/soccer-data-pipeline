# Approved Phase 2 application migration results

**Subsequent approved step:** [staged Docker/Airflow startup](phase2-service-startup.md) succeeded. The migration record below predates that startup. First ingestion and scheduling remain pending.

Executed 7 November 2026 UTC (6 November Pacific), following explicit approval
for migrations 003 and 004 only. Code remained on local branch
`feature/phase2-activation-preflight`, based on verified main `fde57c0`.
No Docker/Airflow startup, ingestion, scheduling, push or merge was performed.

## Immediate preflight

The existing local MySQL 9.3.0 `soccer_db` was healthy and both administrator and
application authentication succeeded. Administrator permissions were sufficient;
no users, passwords or grants were changed. No pipeline writers, other active
InnoDB transactions, enabled events or triggers were found.

All eight tables' rows matched the saved pre-recovery baseline. Original schema
definitions matched except the already documented team AUTO_INCREMENT change
422 → 403. The value 403 was preserved. Backup checksums and successful restore
evidence were rechecked, including the fresh full eight-table backup described
in [the preflight](phase2-activation-status.md). No backup was overwritten/restored.

## Application results

| Stage | Tables | Verification |
| --- | ---: | --- |
| Before migration | 8 | Original rows, schema and backup readiness verified |
| After 003 | 11 | Schema/types/indexes and five FKs verified; exact archive preserved; 20 season-2024 memberships |
| After 004 | 15 | Schema/indexes, namespace CHECK constraints and eight FKs verified; source registry complete and ready |

003 added metadata and three support tables, classified the historical fixtures
as season 2024 / FT, and enabled the database ETL control. No success checkpoint
or pending run was created. Enabling this database control does not start ETL or
unpause Airflow.

004 added four registry tables, provider-scoped uniqueness and namespaced source
constraints. It registered 20 historical team IDs and 380 historical fixture IDs,
with raw IDs equal to their original canonical IDs and provider `api_football`.
The sole season/source binding is `2024 → api_football`. No football-data.org
records or season-2026 bindings were created.

After each migration, the administrator and application connections independently
verified the upgraded schema and original values. All original columns/rows in
the eight preexisting tables were fingerprinted before migration and compared
afterward. Unrelated table definitions also remained identical. Historical fixture
relationships passed the archive validator and database FKs; original IDs and
canonical team/venue descriptions remain unchanged.

| Data/state after 004 | Actual result |
| --- | ---: |
| Historical season-2024 fixtures | 380 |
| Season-2026 fixtures | 0 |
| Canonical teams | 20 |
| Venues | 20 |
| Historical season memberships | 20 |
| Team source mappings | 20 |
| Fixture source mappings | 380 |
| Checkpoint rows | 0 |
| Pending owner | None |
| Duplicate fixture IDs | None; primary-key/registry uniqueness verified |

Private evidence is retained outside Git in the timestamped
`phase2-migrations-20261107T023959Z` audit directory: original-column fingerprints,
preflight evidence, and separate 003/004 verification and application-access
reports. Credentials and raw SQL diagnostics are not included in this document.

## Executed regression checks

- Full suite: **295 passed, zero skipped**, Python 3.13, socket-only isolated
  MySQL 9.3.0, API mocked. The application database was not a test target.
- Actual Airflow 3.3.1 DAG import: passed, including all five tasks, dependencies,
  Monday 06:00 UTC, retries, timeouts and concurrency settings.
- Private Compose configuration: valid without starting Docker.
- Read-only deployment readiness: migrated schema, original data and registry
  passed. Overall exit status remains nonzero because Docker/services are stopped
  and the optional API probe was not repeated. This is not a failed migration.
- No application rollback, historical data correction, root recovery, credential
  rotation or privilege change was needed/performed.

No new GitHub Actions execution is claimed: no push was authorized. The existing
main commit's successful CI remains the result linked in the preflight record.

## Next activation gate: staged Docker/Airflow startup

This step is prepared, **not approved or performed**:

1. Revalidate private Fernet/JWT configuration and offline container restart
   policies before starting Docker Desktop. Preserve all named volumes.
2. Use existing Compose project `soccer-data-pipeline`, original PostgreSQL 16
   metadata volume, and reviewed source mounts. Start metadata/broker services
   first, leaving scheduler/workers stopped.
3. Query original metadata to confirm `premier_league_etl` is paused and no queued
   DAG/task/Celery work could execute. The saved pause report remains verified,
   but this fresh live check must precede worker/scheduler startup.
4. Inspect metadata version and backups. The approval must cover any necessary
   `airflow-init` metadata migration/user setup; never reset metadata or volumes.
5. Build/start the reviewed Airflow services, keeping the DAG paused. Verify the
   five persistent Airflow processes, PostgreSQL and Redis health, task imports,
   startup logs, and container-to-host application MySQL connectivity.

Stop for review on any unexpected state. Service-start approval must not be
interpreted as ingestion or scheduling approval. After healthy startup, request
separate approval for the supervised complete available-season bootstrap, then
another write-capable run for idempotency, and finally weekly scheduling.

There are no live season-2026 results or next scheduled execution to report yet.
The Mac will need to stay awake with MySQL and Docker running for weekly updates.
