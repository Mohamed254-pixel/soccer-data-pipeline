# First approved 2026–27 bootstrap

**Subsequent approved verification:** [one normal incremental repeat](phase2-repeat-results.md) passed, preserving fixture counts and business values. Weekly scheduling remains disabled. The dated bootstrap record below describes the first run only.

Executed once on 7 November 2026 UTC (6 November Pacific), with explicit approval.
Run ID: `phase2-bootstrap-20261107T031951Z`.

The existing five-stage `run_pipeline.py` ran inside the deployed Airflow worker
container using the existing application account. The source was explicitly
`football_data`, Premier League PL / 2021, season 2026. No Airflow DAG run was
triggered, and `premier_league_etl` stayed paused. No second ingestion, scheduling,
push or merge was performed. Phase 2 remains incomplete until separately approved
production idempotency testing and weekly scheduling are verified.

## Preflight and backup

Read-only checks verified all seven persistent services healthy, the paused DAG,
zero active/queued tasks or DAG runs, an empty broker, no pending ETL owner, valid
003/004 schema/registry constraints, and the exact historical snapshot. Runtime
settings and unused run-scoped staging identity were checked in the container.

A missing container `ps` utility prevented the first process-inspection command.
No ingestion had started. A read-only Linux `/proc` inspection checked 23
processes and found no pipeline execution; host processes were checked too.
No packages, services or database records were modified to resolve that tooling
issue. All preflight checks passed before the sole runner attempt.

A new protected backup of all 15 tables was restored on isolated socket-only
MySQL 9.3.0. Every row and table definition matched before ingestion; existing
migration guards verified the restored schema. Source data remained unchanged
during backup verification. Earlier backups were retained, not overwritten.

Backup: `before-phase2-bootstrap-20261107T031300Z.sql`

SHA-256: `493f9b9ed06d6920ad26d428467812aecfaa7084f97ff6d64607ec3f1eb3fe5c`

## Actual execution

All five stages succeeded, exit code **0**, without rerunning the runner:

1. Retrieved and staged the complete available fixture response: 380 fixtures.
2. Retrieved and validated 20 current-season teams and fixture memberships.
3. Loaded provider-specific canonical teams and season memberships; no invented
   venue IDs and no changes to historical descriptions.
4. Loaded fixtures through the existing transactional UPSERT and collision guards.
5. Validated data quality and the exact historical archive, then committed the
   checkpoint and released the run owner.

| Fixture outcome | Actual count |
| --- | ---: |
| Retrieved | 380 |
| Inserted | 380 |
| Updated | 0 |
| Skipped | 0 |
| Rejected | 0 |

Metrics come from the validated frozen manifest, the before/after fixture-ID
sets and exact loaded-value comparisons, rather than MySQL affected-row counts.
All staged IDs were new and disjoint from the historical IDs. This was a
fail-fast batch, not a partial acceptance of invalid API entries.

The imported season has **91 FT and 289 NS fixtures**. Its fixture list contains
380 entries, but its results are incomplete: 289 matches are still scheduled.
All kickoff dates, scores, statuses, observations and team references match the
frozen source batch. No data was fabricated or silently rejected.

The runner's first two progress labels still say API-FOOTBALL; those are legacy
display strings. Runtime configuration, client dispatch, manifest provenance and
stored source mappings all verify football-data.org was the actual source.

## Database verification

| Table | Rows after bootstrap |
| --- | ---: |
| `live_matches` | 760: 380 season 2024, 380 season 2026 |
| `teams` | 40: original 20 API-FOOTBALL plus 20 football-data.org identities |
| `venues` | 20, unchanged |
| `season_teams` | 40: 20 memberships per season |
| `fixture_source_ids` | 760 |
| `team_source_ids` | 40 |
| `season_sources` | 2 |
| `season_sync_state` | 1 |
| `pipeline_control` | 1 |
| `source_registry_state` | 1 |
| `live_matches_backup_20260725` | 1,140, unchanged |
| `live_matches_backup_20260821` | 380, unchanged |
| `matches` | 1,000, unchanged |
| `results` | 43,277, unchanged |
| `teams_backup_20260821` | 42, unchanged |

All original columns/rows in the eight preexisting tables were fingerprinted
before ingestion and compared afterward. Historical fixture/team rows were
selected by their protected season/provider, while untouched legacy tables were
compared in full. All **380 historical matches, 20 original teams and 20 venues**
remain identical. Historical memberships and provider mappings remain identical
too. Global teams now total 40 because providers retain separate identities;
season 2026 still has exactly 20 memberships.

Every staged fixture and team maps to the expected raw provider ID and canonical
namespace. The 2024 binding remains `api_football`; 2026 is `football_data`.
Registry validation checks FK/index/CHECK definitions and completeness. Primary
and unique keys prevent duplicate fixture IDs or canonical/source collisions;
distinct fixture counts also match totals. The original 15-table schema is intact.

### Checkpoint and recovery state

| Field | Stored value |
| --- | --- |
| Season | 2026 |
| `last_success_at` | `2026-11-07 03:20:26.787877` UTC |
| `last_full_sync_at` | `2026-11-07 03:20:26.787877` UTC |
| `last_completed_run_id` | `phase2-bootstrap-20261107T031951Z` |
| `pending_run_id`, observation and lease | All null |

Checkpoint timestamps represent the batch observation time. They were written
only by the successful final validation transaction, after the loads passed.
No earlier season checkpoint was created or overwritten. There are no partial
failed writes to report from this successful run.

Private evidence is retained outside Git in
`pipeline-private/phase2-bootstrap-20261107T031951Z`: baseline fingerprints,
an exclusive one-attempt marker, redacted runner log, completed manifest, exit
status and read-only verification report. The Docker staging volume retains the
same frozen manifest for audit. Secrets are not included in this documentation.

## Tests and remaining gates

- Full suite after ingestion: **295 passed, zero skipped**, 7.63 seconds, on
  isolated MySQL 9.3.0; API mocked and no production test writes.
- Read-only post-verification compared every staged fixture with MySQL and ran
  the existing season-aware quality validator without advancing checkpoints.
- All seven persistent services remain healthy; DAG paused and no other tasks
  or runs active. The bootstrap used the runner, not a Celery/Airflow DAG run.
- No second production ingestion has run. Real production idempotency is still
  unverified; isolated UPSERT/retry/correction tests are not a substitute.
- Automatic weekly scheduling remains disabled. The Mac must remain awake with
  Docker and MySQL active for later scheduled operation.

Ready to request a **separate approval for one repeat-run idempotency test**.
Use a new run ID and the normal incremental plan from the successful checkpoint,
with overlap, overdue/postponed rechecks and bounded provider pacing. Compare
fixture-ID sets and source values before/after: no duplicate records may appear,
and historical rows must remain identical. Observation timestamps and a success
checkpoint may legitimately advance even when source business values are unchanged.
Report source corrections rather than assuming every matched record is unchanged.
Scheduling and GitHub changes remain separately gated.

After real source data exists, guarded migration rollback is deliberately refused.
Retain the additive schema and source data; never delete records to force guards.
Any failed future run must be inspected before approved recovery, without
automatic reruns, checkpoint edits or restoring over the application database.
