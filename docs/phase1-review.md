# Premier League Data Engineering Pipeline — Phase 1 Review

## Scope and inspection

Reviewed all tracked Python scripts, the DAG, Dockerfile and Compose configuration, dependency files, environment template, README, architecture/data-model documentation, schema/migrations, analytics queries, license, ignore rules, and the three CSV datasets before implementation. The existing CSV snapshot has 380 matches, 20 teams, and 20 venues. No schema migrations or dataset modifications are part of this phase.

The initial review identified:

| Finding | Phase 1 change |
| --- | --- |
| Local runner stopped after four steps and skipped quality checks | Added the fifth step and per-step status/duration logging |
| Match loader silently dropped bad dates, IDs, and blank names | Reject malformed batches before opening MySQL |
| Duplicate fixture IDs were not rejected before UPSERT | Validate duplicate IDs in extraction and loading |
| Fractional scores/integers could be truncated; negative scores reached MySQL | Validate integer values and reject invalid scores before writing |
| Empty/non-object API responses produced low-level errors or empty staging output | Explicit payload validation and readable failures before CSV writes |
| Teams with no venues caused sorting errors on a frame with no columns | Keep a stable venue CSV schema, including empty optional venue data |
| API error payloads were echoed directly | Report API failures without echoing external error content |
| Cursor creation failure could leave a DB connection open | Close connections even when cursor creation fails |
| DAG was manual only and allowed multiple active runs | Weekly Monday 06:00 UTC cron and one active run |
| No development test dependencies or CI | Added offline pytest suite and Python 3.11 GitHub Actions workflow |
| Airflow environment template omitted documented setup settings | Added `AIRFLOW_UID` and Fernet-key generation guidance |

The existing four runtime dependency pins installed successfully in an isolated environment. They remain unchanged. `requirements-dev.txt` reuses `requirements-airflow.txt` for those runtime dependencies and adds pytest; notebook packages remain optional through `requirements.txt`.

## Implemented behavior

Both execution paths run:

```text
extract matches → extract teams/venues → load teams/venues → load matches → validate data quality
```

Each loader preserves parameterized MySQL UPSERTs and its transaction boundary. A failed step prevents downstream steps. A post-load quality failure marks the run failed but does not undo earlier committed transactions.

Airflow retains the `premier_league_etl` DAG ID, the five tasks, UTC start date, `catchup=False`, two retries, and a five-minute retry delay. Its schedule is `0 6 * * 1`, with `max_active_runs=1`. Manual triggering remains available. Unpause the DAG for scheduled execution.

Operational identifiers such as `soccer_db`, `/opt/soccer`, the DAG filename, and the `soccer-data` volume remain unchanged to preserve existing connections and stored data.

## Verification

Results from this implementation session (2026-11-04, America/Los_Angeles):

| Check | Result |
| --- | --- |
| `python -m pytest` | 106 passed on macOS, Python 3.13.5, pytest 8.4.2 |
| `python -m pip check` | No broken requirements |
| Real Airflow 3.3.1 DAG import | Passed using an isolated temporary installation and `airflow.dag_processing.dagbag.DagBag`; no import errors |
| Real DAG configuration/dependencies | All five tasks chained correctly; Monday 06:00 UTC cron; two retries with 300-second delay; catchup disabled; one active run |
| Python syntax compilation | Passed for all pipeline scripts and the DAG |
| Docker Compose configuration | Passed using the example environment and `config --quiet` |
| Dataset/schema preservation | No changes to tracked CSVs, SQL schemas, or migrations; snapshot preparation test passed |
| Credential review | No token, private-key, or literal-secret findings in tracked/new source files; `.env` untracked and ignored; example credentials remain placeholders |
| `git diff --check` | Passed |
| Python 3.11 / hosted GitHub Actions run | Configured in CI; not executed here because only Python 3.13 is installed and the branch has not been published |
| Container startup / live ETL refresh | Not executed: Docker daemon is stopped; no live API/MySQL refresh was attempted |
| GitHub repository rename | Not completed; manual instructions below |

The existing Compose file still contains its documented Airflow/PostgreSQL local-development defaults; these are not private production credentials. The credential review covers the current source and changes, not a forensic audit of every historical commit.

### Publication verification

Before committing and publishing the Phase 1 branch, Docker daemon access was checked again with host permissions. Docker Desktop's daemon was not running, so Airflow services were not started and a new end-to-end Airflow ETL run could not be verified. No new Airflow task outcomes are claimed.

