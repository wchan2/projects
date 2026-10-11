import pandas as pd

from strategies.stabilized_crash_low.episodes import label_episodes
from strategies.stabilized_crash_low.signals import build_features, track_lows
from tests.conftest import piecewise

P = {"crash_threshold": 0.25, "merge_gap_days": 60, "stable_days": 63}


def test_stabilization_and_false_start():

    # crash to 60, flat 70 days (stabilizes), new low 55, flat again, recover
    s = piecewise([(0, 100), (50, 60), (51, 60.5), (120, 60.5), (121, 55), (200, 55.5), (400, 105)])
    lab = label_episodes(s, 0.25, 60)
    t = track_lows(s, lab["episode_id"], 63)
    assert t["trigger"].sum() == 2  # confirmed twice
    assert t["false_starts"].iloc[-1] == 1  # first confirmation was a false start
    first = t.index[t["trigger"]][0]
    assert t.loc[first, "days_since_low"] == 63
    assert t.loc[first, "ep_low"] == s.iloc[50]


def test_features_no_lookahead(noisy_market):
    full = build_features(noisy_market, P)
    for cut in (400, 700, 950, 1150):
        part = build_features(noisy_market.iloc[:cut], P)
        pd.testing.assert_frame_equal(part, full.iloc[:cut], check_exact=False)
