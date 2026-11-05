from pathlib import Path
import logging
import os
import subprocess
import sys
from time import perf_counter
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)


def run_step(label, script_path):
    started = perf_counter()
    LOGGER.info("START | %s", label)
    try:
        subprocess.run(
            [sys.executable, "-u", str(script_path)],
            cwd=PROJECT_ROOT,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        LOGGER.exception("FAIL | %s | duration=%.2fs", label, perf_counter() - started)
        raise SystemExit(getattr(exc, "returncode", 1) or 1) from exc
    LOGGER.info("SUCCESS | %s | duration=%.2fs", label, perf_counter() - started)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    os.environ.setdefault("PIPELINE_RUN_ID", "local-" + str(uuid4()))
    LOGGER.info("Run ID: %s", os.environ["PIPELINE_RUN_ID"])
    run_step(
        "Step 1: Pulling match data from API-FOOTBALL...",
        PROJECT_ROOT / "scripts" / "api_matches.py",
    )

    run_step(
        "Step 2: Pulling team and venue data from API-FOOTBALL...",
        PROJECT_ROOT / "scripts" / "api_teams.py",
    )

    run_step(
        "Step 3: Loading teams and venues into MySQL...",
        PROJECT_ROOT / "scripts" / "load_teams.py",
    )

    run_step(
        "Step 4: Loading matches into MySQL...",
        PROJECT_ROOT / "scripts" / "load_live_matches.py",
    )

    run_step(
        "Step 5: Validating data quality...",
        PROJECT_ROOT / "scripts" / "validate_data_quality.py",
    )

    LOGGER.info("Pipeline completed successfully.")


if __name__ == "__main__":
    main()
