# PR #7 final engineering review

Review date: 4 November 2026 (Pacific). Implementation baseline: `69d7005`.

## Branch and code review

PR #6 is merged. Main's tree exactly matches the Phase 2 feature-branch base, and PR #7 adds one adapter commit on top. The comparison contained no missing Phase 2 changes or unexpected files. PR #7 was retargeted to **main**, without merging it. GitHub reported no conflicts before retargeting; recheck the latest commit's checks/mergeability before approval.

Reviewed adapter authentication, competition/season parsing, unsigned source namespaces, source constraints, frozen staging, provider binding, UPSERTs, postponed-ID requests, overlap/full reconciliation, nullable fields, rate-limit headers/retries, and checkpoint-after-quality semantics. Existing unit/integration cases cover these behaviors and historical preservation. The five Airflow tasks and Monday 06:00 UTC schedule remain unchanged.

One reproducible weakness was fixed: migration 004 validated CHECK names and fragments but could accept a weakened expression under the same name. Validation now compares complete normalized CHECK expressions from information_schema; a regression test replaces the namespace constraint with a weaker condition and requires reapply to fail. No application DDL was performed.

## Fernet diagnosis and approval boundary

The explicit private runtime file is the original Desktop checkout's `.env`. No host FERNET_KEY override was present. Compose maps FERNET_KEY to AIRFLOW__CORE__FERNET_KEY. Dotenv parsing found 45 Base64-alphabet characters, no accidental whitespace or outer quotes, and one padding character. Both strict key validation and cryptography.Fernet construction/round-trip failed. This is not a wrong-file, quoting, or whitespace issue. No valid key was found in the local alternate environment/config files checked. Arbitrarily deleting a character would guess a different encryption key; it is not a safe repair.

The existing installation uses PostgreSQL in the stopped Docker stack. **Whether encrypted connections/variables currently exist could not be verified without further metadata access.** No production PostgreSQL/Airflow service was started, and no key was rewritten, disclosed, or rotated. JWT passes; the private file remains mode 0600. Compose validates nonempty values and therefore passes despite the malformed Fernet value.

Before any rotation, obtain explicit approval and a verified **Airflow metadata** backup (separate from the football/MySQL backup below). Prefer inspecting a restored isolated metadata copy. With authorized read-only access, count only encrypted rows, never print values:

```sql
BEGIN READ ONLY;
SELECT COUNT(*) FROM connection WHERE is_encrypted OR is_extra_encrypted;
SELECT COUNT(*) FROM variable WHERE is_encrypted;
ROLLBACK;
```

If the original key is recovered, validate it against encrypted values privately and restore the exact original configuration. If rotation is approved and the old key works, configure new key followed by old key privately, run `airflow rotate-fernet-key` in an approved controlled maintenance context, verify every affected value decrypts without displaying it, then remove the old key. This follows the [official Airflow procedure](https://airflow.apache.org/docs/apache-airflow/stable/security/secrets/fernet.html). If the old key is lost and encrypted rows exist, rotation cannot recover their contents: restore the original key or obtain separate approval to re-enter affected secrets from their authoritative sources. Do not delete metadata, recreate volumes, or reset credentials to force startup. If no encrypted rows exist, a new key still requires approval and consistent configuration across every Airflow component. No rotation is authorized or performed by this review.

## Verified application backup and integrity

A private SQL backup was created outside Git using a single-transaction read-only dump, owner-only file permissions and a restricted backup directory. It was restored only into a random database on a separate socket-only MySQL instance, with networking disabled. Every row, original ID and SHOW CREATE TABLE definition matched the source by SHA-256 fingerprints. Source checks before and after the dump matched, and the trusted archive comparison passed.

- Backup: `~/Desktop/soccer-data-pipeline-backups/before-source-review-20261105T060018Z.sql`
- SHA-256: `7986a769e0487dca08ff20060a5c691381fb983293a2a4d59e0d3675fb1c52d6`
- Adjacent `.verification.json` contains restore proof; both files are private and uncommitted.
- Counts: **380 matches, 20 teams, 20 venues**, with all original values and IDs preserved.
- Migrations **003 then 004** were applied successfully to the **restored copy only**, followed by another historical integrity check.
- The application database remains at its original schema; neither migration was applied there.

The dump covers the football application database, not Docker PostgreSQL/Airflow metadata. Keep both recovery scopes distinct. Stop other writers for an approved migration and take a fresh backup if the application changes after this verified snapshot.

## Executed verification

- Full suite on isolated MySQL 9.3/Python 3.13: **295 passed**; API mocked. Includes FK/unique/source constraints, source collisions, partial migration up/down recovery, idempotency, multi-season checkpoints, missing fields, corrections and archive equality.
- Offline suite: **267 passed**, with 28 explicit MySQL integration skips.
- Actual Airflow 3.3.1 import passed: five tasks, correct dependencies, Monday 06:00 UTC, two retries/five-minute delay, one-hour task timeouts, catchup false and one active run.
- Private Compose configuration passed without service startup. Docker daemon is stopped; running service health, image build, metadata contents and container-to-Mac MySQL connectivity remain unverified.
- Two minimal read-only football-data.org probes through the adapter verified league PL/season 2026 matches and 20 teams. No data was staged or loaded. Explicit FOOTBALL_SOURCE=football_data is supported; deployment settings are not silently switched.
- Read-only application connectivity and archive checks passed. Migration readiness is blocked only by required application approvals/order and operational prerequisites; no namespace/schema conflicts were observed on the restored copy.
- Compilation, dependency consistency, credential scans and protected-dataset/original-SQL checks passed. Check the latest PR commit's Python 3.11/MySQL 8.0/Airflow CI before merging.

## Readiness and exact next steps

PR #7 can be approved for merge once its current CI is green; it is **not activated**. Remaining gates:

1. Recover the exact existing Fernet key privately, or approve a separate Airflow metadata audit/recovery plan. Do not rotate while encrypted-data state is unknown.
2. Approve PR #7's merge to main separately. No merge is performed by this review.
3. Confirm the verified backup is current, stop all writers, then explicitly approve migrations 003 followed by 004. Run each read-only preflight first, apply only after approval, and verify archive/schema/source mappings afterward. See [migration commands](football-data-source.md#migration-004-and-recovery).
4. Set FOOTBALL_SOURCE=football_data and FOOTBALL_SEASONS=2026 in the private deployment configuration; retain API_KEY and FOOTBALL_DATA_API_KEY separately. Preserve the existing Compose project/volumes and validate the recovered Fernet/JWT settings.
5. Obtain approval before production service startup. Keep the DAG paused; verify imports, health, private credentials, volume identity and host.docker.internal database connectivity.
6. Obtain separate approval for one supervised ingestion run. Verify all five tasks, source mappings, statuses/results, unchanged historical values, duplicate prevention and checkpoint advancement. Check a supported rerun, then enable the Monday 06:00 UTC schedule only after results are accepted.

No live ingestion, production service startup, application migration, volume deletion, subscription purchase, credential rotation, or Phase 3 work occurred. A passing test/restore/API probe is not a successful deployment.
