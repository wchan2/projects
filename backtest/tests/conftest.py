import numpy as np
import pandas as pd
import pytest


def piecewise(points, start="2000-01-03"):
    """Business-day series interpolating (n_days, level) waypoints, e.g. [(0,100),(250,150)]."""
    xs, ys = zip(*points)
    n = xs[-1] + 1
    idx = pd.bdate_range(start, periods=n)
    return pd.Series(np.interp(np.arange(n), xs, ys), idx, name="IDX")


@pytest.fixture
def known_crashes():
    """Rise to 100; -40% crash and full recovery; a -19% dip (below threshold); rally;
    -30% crash and recovery. Plateaus keep the extrema exact."""
    return piecewise([(0, 50), (250, 100), (350, 60), (650, 105),
                      (700, 85), (800, 120), (880, 84), (1100, 125), (1200, 130)])


@pytest.fixture
def noisy_market(known_crashes):
    rng = np.random.default_rng(1)
    s = known_crashes * np.exp(rng.normal(0, 0.008, len(known_crashes)))
    vix = pd.Series(15 + 60 * (1 - s / s.cummax()), s.index, name="vix").clip(lower=10)
    rf = pd.Series(0.02, s.index)
    return pd.DataFrame({"price": 3 * s, "signal": s, "vix": vix, "rf": rf})
