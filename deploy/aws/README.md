# Phase 3 AWS deployment candidate

**Status: prepared locally, not deployed.** There is no verified AWS account or
region in this workspace. Budget and infrastructure approval are pending.
Docker was unreachable during preparation, so image building and live cloud
verification have not run. Local Phase 2 configuration/data were not modified.

The proposed design preserves Airflow and its five tasks. This choice is pending
owner confirmation; an AWS-native scheduler would need a different deployment.

## Architecture and scope

```mermaid
flowchart LR
    OP[Operator via AWS SSM] --> EC2[EC2: Airflow Compose]
    API[football-data.org] --> EC2
    EC2 --> RAW[S3: immutable raw response copies]
    EC2 --> DB[Private RDS MySQL 8.4]
    EC2 --> LOG[CloudWatch container logs]
    EC2 --> SECRET[Secrets Manager: application runtime secret]
```

- One x86 EC2 `t3.large` host, encrypted 40 GiB EBS, IMDSv2, SSM management,
  no inbound ports. Docker runs the existing five Airflow services, PostgreSQL
  metadata and Redis. Persistent volumes remain on this host; this is not HA.
- Private, encrypted RDS MySQL in a two-subnet group; only the EC2 security group
  can connect on 3306. Default candidate is single-AZ `db.t4g.micro`, 20 GiB gp3,
  autoscaling capped at 30 GiB, seven-day automated backups, deletion protection,
  snapshot-on-delete and snapshot-on-replacement policies. The engine patch
  must be explicitly selected from versions available in the chosen region.
- A private S3 bucket with versioning, SSE-S3 encryption, ACLs disabled, blocked
  public access, TLS-only bucket policy and retention on stack deletion. No
  automatic data expiry. Raw archives use provider/run/content SHA-256 paths;
  changed responses have different keys. Conditional PUT prevents overwrite;
  retries verify the existing object's body. No headers or tokens are archived.
- Application tasks read only their runtime secret, write/read `raw/*` objects
  and publish logs to the stack's log group using the instance role. They cannot
  read the RDS administrator secret or delete archive objects. No AWS access keys
  go into environment files. Administrator operations use a separate operator.
- A host-status alarm is provisioned but has no notification destination yet.
  CloudWatch logging alone is not task-failure alerting. Choose/verify an alert
  destination and add DAG-failure monitoring before unattended cutover.

CloudFormation is in `infrastructure.json`. It creates infrastructure only:
there is no UserData that initializes Airflow, copies secrets, imports the
application database, starts ETL or enables a schedule. `compose.yaml` is a
separate cloud project, not an override for the Mac's existing stack.

## Costs and approval

