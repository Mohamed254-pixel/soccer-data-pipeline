# Approved staged Docker and Airflow startup

**Subsequent approved step:** [one supervised bootstrap](phase2-bootstrap-results.md) has now loaded and validated 380 season-2026 fixtures. The startup record below predates ingestion. The DAG remains paused; production repeat-run testing and scheduling still await approval.

Verified 7 November 2026 UTC (6 November Pacific). Approval covered service
startup and read-only verification only. No DAG trigger, ETL run, scheduling,
application-data write, credential change, push or merge was performed.

## Startup sequence and safeguards

1. Rechecked the existing physical metadata backup and pre-pause logical backup
   checksums, saved pause evidence, private Fernet/JWT configuration and offline
   Docker restart policies. No saved pipeline containers could automatically
   start ingestion; unrelated containers were manually stopped.
2. Started Docker Desktop. Verified the original named volumes:
   `soccer-data-pipeline_postgres-db-volume` and `soccer-data-pipeline_soccer-data`.
   Used Compose project `soccer-data-pipeline`, preserving original metadata and
   staging storage.
3. Verified the original runtime checkout at `fde57c0` matches reviewed Python,
   DAG and archive source. Kept its existing config, logs and plugins rather than
   replacing them with absent directories from a separate worktree.
4. Started only PostgreSQL and Redis. Live metadata confirmed the exact DAG was
   paused, no queued/running/retry/deferred task work existed, no active DAG runs
   existed, and Redis was empty. Historical records were present: five DAG runs,
   22 task instances, one Airflow user, zero connections and zero variables.
5. Saved a fresh private metadata dump and historical-row fingerprints. The new
   dump's archive listing was checked; this new dump was not independently
   restore-tested. The earlier physical backup already has successful restore
   evidence, whose checksum was rechecked before startup.
6. Built the reviewed images and ran a one-off read-only Python container. Actual
   Airflow 3.3.1 / Python 3.13.14 validated Fernet encryption/decryption, current
   metadata and provider migration heads, container-to-host MySQL access, archive
   integrity and the actual DAG import/dependencies. No scheduler or ETL ran in
   that container.
7. Started API server, DAG processor and triggerer. After their health passed,
   rechecked paused state, no active task/run work and an empty broker, then
   started scheduler and worker.

`airflow-init` was **not run**: the existing metadata and user setup are current.
The stack has five persistent Airflow services plus a one-shot initialization
service, not six persistent Airflow services. No metadata initialization,
migration, user creation or volume reset was needed. Scheduler heartbeats and DAG
registration are normal service activity; historical records remain preserved.

## Executed final verification

| Component | Result |
| --- | --- |
| `airflow-apiserver` | Running, healthy |
| `airflow-dag-processor` | Running, healthy |
| `airflow-scheduler` | Running, healthy |
| `airflow-triggerer` | Running, healthy |
| `airflow-worker` | Running, healthy |
| PostgreSQL / Redis | Both running, healthy |
| `airflow-init` | Skipped; existing metadata is current |
| Restarts | Zero across all seven persistent containers |
| DAG | `premier_league_etl`, paused |
| Active/queued tasks and runs | Zero |
| Broker queue and unacknowledged messages | Zero |
| DAG import errors | Zero |
| Schedule and dependencies | Five-task chain; Monday 06:00 UTC; catchup disabled; two five-minute retries; one-hour task timeout; one active run |
| Secrets | All five Airflow environments match private Fernet/JWT values; actual encryption round-trip passed |
| Volume mounts | Original named volumes and read-only archive mount verified |
| Runtime source | File hashes verified inside all five Airflow containers |
| Staging permissions | Existing named-volume parent writable; staging directory not yet created; archive readable |
| Historical Airflow metadata | DAG-run, task-instance, user, connection and variable row fingerprints unchanged |
| Startup logs | No ERROR/CRITICAL/FATAL/traceback markers or private credential matches found in captured logs |
| MySQL archive | 380 matches, 20 teams and 20 venues; original values unchanged |
| Other existing MySQL tables | All original rows across all eight preexisting tables unchanged |
| Season 2026 fixtures | **0** |
| Checkpoints / pending owner | Empty / none |

The initial final-audit path assertion rejected Docker Desktop's `/host_mnt`
prefix for one bind mount. Read-only diagnosis confirmed the same intended host
path. The audit was corrected to recognize that exact host alias and additionally
verify mounted file hashes. No container, volume or data correction was made.

Private startup evidence, metadata fingerprints and a fresh pre-start logical
dump are retained outside Git under `pipeline-private/phase2-service-startup`.
The original backups were preserved. No fresh full pytest run was needed for
startup-only changes: the preceding migration stage passed all 295 tests on
isolated MySQL. This stage imported the real DAG inside the deployed image and
verified live services and database reads. No new CI run is claimed without a push.

## First-ingestion gate

Service readiness checks pass. First ingestion remains **unapproved and unrun**.
The intended target is the existing local `soccer_db`, using its application
account, `FOOTBALL_SOURCE=football_data`, competition PL / 2021 and season 2026.
The first run must bootstrap the complete available fixture response, not only
the matchday-one readiness sample. Two additional read-only API calls verified
**380 available fixtures: 91 FT and 289 NS**, plus 20 teams with consistent fixture
memberships. The fixture list is complete in size; the season's results are not
complete. Nothing was staged and no database connection was opened by these
probes. Source coverage can change before the approved run; actual imported counts
must still be measured from that run.

Before a write-capable run, show the source coverage and execution plan and obtain
explicit ingestion approval. Preserve the 2024 archive, validate all mappings,
memberships, fixture statuses/scores and checkpoint behavior, then separately
request repeat-run approval. Scheduling requires a later approval still.

The proposed first supervised run uses the existing five-stage `run_pipeline.py`
inside the worker container, with application credentials and the DAG still
paused. A paused DAG is not an execution path to rely on for a scheduler-driven
manual run. The runner exercises ETL in the deployed environment without creating
an Airflow DAG run or changing pause state. It will claim the database owner, bind
season 2026 to football-data.org, stage available fixtures and teams, add their
separate provider identities and memberships, load fixtures, then validate and
commit the success checkpoint. These write-capable steps have **not** executed.
Immediately afterward, verify archive equality, source IDs/statuses/scores,
uniqueness and checkpoint state.

The DAG remains paused and there is no next automatic run to report. Keep the
Mac awake, MySQL running and Docker Desktop active to retain service availability.
This is a local deployment, not an always-on cloud service. Do not run a routine
unqualified `compose up` that invokes unnecessary initialization; follow the
existing-metadata startup sequence in the README. Never remove named volumes.
