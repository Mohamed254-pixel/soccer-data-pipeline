# Isolated EC2 demo

This stack is a manual-only recruiter demo in `us-east-2`. It seeds a new database from the committed 2024 archive and
reuses the current five tasks and quality checks. The demo DAG has ID
`premier_league_demo`, no schedule, one active run and one concurrent task.
The existing local DAG, scheduling, MySQL, and Compose project are separate.
CloudFormation deployment and staged startup completed. See the
[verified AWS baseline](../../../docs/portfolio/phase3/README.md) for results.
The first successful live five-stage ingestion completed on November 11, 2026.
It loaded 380 unique 2026–27 fixtures and archived the matches and teams
responses. One supervised repeat run reprocessed the 30 fixtures in the
normal incremental window without inserting duplicates or changing fixture
business values. See the [verified AWS evidence](../../../docs/portfolio/phase3/README.md).

## Exact proposed infrastructure

Use stack name `premier-league-phase3-demo` and the existing CLI profile
`soccer-data-pipeline`. Resolve and record an eligible Ohio x86_64 AL2023
AMI ID and supported Ohio availability zone before creating the change set.
Set `ApprovedStopEpoch` to the separately approved absolute UTC cutoff.
The template creates these 14 CloudFormation resources:

| Logical IDs | Configuration |
|---|---|
| `Vpc`, `ComputeSubnet` | One VPC and one IPv4 subnet in a single Ohio AZ |
| `InternetGateway`, `GatewayAttachment`, `PublicRoutes`, `InternetRoute`, `PublicRouteAssociation` | Internet egress through an internet gateway |
| `HostSecurityGroup` | Zero ingress, outbound TCP 443 only |
| `AirflowHost` | One on-demand Linux x86 `c7i-flex.large`, 2 vCPU and 4 GiB, one auto-assigned public IPv4 while running, 20 GiB encrypted gp3 root disk deleted on termination |
| `Archive`, `ArchivePolicy` | One retained versioned S3 Standard bucket, SSE-S3, block public access, TLS and conditional writes required on `raw/` |
| `RuntimeSecret` | One retained Secrets Manager secret for demo-only values, with no value supplied to the template |
| `HostRole`, `HostProfile` | EC2 trust, AWS-managed Systems Manager core policy, scoped archive and secret access |

The EC2 role allows `s3:PutObject` and `s3:GetObject` on this bucket's
`raw/*`, and `secretsmanager:GetSecretValue` on this secret ARN. It has no
archive delete, bucket listing, secret update, or EC2 stop grant. The operator
uses a separately approved identity for CloudFormation and SSM access. Do
not grant the host the operator's permissions. No RDS, Redis, NAT gateway,
load balancer, CloudWatch log group or alarm is created. Docker rotates
container stdout/stderr locally at 5 MiB × 2 per service. Airflow task log
files and staging are separate volumes. Check their growth after each run and
export only the selected redacted evidence before cleanup.

MySQL and PostgreSQL bind to internal Docker networks with no published DB
ports. MySQL requires encrypted TCP and the app account has only SELECT,
INSERT, UPDATE, DELETE on the demo schema. The MySQL client relies on enforced
TLS inside the dedicated host and does not verify the generated MySQL server
certificate's identity. The UI binds to host loopback port 18080 for SSM
port forwarding. The host firewall restricts IMDS access from Docker to the
scheduler on its dedicated egress bridge. This trusted scheduler can assume
the host role, including reading the demo secret. Host root and Docker
administrators are trusted. They can inspect task environment and mounted
secrets. Never give demo credentials or Docker access to viewers.

## Gross estimate for this exact template

Rates use the Ohio Price List results from the Phase 3 review and one 730-hour
month. The resource envelope is 32 running hours and one month of storage.

| Item | Assumption | Gross |
|---|---|---:|
| EC2 | 32 × $0.08479 | $2.7133 |
| Public IPv4 | 32 × $0.005 | $0.1600 |
| Root disk | 20 × $0.08, full month | $1.6000 |
| Secrets Manager | One secret for a month | $0.4000 |
| S3 Standard | 1 GB-month, 1,000 PUTs and 1,000 GETs | $0.0284 |
| Contingency | Secret requests, small transfers and usage rounding | $0.2500 |
| **Total** | Before credits, free allowances and taxes | **$5.15** |

S3 versions count toward storage. Optional snapshots are excluded and would
need their own cost review. Stopping ends instance compute and auto-assigned
public IPv4 usage. EBS, the S3 archive and the secret continue to accrue.
Check gross project spend before launch and after billing catches up. Do not
add capacity, prolong the deadline or retry provisioning if the reviewed
envelope no longer fits the $10 budget.

