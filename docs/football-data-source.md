# football-data.org source integration

## Design before implementation

Use an explicit `FOOTBALL_SOURCE` selector, defaulting to `api_football` for compatibility. Select `football_data` for new 2026–27 ingestion. Keep all five Airflow tasks and the Monday 06:00 UTC schedule. Do not change migration 003 or apply any migration to the application database in this work.

Source identity must precede loading. Migration 004 introduces:

- `season_sources`: one provider per season, with 2024 restricted to API-FOOTBALL. Existing seasons are bound to API-FOOTBALL. Switching a populated/bound season requires a separately reviewed reconciliation, never an automatic fallback.
- `team_source_ids` and `fixture_source_ids`: unique `(provider, source_id)` to unique canonical IDs, with foreign keys and arithmetic namespace checks. API-FOOTBALL retains its original IDs in the lower half of the existing unsigned columns. football-data.org uses `2^31 + source_team_id` for canonical team IDs and `2^63 + source_fixture_id` for fixture IDs. Raw positive IDs must fit below those offsets. No hashing, float conversion, name matching, or guessed cross-provider identity.
- A team `source_provider` discriminator and provider-scoped team-name uniqueness. Both providers can describe the same real club with the same name while retaining independent source identities; no original team values or IDs change. Cross-provider club deduplication is intentionally not inferred.

The existing fixture date/name unique-key guard remains. One-provider-per-season prevents importing the same season twice with different fixture IDs. Venue IDs are not synthesized: football-data.org provides venue text but no stable venue resource ID in these endpoints. New team snapshots retain stadium text and use null venue_id; the original 20 venues remain unchanged.

Use date overlap plus explicit pending fixture requests for incremental extraction, and full active-season reconciliation every 28 days. Require every known fixture in a full reconciliation; never interpret a permission error as an empty season. Keep run ownership, frozen staging, observation binding, transactional loads, and checkpoint-after-quality behavior. Source identity must be bound to manifests, source-season registrations, and all load/validation stages.

004 is an explicit guarded migration after 003, with a read-only preflight by default. DDL commits implicitly. Stop writers, verify backups and archive integrity, and obtain approval before application. A down migration must refuse any football-data source binding/rows and never delete imported data. Test resume, rollback, IDs, and archive preservation on disposable MySQL only.

## Adapter contract and unavailable fields

The adapter uses the existing private `FOOTBALL_DATA_API_KEY` in `X-Auth-Token`, HTTPS v4 endpoints, and refuses redirects. Credentials and raw provider error bodies are not logged. Source token values and the private runtime environment were not modified in this implementation.

| football-data.org | Canonical storage |
| --- | --- |
| Match `id` | Raw `fixture_source_ids.source_id`; namespaced `live_matches.fixture_id` |
| Home/away team `id` | Raw `team_source_ids.source_id`; namespaced team FK values |
| Competition PL / ID 2021, season.startDate | Canonical Premier League scope and requested starting-year season |
| utcDate | UTC DATETIME(6); unknown scheduled/postponed kickoff remains null |
| score.fullTime.home / away | Nullable nonnegative goals; FINISHED requires both values |
| FINISHED duration REGULAR / EXTRA_TIME / PENALTY_SHOOTOUT | FT / AET / PEN |
| SCHEDULED / TIMED / IN_PLAY / PAUSED | TBD / NS / LIVE / HT |
| EXTRA_TIME / PENALTY_SHOOTOUT / SUSPENDED | ET / P / SUSP |
| POSTPONED / CANCELLED / AWARDED | PST / CANC / AWD |
| Team venue text | season_teams.team_data.stadium; null venue_id, no invented stadium resource |
| Optional match venue / lastUpdated / raw status | Frozen manifest provenance fields |
| Team name / tla / crest / founded / area.name | Name, code, logo, founding year, country in season team snapshots |

Elapsed minute is left null because the list endpoint/plan does not guarantee it. Stadium capacity, surface, image, structured venue address/city, and stable venue IDs are not supplied by these endpoints. No source IDs or venues are inferred from names or home-team identity. A match venue (when present) is kept in staging and is not assumed to equal the home team's stadium. Source lastUpdated is provenance; checkpoints and stale-batch fencing use the existing UTC observation time. Optional fields remain null when absent, not fabricated defaults. A missing required field, unfamiliar status, unknown kickoff on a status that requires one, negative/fractional score, wrong season, or invalid response fails before a fixture load.

Neither source overwrites canonical historical descriptions. New-source canonical team rows may increase the total from 20 to 40; this is source separation, not extra season memberships. Each active season still requires exactly 20 memberships, and the original 20 team and 20 venue records must remain byte-for-value equal to the archive. No season is deleted or replaced.

## Migration 004 and recovery

Migration 003 SQL remains unchanged. 004 requires its fully upgraded schema and exact archive verification. It refuses pending ETL owners, unclassified matches, or preexisting IDs in reserved namespaces. Initial source bindings/mappings label all existing records API-FOOTBALL. A separate ready marker blocks runtime access while 004 is incomplete. The source registry, keys/types/engines and FK/CHECK constraints are checked before marking it ready. Apply/rollback share the database-scoped migration lock with 003; external writers still must be stopped.

The team discriminator and fixture composite index each use an atomic ALTER. Other DDL statements commit independently and support resuming an interrupted apply. A retry of an applied migration verifies the schema/registry and performs no writes. The guarded down migration refuses any football-data season binding or upper-namespace rows, even if a first run failed after claiming an empty season. It never deletes imported football-data rows to force a rollback. Interrupted down cleanup is resumable. Once source data exists, retain the schema and pause/resume/release the run using the existing recovery process. Do not drop 004 manually or replay old legacy CSV loaders after activation.

