import numpy as np
import pandas as pd
import pytest

from strategies import stabilized_crash_low
from strategy import Context

PARAMS = stabilized_crash_low.PARAMS
CTX = Context()


def piecewise(points, start="2000-01-03"):
    """Business-day series interpolating (n_days, level) waypoints, e.g. [(0,100),(250,150)]."""
    xs, ys = zip(*points, strict=True)
    n = xs[-1] + 1
    idx = pd.bdate_range(start, periods=n)
    return pd.Series(np.interp(np.arange(n), xs, ys), idx, name="IDX")


@pytest.fixture
def known_crashes():
    """Rise to 100; -40% crash and full recovery; a -19% dip (below threshold); rally;
    -30% crash and recovery. Plateaus keep the extrema exact."""
    return piecewise(
        [
            (0, 50),
            (250, 100),
            (350, 60),
            (650, 105),
            (700, 85),
            (800, 120),
            (880, 84),
            (1100, 125),
            (1200, 130),
        ]
    )


@pytest.fixture
def noisy_market(known_crashes):
    rng = np.random.default_rng(1)
    s = known_crashes * np.exp(rng.normal(0, 0.008, len(known_crashes)))
    vix = pd.Series(15 + 60 * (1 - s / s.cummax()), s.index, name="vix").clip(lower=10)
    risk_free = pd.Series(0.02, s.index)
    return pd.DataFrame({"price": 3 * s, "signal": s, "vix": vix, "risk_free": risk_free})


@pytest.fixture
def capitulation_market():
    """A flat market that crashes 40%, bottoms out and starts to rebound while VIX spikes to 50
    and then fades. Built so VIX stabilizing, RSI bouncing and a deep dip all hold at about the
    same time (days ~400-420), then stays flat long enough for a one-year hold to finish."""
    price = piecewise([(0, 100), (300, 100), (360, 60), (400, 60), (440, 75), (800, 75)])
    vix = piecewise([(0, 15), (300, 15), (340, 50), (350, 50), (430, 30), (470, 18), (800, 18)])
    return pd.DataFrame(
        {"price": price, "signal": price, "vix": vix.to_numpy(), "risk_free": 0.02},
    )
