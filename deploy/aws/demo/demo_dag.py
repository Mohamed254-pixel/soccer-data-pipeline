"""Build a manual-only copy of the existing DAG, retaining the task graph."""
import re
import sys
from pathlib import Path


def render(source):
    for pattern, value in (
        (r'dag_id="premier_league_etl"', 'dag_id="premier_league_demo"'),
        (r'schedule="[^"]+"', 'schedule=None'),
    ):
        source, count = re.subn(pattern, value, source)
        if count != 1:
            raise ValueError(f"Expected one DAG setting matching {pattern}")
    return source


if __name__ == "__main__":
    Path(sys.argv[2]).write_text(render(Path(sys.argv[1]).read_text()))
