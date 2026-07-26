from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parent


def run_step(label, script):
    print(f"\n{label}")
    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / script)],
        cwd=PROJECT_ROOT,
        check=True,
    )


def main():
    try:
        run_step("Step 1: Pulling API data...", "api_matches.py")
        run_step("Step 2: Loading into MySQL...", "load_live_matches.py")
    except subprocess.CalledProcessError as exc:
        print(f"\nPipeline stopped because a step failed (exit code {exc.returncode}).")
        return exc.returncode

    print("\nPipeline complete!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