A read-only connection using the existing private MySQL credentials confirmed:

| Table | Rows | Unique source IDs |
| --- | ---: | ---: |
| `live_matches` | 380 | 380 |
| `teams` | 20 | 20 |
| `venues` | 20 | 20 |

All nine existing post-load data-quality checks passed against MySQL. The local pytest suite also passed again: **106 tests** on Python 3.13.5. These checks confirm the stored snapshot's quality; they do not substitute for an API refresh and successful five-task Airflow run. Existing credentials were read privately without printing their values. The tracked datasets and all SQL files were checked against the branch baseline and remained byte-for-byte unchanged.

The branch is being published for pull-request review against `main`; Python 3.11 hosted CI must be checked on that pull request. No merge is authorized.

Run the offline suite:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```

Validate Compose without a private `.env` or a running Docker daemon:

```bash
ENV_FILE_PATH=.env.example FERNET_KEY='' AIRFLOW_UID=50000 docker compose --env-file .env.example config --quiet
```

With Docker Desktop and the existing Airflow services running:

```bash
docker compose exec airflow-scheduler airflow dags list-import-errors
docker compose exec airflow-scheduler airflow tasks list premier_league_etl
docker compose exec airflow-scheduler airflow dags list-runs premier_league_etl
```

The lightweight tests do not claim to start containers, execute a live ETL refresh, or run hosted GitHub Actions. Check the Actions tab after opening a pull request. Live ETL requires your private API/MySQL configuration and refreshes the staged files; it is intentionally separate from offline testing.

## Changed files

Modified:

```text
.env.example
README.md
dags/soccer_pipeline_dag.py
docs/architecture.md
docs/data-model.md
run_pipeline.py
scripts/api_matches.py
scripts/api_teams.py
scripts/load_live_matches.py
scripts/load_teams.py
scripts/validate_data_quality.py
```

Added:

```text
.github/workflows/tests.yml
docs/phase1-review.md
pytest.ini
requirements-dev.txt
tests/conftest.py
tests/test_api.py
tests/test_dag.py
tests/test_datasets.py
tests/test_db.py
tests/test_loaders.py
tests/test_quality.py
tests/test_runner.py
```

## Repository rename

**Status: not completed.** GitHub metadata still identifies the repository as `Mohamed254-pixel/soccer-data-pipeline`. The available GitHub connector does not expose a repository rename operation, and GitHub CLI is not installed here. Updating the project title and docs does not rename the remote repository.

Rename the existing repository in GitHub:

1. Open [repository Settings](https://github.com/Mohamed254-pixel/soccer-data-pipeline/settings).
2. Under General → Repository name, enter `premier-league-data-pipeline` and select Rename.
3. Confirm GitHub shows `Mohamed254-pixel/premier-league-data-pipeline`.
4. Update About → Description to: `Premier League Data Engineering Pipeline: API-FOOTBALL ETL with Python, Pandas, MySQL, Airflow, Docker, automated quality checks, pytest, and CI.`
5. Update the existing local remote after confirmation:

```bash
git remote set-url origin https://github.com/Mohamed254-pixel/premier-league-data-pipeline.git
git remote -v
```

Then update the README clone URL and this status to reflect the verified rename. Rename the existing repository rather than creating another one; this preserves its history. There is no need to rename the local checkout directory or the database/volume identifiers.

## Branch review and merge

Changes are prepared on `feature/phase1-reliability`; `main` is not merged or modified by this phase. Review the working tree and tests before committing:

```bash
git status --short
git diff --check
git diff
python3 -m pytest
```

After reviewing, stage the Phase 1 files, commit, and publish the branch:

```bash
git add README.md docs .env.example run_pipeline.py dags scripts tests pytest.ini requirements-dev.txt .github/workflows/tests.yml
git commit -m "Add Phase 1 pipeline reliability and automated tests"
git push -u origin feature/phase1-reliability
```

Open a pull request targeting `main`, inspect its file diff and Python 3.11 CI result, and merge only after your approval. No AWS resources, deployments, incremental ingestion, dbt, or Kafka are introduced.

## Planned improvements

- Incremental ETL
- Raw API storage in AWS S3
- Amazon RDS
- dbt transformations
- Additional football datasets
- Freshness monitoring, alerts, and dashboards
- Match-to-team foreign keys in a separately reviewed schema change
