"""Check the existing committed snapshot without rewriting it or using MySQL."""

from pathlib import Path

import pandas as pd

from load_live_matches import prepare_rows
from load_teams import prepare_team_rows, prepare_venue_rows


def test_committed_snapshot_remains_loadable():
    root = Path(__file__).resolve().parents[1] / "data"
    matches = prepare_rows(pd.read_csv(root / "live_matches.csv"))
    teams = prepare_team_rows(pd.read_csv(root / "teams.csv"))
    venues = prepare_venue_rows(pd.read_csv(root / "venues.csv"))
    assert (len(matches), len(teams), len(venues)) == (380, 20, 20)
    assert len({row[0] for row in matches}) == 380
    assert {row[9] for row in teams if row[9] is not None} <= {row[0] for row in venues}