For approved maintenance only, using a private administrator environment:

```bash
# Read-only preflight; 003 must already exist:
PIPELINE_ENV_FILE=/private/path/admin.env python scripts/migrate_sources.py
# Separate approval required before either mutation:
PIPELINE_ENV_FILE=/private/path/admin.env python scripts/migrate_sources.py --apply
PIPELINE_ENV_FILE=/private/path/admin.env python scripts/migrate_sources.py --rollback
```

The application account needs INSERT/SELECT/UPDATE on the new mapping/binding tables; runtime performs no DDL. Use MySQL 8.0.16 or later for enforced CHECK constraints. Stop all writers during migrations. A source binding cannot be changed in place: existing fixture/team IDs, checkpoints, and uniqueness rules require a separate reviewed cross-provider reconciliation. No fallback resets checkpoints or downloads the protected archive.

## Verification and safe activation

Automated verification uses mocked HTTP payloads and a separate socket-only disposable MySQL server. It covers the complete five stages, POSTPONED-to-FINISHED corrections, completed-run retries, colliding historical raw IDs/names, multi-season checkpoints, API-FOOTBALL compatibility after 004, schema drift/constraints, migration up/down/reapply/resume, and unchanged historical values. CI runs Python 3.11 with MySQL 8.0 and actual Airflow 3.3.1 imports. PR #7 now targets `main` after confirming that main contains the complete Phase 2 base; PR #6 was already merged earlier with owner approval. PR #7 remains unmerged. See [the final review](pr7-review.md).

No application migration, live ingestion, credential rotation, service startup, subscription purchase, or volume removal is part of this implementation. The earlier limited live probes verified 2026–27 match/team access; they do not establish that this new adapter has ingested or validated a live database batch. A real ingestion run remains unapproved/unperformed.

Activation order:

1. Review PR #7 against main and approve its merge separately. Its base was verified and retargeted; no further intermediary feature-branch merge is needed.
2. Preserve the private API keys and Fernet/JWT secrets. Set `FOOTBALL_SOURCE=football_data` and `FOOTBALL_SEASONS=2026` explicitly for the intended runtime. Do not silently replace `API_KEY` with the football-data token. Keep one shared durable staging directory and the existing Compose project/volumes.
3. Follow the [backup/restore verification procedure](phase2-activation.md): pause/stop writers, take a private backup, restore it into an isolated compatible server, compare all historical values/IDs/schema, and retain recovery evidence. No application backup restoration was executed by these tests.
4. Obtain approval for migrations. Run 003 preflight/apply only if not already applied, then 004 preflight/apply. Recheck original 380 matches / 20 teams / 20 venues and all original values immediately afterward. Inspect schema/registry readiness and source bindings. Never bypass drift, namespace, or pending-run guards.
5. Use `FOOTBALL_SOURCE=football_data python scripts/check_readiness.py --env-file /private/path/runtime.env --api` for small read-only access checks. The command must still exit nonzero until schema, configuration, healthy services, and source bindings are ready. A bootstrap-ready token is not proof of a successfully deployed pipeline.
6. Obtain separate approval before starting/building/initializing production Airflow services. Keep the DAG paused; verify imports, volume identity, worker health, and Mac-host MySQL connectivity. Docker daemon availability/build/networking remain operational checks, not claims made by unit tests.
7. Obtain explicit approval for one supervised manual ingestion run. Verify every stage, 2026 source IDs and statuses, 20 season memberships, original archive equality, no duplicate IDs, checkpoint advancement only after quality success, and idempotent rerun behavior. Preserve source IDs as integers or decimal strings in exports; do not round them through floating point.
8. Only after that run is accepted, enable the existing Monday 06:00 UTC schedule and inspect the first scheduled execution. No Phase 3 work is included.

Sources: [competition endpoints](https://docs.football-data.org/general/v4/competition.html), [match contract](https://docs.football-data.org/general/v4/match.html), [status/response header tables](https://docs.football-data.org/general/v4/lookup_tables.html), [rate-limit policy](https://docs.football-data.org/general/v4/policies.html).

## Executed follow-up results

| Check | Observed result |
| --- | --- |
| Offline suite, local Python 3.13.5 | **267 passed, 27 expected integration skips** |
| Full suite, isolated MySQL 9.3.0 socket | **294 passed**, API mocked, no application credentials |
| Actual Airflow 3.3.1 DAG import | Passed: five-task chain, Monday 06:00 UTC, retries/timeouts, max_active_runs=1 |
| Example/private Compose syntax | Passed without starting containers |
| Application read-only integrity check | 380/380 distinct fixtures, 20/20 teams, 20/20 venues; all original values match archive |
| Application migrations | 003 and 004 remain unapplied; Phase 2 disabled |
| Credentials, archive, original SQL, DAG and Compose files | Credential scan passed; protected datasets and SQL 001–003, DAG, and Compose unchanged from the Phase 2 base |
| Docker daemon/services | Daemon stopped; runtime services/networking/build not verified |
| Current private secrets | JWT passes; **Fernet fails strict Base64/length validation** |

The current private Fernet value has 45 characters and does not decode as a valid key. No environment override was present; the private file still has mode 0600. This is a new blocker relative to earlier successful configuration checks. Compose's nonempty-variable check cannot detect a malformed key. **Recover and verify the exact existing Fernet key privately before startup; do not generate/rotate a replacement for an environment with stored encrypted Airflow values.** This implementation neither edited nor disclosed it. The current football-data token is present; no additional live API requests or ingestion were performed in this implementation.

CI results must be checked on the follow-up PR's latest commit. Local MySQL 9.3/Python 3.13 tests do not substitute for the separate Python 3.11/MySQL 8.0 CI jobs.
