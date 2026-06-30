import subprocess

print("Step 1: Pulling API data...")
subprocess.run(["python3", "scripts/api_matches.py"])

print("Step 2: Loading into MySQL...")
subprocess.run(["python3", "scripts/load_live_matches.py"])

print("Pipeline complete!")