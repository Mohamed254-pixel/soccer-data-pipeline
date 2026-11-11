# Phase 3 AWS deployment review

Reviewed November 10, 2026 for the Premier League Data Pipeline at `9c039a4`.
This is the pre-deployment review. The isolated EC2 demo was subsequently
deployed and verified through startup. See the [AWS demo evidence](portfolio/phase3/README.md)
for the current verified results.

## Verified baseline

- STS verified the selected project account using temporary credentials on
  `soccer-data-pipeline`. Its configured Region is Ohio (`us-east-2`).
- AWS Free Tier returned **FREE / ACTIVE**, **$120.00** remaining, and a plan
  expiration of **May 10, 2027 UTC**. Credit exhaustion can end the plan earlier.
  Export the demo evidence and recoverable data before either event.
- AWS Budgets returned a **$10 monthly** budget. The queried legacy IncludeCredit
  field was null. Verify the current filters, actual spend, and alert recipient
  in Billing before launch. Treat $10 as a **gross usage** ceiling. A budget
  alert can arrive after usage has accrued.
- The Ohio EC2 eligibility query returned `c7i-flex.large` and
  `m7i-flex.large` among the eligible sizes. Neither `t3.large` nor
  `t3.xlarge`, the template's only allowed sizes, appeared. Treat that as a
  provisioning blocker for the existing template on this plan.
- RDS reported orderable MySQL 8.4 / `db.t4g.micro` / gp3 combinations, including
  8.4.13. Orderability shows regional availability. It leaves project policy,
  launch permission, capacity, and actual restore compatibility to verify.
  CloudFormation validated the existing template and reported `CAPABILITY_IAM`.
  Validation leaves provisioning and IAM authorization untested.
- The local MySQL 9.3.0 socket answered a read-only transaction. The application
  has 15 tables and 380 fixtures each for seasons 2024 and 2026.
  `pipeline_control` is enabled, has no pending owner, and last completed on
  November 7 at 05:09:02 UTC. The Mac's main checkout was clean. The Phase 3
  candidate has no changes to the tracked local DAG, Compose, SQL or dataset
  files relative to main. Docker was unreachable, so current Airflow service,
  pause and run history could not be queried. No local services were started,
  paused, or reconfigured. The 317 passing tests are the previous recorded result.

