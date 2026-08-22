from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parent


def run_step(label, script_path):
    print(f"\n{label}")

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=PROJECT_ROOT,
    )

    if result.returncode != 0:
        raise SystemExit(
            f"\nPipeline stopped because a step failed "
            f"(exit code {result.returncode})."
        )


def main():
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

    print("\nPipeline completed successfully.")


if __name__ == "__main__":
    main()