Select the account, region and monthly spending limit first. Use the
[AWS Pricing Calculator](https://calculator.aws/) with the actual region and
these resources: 730 EC2 hours/month, 40 GiB EBS, 730 RDS hours/month, 20–30 GiB
RDS storage, public IPv4, Secrets Manager, CloudWatch ingestion/retention, S3
versions and transfers. Do not assume the resources are free-tier eligible.
No NAT gateway, ALB, MWAA, EKS, Kafka, Spark or dbt is proposed. Retained
S3 data, secrets, log groups, snapshots and EBS volumes can continue incurring
charges after a stack is deleted; cleanup needs separate data-retention review.

Configure an AWS SSO profile with a suitably scoped deployment role using the
[official AWS CLI setup](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).
Never send credentials through chat or commit them. Use a budget alert approved
by the owner; a budget notification is not a hard spending cap.

```bash
python -m pip install -r requirements-aws.txt
python scripts/aws_deploy.py identity --profile YOUR_SSO_PROFILE \
  --account-id YOUR_ACCOUNT_ID --region YOUR_REGION
aws rds describe-db-engine-versions --engine mysql --region YOUR_REGION \
  --query 'DBEngineVersions[?DBParameterGroupFamily==`mysql8.4`].EngineVersion'
python scripts/aws_deploy.py plan --profile YOUR_SSO_PROFILE \
  --account-id YOUR_ACCOUNT_ID --region YOUR_REGION --mysql-version APPROVED_PATCH
```

The plan command creates a **new-stack change set**, not paid resources. Review
all changes and a region-specific cost estimate. Existing-stack updates are
intentionally refused by this first-deployment helper. Only after explicit
resource/cost approval:

```bash
python scripts/aws_deploy.py execute --profile YOUR_SSO_PROFILE \
  --account-id YOUR_ACCOUNT_ID --region YOUR_REGION \
  --change-set REVIEWED_CHANGE_SET --approve-costs-and-resources
```

This requests creation; success is not a claim of stack readiness. Wait for
`CREATE_COMPLETE`, then inspect all resources and outputs. Do not automatically
retry failed provisioning or delete retained resources to force success.

## Host and secret preparation

1. Use SSM to access the new EC2 instance. It has no SSH/UI inbound rule. Install
   Docker Engine using the supported Amazon Linux procedure and install a
   reviewed, checksum-verified [Compose plugin](https://docs.docker.com/compose/install/linux/).
   These host changes require the approved deployment scope. No installer is run
   on the Mac. The template itself does not install or start Docker.
2. Check out the reviewed commit on the host. Download the public RDS CA bundle
   from `https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem` into
   `deploy/aws/certs/global-bundle.pem`; inspect its certificate validity. The
   directory is gitignored. Build with
   `docker build -f deploy/aws/Dockerfile -t premier-league:REVIEWED_COMMIT .`.
   The image copies only scripts, DAGs and the three committed archive CSVs.
   It never copies `.env`, private files or live staging. Scan/test the image
   before deployment; no successful image build is claimed yet.
3. After the separately approved database copy and app-account creation, populate
   the stack runtime secret privately with the keys in
   `scripts/aws_runtime_env.py:REQUIRED`. Do not reuse the Mac root account or
   grant ETL DDL/admin access. `DB_HOST` must be the exact RDS endpoint;
   `DB_NAME=soccer_db`; provider and season are `football_data` / `2026`.
4. Generate new cloud-only metadata database and broker passwords, a valid Fernet
   key, and an independent JWT secret. Existing Mac keys/metadata are preserved;
   do not rotate them. New cloud metadata must never pretend to decrypt the old
   metadata with a different key. Metadata migration, if desired, needs its own
   reviewed backup/key recovery procedure.
5. Build URL-encoded metadata/result/broker URIs from those private cloud values:
   `postgresql+psycopg2://airflow:ENCODED_PASSWORD@postgres/airflow`,
   `db+postgresql://airflow:ENCODED_PASSWORD@postgres/airflow`,
   `redis://:ENCODED_PASSWORD@redis:6379/0`. Store these as the three URI keys.
   Verify consistency with the corresponding PostgreSQL/Redis password fields.
6. Set the remaining nonsecret values from stack outputs: immutable
   `PIPELINE_IMAGE`, `AWS_REGION`, `PIPELINE_LOG_GROUP`, a unique
   `LOG_STREAM_PREFIX`, `PIPELINE_RAW_S3_BUCKET`, and 12-digit
   `PIPELINE_S3_EXPECTED_OWNER`. On the cloud host, use a Python environment with
   `requirements-aws.txt` installed to write a new private file:

   ```bash
   mkdir -m 700 -p "$HOME/pipeline-private"
   python scripts/aws_runtime_env.py --region YOUR_REGION \
     --secret-id STACK_RUNTIME_SECRET_ARN \
     --output "$HOME/pipeline-private/cloud.private.json"
   python scripts/aws_compose.py --config "$HOME/pipeline-private/cloud.private.json" -- config --quiet
   ```

   The writer uses mode 0600, rejects repository paths/administrator users,
   validates Fernet, and never overwrites an existing file. Values are stored as
   private JSON and passed via process environment, avoiding dotenv/Compose
   quoting differences for passwords. It prints no secrets.
   Do not print expanded Compose config or turn on shell tracing.
7. Configure the CloudWatch agent on the new host using
   `cloudwatch-agent.json`, replacing its log-group placeholder with the stack
   output. Verify it actually collects every task's JSON log file. Container
   stdout logging alone does not prove Airflow task files reach CloudWatch. The
   candidate instance role permits log-stream creation/writes/descriptions in
   that group; configure the agent to use that existing group, not create groups
   or change retention. Install/start the agent only in the approved host scope.

## Safe database copy and cutover gates

This is a **new target database**, not a modification of local `soccer_db`.
Migrations 003/004 are already applied locally and must not be blindly replayed
on a copied 15-table schema. Copy the complete application database, not `mysql`
users/system tables, and do not delete the local source or backups.

1. Verify the latest local run/checkpoint and all 380 archive fixtures, original
   teams/venues, 380 season-2026 fixture IDs, membership and source maps. Check
   Docker's real state; it was unreachable during preparation. Do not assume a
   previously enabled local DAG is currently executing.
2. Obtain a current backup and restore it to an isolated instance of the exact
   chosen RDS MySQL 8.4 patch. Compare all 15 table definitions/row fingerprints,
   foreign keys, indexes, JSON fields, large unsigned IDs and checkpoints.
   Native local MySQL is 9.3: a cross-version logical import is **not yet proven**.
   Fix/review incompatibilities on disposable copies; never rewrite source rows
   or reset counters to hide differences.
3. Obtain separate approval for a short source-writer freeze. Pause the local DAG,
   verify no active/queued tasks or pending owner, and take the final consistent
   15-table dump. Record checksums, row fingerprints and the cutover checkpoint.
   Upload only the approved protected backup to an approved encrypted location;
   do not add S3 backup permissions to the task role or put dumps in Git.
4. Obtain explicit import approval. Import into the new empty RDS `soccer_db`
   through the controlled operator path. Validate exact source/target equality
   and the trusted archive. Create a distinct least-privileged runtime account
   using separately approved SQL, not the RDS master credentials. Require TLS;
   the cloud connection uses `VERIFY_IDENTITY` with the trusted RDS CA bundle.
5. Keep cloud Airflow paused. Start infrastructure only after approval, initialize
   **new cloud-only metadata** explicitly with `airflow db migrate`, and create
   a unique cloud UI account using private input. Then start/health-check the
   five Airflow services in stages. Never initialize/reset the Mac metadata.
6. Approve one supervised cloud incremental run against RDS. Verify all five
   tasks, immutable raw S3 objects, 380 fixtures per season, unchanged archive,
   uniqueness/mappings, checkpoint commit and CloudWatch task output. Approve a
   repeat run separately and check idempotency. No duplicate owner/writer should
   be active on either database.
7. Approve cloud scheduling only after those checks and notification tests pass.
   The Mac DAG must stay paused while the cloud becomes the authoritative writer.
   Check for an overdue immediate slot; allow only the explicitly approved run.
   Verify the actual next Monday 06:00 UTC execution and later observe its result.
8. Save recovery evidence and metadata/staging-volume backups to an approved
   protected location. RDS backups cover application data, not local EC2 Airflow
   metadata or staging. The retained root EBS volume is not an independent backup.

Rollback before cloud writes: leave cloud paused, keep the target intact for
inspection, and re-enable the unchanged local deployment only with approval.
After cloud writes: pause cloud first; reconcile/checkpoint cloud-only changes
back to an isolated copy before considering an approved reverse cutover. Never
simply unpause a stale local database or restore over either live database.

## Validation and remaining limitations

Local verification on 10 November 2026: **317 tests passed, zero skipped**, with
mocked API/SDK calls and a new socket-only MySQL 9.3 test instance. Only randomly
named test databases were used; the application database was not opened or
modified. The test server was shut down afterward. CloudFormation linting and
cloud Compose configuration validation passed. This does not prove RDS 8.4
restore compatibility or successful cloud execution. New GitHub CI jobs are
prepared locally but have not run on unpublished changes.

```bash
python -m pip install -r requirements-dev.txt 'cfn-lint>=1.60,<2'
python -m pytest
cfn-lint deploy/aws/infrastructure.json
```

CI retains the original MySQL 8.0 integration job and adds MySQL 8.4 plus offline
CloudFormation validation. Test API/SDK calls are mocked or use botocore Stubber;
no AWS credentials are required. Optional S3 archival is off by default in the
Mac deployment and fails closed if enabled but unavailable. Shared run-scoped
POSIX staging remains authoritative; S3 is an audit copy, not a distributed lock.

Not yet verified: AWS entitlement/IAM, region-specific engine availability and
costs, actual stack creation, image build, RDS import, cloud secrets/metadata,
cloud supervised/repeat ingestion, alert delivery, backup restoration from cloud,
or cloud scheduling. CloudWatch alarm notification and DAG failure alerts need
an agreed recipient and implementation before unattended cutover. No cloud
completion or always-on availability is claimed.

Official references: [RDS CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-rds-dbinstance.html),
[S3 conditional PUT](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html),
[MySQL TLS options](https://dev.mysql.com/doc/connector-python/en/connector-python-connectargs.html).
