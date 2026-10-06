import numpy as np
import pandas as pd

from episodes import label_episodes
from signals import apply_filters, build_features, track_lows

EP = {"crash_threshold": 0.25, "merge_gap_days": 60}
ST = {"stable_days": 63, "filters": {"vix_max": {"enabled": True, "max": 30},
                                       "above_ma": {"enabled": True, "window": 200},
                                       "min_depth": {"enabled": False}}}


def test_stabilization_and_false_start():
    from tests.conftest import piecewise
    # crash to 60, flat 70 days (stabilizes), new low 55, flat again, recover
    s = piecewise([(0, 100), (50, 60), (51, 60.5), (120, 60.5), (121, 55), (200, 55.5),
                   (400, 105)])
    lab = label_episodes(s, 0.25, 60)
    t = track_lows(s, lab["episode_id"], 63)
    assert t["trigger"].sum() == 2                       # confirmed twice
    assert t["false_starts"].iloc[-1] == 1               # first confirmation was a false start
    first = t.index[t["trigger"]][0]
    assert t.loc[first, "days_since_low"] == 63
    assert t.loc[first, "ep_low"] == s.iloc[50]


def test_filters_toggle_and_fail_closed(noisy_market):
    f = build_features(noisy_market, EP, ST)
    assert "f_vix_max" in f and "f_above_ma" in f and "f_min_depth" not in f
    nm = noisy_market.copy()
    nm["vix"] = np.nan
    assert not build_features(nm, EP, ST)["filters_pass"].any()      # missing VIX => fail
    assert (f.loc[~f.filters_pass, "first_fail"] != "").all()


def test_features_no_lookahead(noisy_market):
    full = build_features(noisy_market, EP, ST)
    for cut in (400, 700, 950, 1150):
        part = build_features(noisy_market.iloc[:cut], EP, ST)
        pd.testing.assert_frame_equal(part, full.iloc[:cut], check_exact=False)