[Phase 3 price and Free-plan sources](../../../docs/phase3-aws-deployment-plan.md)

## Approval and offline verification

The stack has **no automatic Docker install, database bootstrap or ETL**.
Cloud-init installs and arms a systemd check only. First boot writes the
earlier of the approved UTC deadline and 31 h 59 min from initialization,
with margin for the 15-second timer interval. The absolute file persists
across reboots and stops. A missing, invalid or expired deadline requests
OS poweroff. The instance maps OS poweroff to EC2 stop. A failed cloud-init,
broken timer or operator change can still defeat this control. Require an
independent operator alarm/reminder and confirm EC2 reaches `stopped`.

The shell tests inject a fake clock and poweroff command to exercise
before-deadline, exact deadline, past deadline, missing and malformed inputs.
Real systemd timer firing and EC2 stop behavior remain launch checks. Test
them early by temporarily shortening the deadline on the approved host,
confirming it stops, then restoring the original cutoff through approved
operator recovery if the chosen drill allows it. An easier approach is
testing the command with a separate temporary service that writes a marker
and leaves the real stop timer active, then observing the actual planned
stop. Keep an operator ready to call stop when the approved deadline arrives.
An expired instance immediately stops on restart. Preserve the original cutoff
when recovering from any drill.

Steady-state container limits are 3,200 MiB, leaving 896 MiB of nominal 4 GiB
for the OS and Docker. This is an allocation check. Actual runtime peaks and
image disk use remain unmeasured until a disposable 4 GiB / 20 GiB Linux
Docker environment is available. The MySQL bootstrap and metadata migration
run before normal Airflow startup. Use the capacity script before building,
after building and during representative load. Require at least 12 GiB free
before build, 4 GiB after build and during runtime, at least 384 MiB available
RAM during runtime, five healthy containers, zero OOM kills and zero
unexpected restarts. Monitor repeatedly during bootstrap and the heaviest
test and repeat. Stop if these thresholds fail. Reprice any proposed change.

Offline verification on November 10, 2026: 326 tests passed with no skips,
using a fresh socket-only MySQL 9.3 server, including a demo bootstrap from
the committed archive and the existing football-data.org five-stage
integration with a mocked provider. Ohio CloudFormation lint and offline
Compose parsing passed. Airflow 3.3.1 imported the generated DAG and confirmed
its null timetable and exact five-task chain. This leaves MySQL 8.4 container startup, the x86
image build, actual container resource fit and live systemd/EC2 behavior
unverified. The deployed AWS workload was subsequently measured during both
successful ingestions; refer to the evidence report for observed capacity and
post-run health. Following evidence collection, the instance was verified
stopped; verify its state and cutoff before any later restart.

## After approval

1. Verify identity, Free plan, budget and stack absence. Review the exact
   template SHA-256, AMI ID, AZ, UTC cutoff, operator SSM access and image
   digests. Create a **CREATE** change set using
   `deploy/aws/demo/infrastructure.json` and `CAPABILITY_IAM` only after
   approval to create it. Show all 14 Add actions and exact parameters and
   request execution approval. The separate RDS helper targets the full
   template and must not be used for this demo.
2. After execution approval, wait for stack completion. From SSM, inspect
   cloud-init and verify the systemd service/timer and deadline. Confirm the
   host is dedicated to this demo before installing Docker, the reviewed
   Compose plugin and the required host Python dependency (`cryptography`).
   Install Docker via AL2023's signed packages. Obtain the Compose binary
   from its official release and verify the checksum. Install iptables if
   absent. Apply `sudo bash deploy/aws/demo/imds-firewall.sh` after Docker
   starts and before running containers. Reapply after any Docker/firewall
   restart before starting containers. Verify the IMDSv2 rule and that only
   the scheduler container can reach IMDS. Run
   `sudo bash deploy/aws/demo/check-capacity.sh before-build`.
3. Transfer the reviewed source through the approved operator path. Build
   with `sudo docker build --platform linux/amd64 --build-arg
   AIRFLOW_BASE=apache/airflow@sha256:REVIEWED_DIGEST -f
   deploy/aws/demo/Dockerfile -t premier-league-demo:REVIEWED_COMMIT .`.
   Resolve PostgreSQL 16 and MySQL 8.4 digests and pull them explicitly.
   Run the capacity script with `after-build`.