[AWS Free plan FAQ](https://aws.amazon.com/free/free-tier-faqs/) ·
[Eligible EC2 sizes and EBS types](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html) ·
[AWS Budgets timing](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)

## Free plan and Ohio cost

The new AWS experience has service and feature limits enforced by project
policies. Its Free plan covers access to EC2/EBS, RDS, S3, VPC, CloudFormation,
Systems Manager, Secrets Manager and CloudWatch, subject to those policies.
The published list also includes Lambda, EventBridge, DynamoDB and Athena.
Eligible EC2 sizes and gp3 can still consume credits. RDS micro and small
storage configurations should be checked against the project's Free-plan
console choices before any create call. The legacy 750-hour RDS entitlement
does not apply as a planning assumption for this project. Use regional S3,
with bounded versions and results retention. Use the project Region for every
regional resource. Retain the template's internet gateway and avoid NAT,
load balancers, interface endpoints and managed Airflow for this demo.

[AWS supported services](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html) ·
[Project policy restrictions](https://docs.aws.amazon.com/accounts/latest/reference/scps-and-rcps-for-projects.html) ·
[RDS Free Tier terms](https://aws.amazon.com/rds/faqs/)

### Full candidate, 730 hours per month

| Item | Ohio rate and assumption | Gross/month |
|---|---|---:|
| EC2 Linux `t3.large` | $0.0832/hour | $60.74 |
| Single-AZ RDS MySQL `db.t4g.micro` | $0.016/hour | $11.68 |
| EC2 gp3 | 40 GiB at $0.08 | $3.20 |
| RDS gp3 | 20 GiB at $0.115, up to 30 GiB with autoscaling | $2.30–$3.45 |
| EC2 public IPv4 | One auto-assigned address at $0.005/hour | $3.65 |
| Secrets Manager | Runtime plus managed RDS administrator secret | $0.80 + API calls |
| S3 Standard | 1 GB, 1,000 PUTs and 1,000 GETs, including versions in storage estimate | ~$0.03 |
| CloudWatch | 1 GB standard log ingestion, one standard alarm, small log storage | ~$0.60–$0.65 |
| **Total** | Before credits, free allowances, taxes, transfer or excess backups | **~$83–$84** |

EC2 compute and RDS compute each exceed the whole monthly budget. An Ohio
public NAT gateway plus its IPv4 would add $36.50/month before data processing.
This template has no NAT. Cross-AZ DB traffic, retained backups and EBS volumes,
S3 versions, RDS CPU credits, EC2 surplus CPU credits, and log growth are extra.
Keep the database in the host's AZ if the full design is ever approved and the
availability tradeoff is acceptable. RDS auto-starts after seven consecutive
days stopped. Storage and backups still accrue while stopped.

EC2, EBS, RDS instance and RDS storage rates were queried from the AWS Price
List API for Ohio on the review date. The pricing endpoint in `us-east-1`
served Ohio product metadata. The estimates assume low volume and exclude
unrelated usage in this AWS project.

[AWS Price List API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/using-price-list-query-api.html) ·
[VPC pricing](https://aws.amazon.com/vpc/pricing/) ·
[RDS pricing](https://aws.amazon.com/rds/mysql/pricing/) ·
[Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/) ·
[S3 pricing](https://aws.amazon.com/s3/pricing/) ·
[CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/) ·
[RDS stop and restart behavior](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StopInstance.html)

## Architecture decision

**Recommended first deployment: a time-boxed EC2 demo with Airflow, local-to-EC2
MySQL, and private S3.** Use one eligible x86 `c7i-flex.large` at
$0.08479/hour, 20 GiB encrypted gp3, an auto-assigned public IPv4 with zero
inbound rules, and SSM for administration and localhost UI forwarding.
Use Airflow LocalExecutor with Postgres metadata and measured, low concurrency.
Remove Redis, Celery workers and RDS from the demo configuration. Keep MySQL
on an internal Docker network with no published port and a distinct application
user. The host needs 4 GiB memory fit and 20 GiB disk headroom proven with the
actual image and representative data. Reprice before substituting a larger
host or disk. This preserves the five-task DAG, Python transformations,
relational tables and upserts, incremental checkpoint, quality checks, and
immutable raw archives. Keep the demo writer confined to its own database and
its own S3 prefix. Obtain permission before a live provider call, including
whether the Mac and cloud can share the API quota during the demo.

Budget model: **$5.75** for 32 running hours in a 730-hour month, with one
20 GiB disk retained for the whole month ($1.60), one secret ($0.40), low-volume
logs/one alarm (~$0.60), S3 (~$0.03), and $0.25 for small backup/API usage.
The same assumptions yield **$7.19** at 48 hours and **$68.43** if left running.
Use 32 hours as the initial approved envelope, reserve the balance for
variance, and check gross project spend before each run. Stop after evidence
collection and verify `stopped`. Set a dated reminder and pre-approve a
cloud-local OS shutdown timer with EC2 instance-initiated shutdown set to
`stop`. Use the timer as a backup for the manual stop, verify it in a trial,
and keep the cloud DAG paused except for the explicitly approved test.
A stopped host has no live UI or scheduler. Capture a DAG graph, run history,
SQL results and S3 lineage for asynchronous recruiter review. Single-host
failure can affect both Airflow metadata and application data, so rehearse an
encrypted backup and restore.

**Lowest recurring cost if unattended execution is essential:** EventBridge
Scheduler → non-VPC Lambda → private S3, with DynamoDB conditional checkpoint/
lease updates and optional Athena over versioned, partitioned Parquet. Budget
**under $2/month** for a weekly workload modeled at 8 invocations including
retries, 120 seconds each at 1 GB, 1 GB of combined S3/log input per month or
less, one secret, and a 1 GB Athena scan ceiling across the month's demo
queries. Verify volumes and applicable allowances before launch. There is no
NAT or dedicated IPv4. This requires a rewrite of orchestration, state and
relational publication. Preserve incremental extraction, immutable raw
objects, idempotent validated publication and SQL analytics. Athena replaces
the cloud MySQL serving path and screenshots from the existing Airflow
pipeline can document the original orchestration. Use bounded retry, concurrency
and scan controls. Validate Lambda runtime limits and provider behavior before
selecting this design.

**Full EC2 + RDS + S3** gives managed database backups, private RDS connectivity,
independent storage and a continuously available Airflow scheduler. It
requires a Free-plan-eligible compute redesign plus a higher gross budget for
always-on operation. A short EC2 + RDS lab could use fewer compute hours but
adds restore time, retained storage, a second secret and the seven-day restart
risk. It provides little extra demonstration value unless managed RDS is a
specific requirement. A Mac scheduler writing to S3 is inexpensive and keeps
Airflow, but the run still depends on the Mac and does not show cloud-hosted
execution.

[Lambda pricing](https://aws.amazon.com/lambda/pricing/) ·
[EventBridge pricing](https://aws.amazon.com/eventbridge/pricing/) ·
[DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/on-demand/) ·
[Athena pricing](https://aws.amazon.com/athena/pricing/)

## Security review and required changes for the demo

- Retain IMDSv2, encrypted EBS and zero inbound host rules. Use SSM for
  scoped operator sessions and forward the loopback UI. Keep database and
  metadata ports unexposed. HTTPS egress covers the source API and AWS
  service calls. Verify package/image pulls and SSM from the proposed subnet.
  For the full design, RDS is encrypted, private, restricted to the host SG
  on 3306, and uses `require_secure_transport` with CA and endpoint identity
  verification. The template's host 3306 egress covers the VPC CIDR. Narrow
  it to the DB security group if the full design is pursued.
- The host policy limits S3 to `raw/*` get/put, secret retrieval to one ARN,
  and logs to the designated group. It grants SSM agent permissions and
  leaves the managed RDS admin secret and S3 deletes with operators.
  Containers able to reach IMDS can share the instance-role permissions at
  hop limit 2. Document that boundary and test which processes can access
  metadata. Restrict access to the trusted writer or move S3 operations
  behind a host-side helper if stronger isolation is needed. Keep Docker
  socket access out of task containers. Use the current human role only
  under the approved deploy scope. Scope any deployment role and PassRole
  to the reviewed resources.
- Keep S3 Block Public Access, ACLs disabled, SSE-S3, TLS-only and versioning.
  Conditional PUT and digest verification protect normal application retries.
  The role can still issue ordinary PUTs. Require conditional PUT at the
  bucket policy for the writer if immutability must be enforced beyond the
  app. Set reviewed demo expiration for current and noncurrent versions and
  delete markers, with a separate evidence export.
- Use one demo runtime secret with cloud-only DB and Airflow credentials.
  Keep API tokens out of dumps, images, command-line arguments, logs and
  artifacts. The current writer creates a mode-0600 file and Compose passes
  values in environment variables, which Docker administrators can inspect.
  Restrict host/SSM access, avoid logging expanded config, and protect or
  remove temporary secret material on teardown. Do not use DB root for ETL.
- Before the full design is reused, align RDS log export with explicit
  retention on the separate RDS log groups. Verify whether slow-query
  collection is actually enabled. The EC2 alarm has no notification target.
  Test delivery to an approved recipient before any unattended schedule.
- If the helper is reused, bind execution approval to the exact change-set
  ARN **and parameters** (engine version, compute size, storage and Region).
  The current helper validates template equality and Add actions. Its
  execution path does not compare parameter values to an approved manifest.
  Record the resolved AMI and review the actual resource changes before execution.

## Execution and verification after approval

1. Build the separate demo template/Compose profile at a reviewed revision.
   Lint it and run isolated tests with no production secrets. Build the pinned
   x86 image. Exercise the five tasks with an isolated MySQL restore, fake API
   and temporary raw storage. Verify boot time, CPU, memory, free disk and
   logging limits on representative data. Use committed archive fixtures or
   a separately approved sanitized seed as the default demo input.
2. Recheck STS identity, Ohio class/AMI eligibility, budget configuration,
   current usage and Free-plan expiry. Tag the stack with project, purpose and
   expiry. Review exact resource IDs/parameters and the change set. Allow only
   one host, one 20 GiB disk, one public IP while running, one bucket, one
   secret and bounded logging, plus the supporting networking and IAM.
3. Provision the isolated stack, confirm SSM, no inbound ports, encrypted
   storage, private S3 and restricted metadata access. Use fresh cloud-only
   Airflow metadata. Verify approved secret injection and private MySQL
   connectivity. Keep the DAG paused until the supervised run mechanism is
   ready. Select explicit manual test runs and return to paused state.
4. Run bootstrap/incremental validation, then repeat the same logical input.
   Check task success, fixture identities, archive counts, unique keys and
   foreign keys, S3 digests, unchanged rows after the repeat, and checkpoint
   advancement only after quality checks. Test a failure and safe recovery on
   disposable data. Capture redacted screenshots, SQL evidence and S3 object
   lineage. Stop the host and verify state. Check gross usage again after
   billing data catches up.
5. If an authoritative cutover is ever requested, approve that separately.
   For RDS, rehearse the MySQL 9.3 → 8.4 logical restore to the exact target
   patch and compare all 15 schemas, fingerprints and checkpoints. Require an
   approved source-writer freeze, import, supervised and repeat runs, then
   approved scheduling after alert and restore tests. For the first demo the
   Mac stays independent throughout.

## Rollback, cleanup and approvals

A failed demo stays isolated. Disable its triggers, let in-flight work finish
or fence the pending owner, capture sanitized diagnostics, stop the host, and
restore only into a fresh demo database from the last verified export if
needed. For a future authoritative cutover, preserve the source checkpoint.
Before cloud writes, restore local scheduling only under the cutover approval.
After cloud writes, stop the cloud writer and reconcile cloud-only changes in
an isolated restore before any reverse cutover.

Approve the export and retention policy before stack creation. At teardown,
verify the export is recoverable, delete the stack and inspect retained
resources by ID. Delete approved orphan EBS volumes/snapshots and release
any allocated IP. Empty approved S3 buckets by removing **all versions and
delete markers** and abort incomplete multipart uploads before bucket
deletion. Remove approved runtime secrets, log groups, alarms and unused roles
or subscriptions. For the full template, disable RDS deletion protection
under the teardown approval, record the final snapshot choice, and account
for retained RDS snapshots/automated backups and separate log groups.
Inventory Ohio and check billing again after metering catches up.

Before any deployment, approve:

1. **Design and spend** — isolated EC2 demo, Ohio, 32 running hours, $10 gross
   monthly ceiling, stopping deadline and evidence retention.
2. **Exact infrastructure and IAM** — reviewed revision, parameters, resource
   list, named role policies and permitted SSM operators. Approve creation
   of the change set, then its exact execution after review. Budget or alert
   edits require approval if needed.
3. **Data and execution** — chosen seed or sanitized export, secret entry,
   any live provider API usage, and the supervised test/repeat. Approve any
   recurring cloud schedule, authoritative cutover, or Mac schedule change
   separately.
4. **Teardown** — deadline, approved exports, retained resources and explicit
   deletion scope. Any code push also requires approval.
