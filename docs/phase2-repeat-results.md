# Approved incremental repeat and publication readiness

**Subsequent approved steps:** PR #8 was merged as `381747c`; [weekly scheduling activation](phase2-scheduling-results.md) then succeeded, including one real scheduler-created run. The DAG is now enabled. The record below describes the earlier repeat-run and publication preparation.

Verified 7 November 2026 UTC (6 November Pacific). This was **one** separately
approved production repeat, using the existing five-stage runner inside the
worker container and the application account. It was not a full bootstrap,
Airflow DAG trigger, automatic retry or schedule activation.

Run ID: `phase2-repeat-20261107T034335Z`.

## Preflight

- Both seasons had 380 fixtures; global teams/venues were 40/20. Every fixture
  from the bootstrap still matched its frozen observation, and the archive passed
  the existing exact CSV validator.
- Source bindings, source-ID registries and migration constraints were valid.
  No run owner, active tasks, active DAG runs or queued broker work existed.
  All seven persistent services were healthy and `premier_league_etl` was paused.
- The existing success/full-sync checkpoint was
  `2026-11-07 03:20:26.787877` UTC. The normal 14-day overlap/future window was
  requested with `season=2026`, `dateFrom=2026-10-24`, `dateTo=2026-11-21`.
  The full-reconciliation flag remained false; no checkpoint was edited to force
  a particular extraction strategy.
- A new protected backup of all 15 tables and both seasons was restored on
  isolated MySQL 9.3.0. Every table's rows and definition matched. The application
  database remained unchanged during the backup/restore test.

Backup: `before-phase2-repeat-20261107T033744Z.sql`

SHA-256: `26dfe63132387abf62f12d714ad3e2af613e5f36e0ac288993d8ed23545c77aa`

## Actual results

All five stages succeeded; runner exit code **0**. The source was football-data.org
PL / 2021, season 2026. No second repeat was attempted.

| Outcome | Actual count |
| --- | ---: |
| Fixtures retrieved and revalidated | 36 |
| New fixtures inserted | 0 |
| Fixtures with changed business values | 0 |
| Fixtures with unchanged business values | 36 |
| Observation-only timestamp updates | 36 |
| Rejected fixtures | 0 |
| Duplicate fixtures or mapping collisions | 0 |

Dates, names, scores, statuses, season and team references remained identical for
all matched fixtures. Their `source_observed_at` values advanced to record the
new check. The other 724 fixture rows, including all 380 archived fixtures, were
identical in every column. Each stored matched row was also compared with the
exact new staged source tuple, not merely with before/after counts.

The UPSERT still executes and writes observation metadata on a matched fixture;
this is not a claim of zero SQL updates. No real source correction occurred in
this particular response. Postponements, corrections, stale observations and API
failures remain covered by the isolated tests rather than claimed as live events.

All 15 table row counts stayed unchanged from the bootstrap:

| Data | Count |
| --- | ---: |
| Season-2024 fixtures | 380 |
| Season-2026 fixtures | 380: 91 FT, 289 NS |
| Total fixtures / fixture source mappings | 760 / 760 |
| Teams / team source mappings | 40 / 40 |
| Memberships | 20 per season, 40 total |
| Venues | 20 |
| Source bindings / checkpoint rows | 2 / 1 |

All historical rows across the original eight tables were compared with their
pre-bootstrap fingerprints and remain intact. The original canonical team and
venue descriptions are unchanged. Source registry and canonical ID sets are
unchanged; current membership snapshots agree with the new source team response.
No table, account or privilege was created, dropped or reset. MySQL may consume
AUTO_INCREMENT values during duplicate-key insert attempts; counters are not
reset to force equality, and existing row IDs remain unchanged.

## Checkpoint verification

| Field | Before | After, UTC |
| --- | --- | --- |
| `last_success_at` | `2026-11-07 03:20:26.787877` | `2026-11-07 03:44:12.781256` |
| `last_full_sync_at` | `2026-11-07 03:20:26.787877` | Unchanged |
| Completed run | Bootstrap ID | `phase2-repeat-20261107T034335Z` |
| Pending owner / observation / lease | Null | All null |

The new success timestamp is the frozen observation time, committed only by the
successful final validation transaction. Full-sync time did not advance on an
incremental run. No checkpoint or owner was changed manually.

## Automated checks and local changes

- **295 tests passed, zero skipped**, 6.81 seconds, on isolated socket-only
  MySQL 9.3.0; API mocked. Production was not a disposable test target.
- Actual Airflow 3.3.1 import passed: five-task dependencies, UTC Monday 06:00,
  catchup disabled, two five-minute retries, one-hour timeout, one active run.
- The only ETL code change in the publication branch makes the runner's first
  two progress labels provider-neutral. Both live runs used the existing deployed
  `fde57c0` code; the label fix was tested locally and has not been deployed or
  used to perform another production run.
- Credentials, backups, environment files and full private run evidence remain
  outside Git. The publication diff retains the original datasets, schema,
  migrations, DAG, Compose and CI workflow.

Private evidence is retained under
`pipeline-private/phase2-repeat-20261107T034335Z`: full before/after comparisons,
one-attempt marker, redacted runner log, completed manifest and verification.

## Ready for review; scheduling still gated

The feature branch `feature/phase2-activation-preflight` is being prepared for
publication against `main` at `fde57c0`. Its commits document the independently
approved migrations, startup, bootstrap and production repeat, plus the small
logging correction. A PR title/body is prepared privately for review; no push,
PR creation or merge is authorized yet. Python 3.11/MySQL 8.0 GitHub Actions must
run on the future PR; no CI result for unpublished commits is claimed.

**Do not call Phase 2 fully complete yet.** The DAG stays paused and there is no
next scheduled execution to report. Enabling weekly scheduling requires separate
approval and checks for unintended immediate catch-up. No real Airflow DAG task
run is claimed from these supervised runner executions. The Mac must stay awake
with MySQL and Docker Desktop running. Automated alerting/backup retention and
cloud deployment remain future work; no Phase 3 technologies were introduced.