4. Prepare a reviewed nonsecret settings JSON with keys `DEMO_IMAGE`,
   `DEMO_MYSQL_IMAGE`, `DEMO_POSTGRES_IMAGE`, `DEMO_RAW_BUCKET`, and
   `DEMO_AWS_ACCOUNT_ID` from the verified operator identity. Use
   reviewed immutable digest references for MySQL and PostgreSQL. Populate
   the stack secret privately with independent 64-character lowercase hex
   values for `DEMO_ROOT_PASSWORD`, `DEMO_APP_PASSWORD`,
   `DEMO_BOOTSTRAP_PASSWORD`, `DEMO_METADATA_PASSWORD`, `DEMO_JWT_SECRET`,
   plus a Fernet key in `DEMO_FERNET_KEY` and the separately approved
   `DEMO_FOOTBALL_TOKEN`. From a root session with tracing off and
   `set -o pipefail`, pipe
   `aws secretsmanager get-secret-value --region us-east-2 --secret-id
   REVIEWED_SECRET_ARN --query SecretString --output text` directly into
   `python3 deploy/aws/demo/runtime.py --directory /root/pl-demo-runtime
   --settings /root/pl-demo-settings.json`. Never echo the result. Keep the
   private directory root-only, with the runtime file mode 0600. The three
   password files are readable only through the private host directory or
   their explicit container mounts.
5. On the demo host as root, use this wrapper for every Compose operation:

   ```bash
   demo() {
     python3 deploy/aws/demo/runtime.py --directory /root/pl-demo-runtime -- "$@"
   }
   demo config --quiet
   demo up -d --wait mysql postgres
   demo --profile setup run --rm bootstrap
   demo --profile setup run --rm staging-permissions
   demo --profile setup run --rm staging-check
   demo exec -T mysql bash -ec '
     export MYSQL_PWD="$(cat /run/secrets/demo_root)"
     mysql --protocol=socket -uroot -e "DROP USER IF EXISTS '\''demo_bootstrap'\''@'\''%'\''"
   '
   demo run --rm airflow-api db migrate
   demo run --rm airflow-api users create --username demo-admin \
     --firstname Demo --lastname Operator --role Admin --email APPROVED_EMAIL
   demo up -d --wait airflow-api airflow-processor airflow-scheduler
   bash deploy/aws/demo/check-capacity.sh running
   ```

   The one-shot staging setup owns only `/opt/soccer/data/staging` as
   `50000:0` with mode `0750`; it does not recurse over existing staged files.
   Its setup container has no network, a read-only root filesystem, and only
   the `CHOWN` and `FOWNER` capabilities. The separate write check runs as the
   Airflow UID `50000:0` with no capabilities before the scheduler starts.

   Enter the unique UI password at the private prompt. Verify MySQL root is
   localhost-only, the bootstrap account is gone and the app cannot perform
   DDL. Do not grant the running DAG access to bootstrap or root passwords.
   If bootstrap fails, stop and inspect the isolated schema. Never run it on
   the production DB or reset existing volumes by default.
6. Forward remote port 18080 through SSM, log in locally, verify the demo DAG
   has no schedule and approve a manual run. Record five task successes,
   original archive fingerprints, fixture keys and foreign keys, checkpoint
   advancement only after validation, and S3 content digests. Run the
   approved repeat and compare rows for idempotency. Capture redacted evidence
   and record runtime/disk peaks. Pause the demo DAG, confirm no pending
   writer, stop the Compose project gracefully, and stop EC2. Verify
   `stopped` from the operator CLI. Keep the Mac independent throughout.

## Rollback and cleanup

On failure, pause the demo DAG and let current tasks finish or cancel and
confirm the writer is inactive. Capture sanitized diagnostics and stop EC2.
Only use approved, isolated archives or exports for recovery. Restore into
a new demo schema or stack, never over the Mac or a partially written demo.
For any new host or extra running hours, get a fresh budget decision.

After the approved export, delete the demo stack and wait for completion.
Check that the instance terminated, the auto-assigned IPv4 is gone, the root
EBS disk was deleted, and the demo role and network are gone. The S3 bucket
and secret intentionally survive stack deletion. Inventory all S3 versions,
delete markers and incomplete uploads. Empty and delete the bucket only
under the cleanup approval. The lifecycle expires current raw objects
after 30 days, noncurrent versions after 7 days and eligible delete markers.
Schedule deletion of the runtime secret with the approved recovery window.
Review any optional snapshots or exports by exact ID and delete only the
approved artifacts. Recheck gross usage after billing catches up.
