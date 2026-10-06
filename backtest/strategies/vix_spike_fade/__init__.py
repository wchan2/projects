"""Buy when a VIX spike starts to stabilize.

An episode opens when VIX closes at or above `spike_level` and closes when it falls below
`reset_level`. Inside an episode, the signal fires once all of these hold:
  * VIX peaked at least `stable_days` trading days ago (no new VIX high since),
  * VIX has come down at least `pullback` (fraction) from that peak,
  * its `smooth_days`-day average is lower than it was `smooth_days` days ago (still drifting
    down, i.e. a gradual decline rather than a one-day dip).
Then scale in over `buy_weeks` weekly tranches, hold `hold_years`, sell.
"""

import pandas as pd

from signals import episode_summary
from strategy import Context, Strategy, StrategyResult, scale_in, scale_in_anchors

from .signals import build_features

PARAMS = {
    "spike_level": 30,  # VIX close that opens an episode
    "reset_level": 20,  # VIX close below this closes the episode
    "stable_days": 10,  # trading days since the VIX peak
    "pullback": 0.25,  # required fall from the VIX peak
    "smooth_days": 5,  # trend window: SMA(vix) must be falling over this many days
    "buy_weeks": 8,
    "tranche_step_days": 5,
    "hold_years": 1,
    "chained": True,
    "filters": {},  # optional tranche filters (see signals.py)
}

SENSITIVITY_GRID = {
    "spike_level": [25, 30, 40],
    "stable_days": [5, 10, 20],
    "pullback": [0.15, 0.25, 0.35],
    "hold_years": [1, 2],
}


def run(data: pd.DataFrame, params: dict, ctx: Context) -> StrategyResult:
    """data: price, signal, vix, rf."""
    feat = build_features(data, params)
    equity, weights, trades, events = scale_in(feat, params, ctx)
    trades = trades.rename(columns={"ref_value": "vix_peak", "ref_date": "vix_peak_date"})
    anchors = scale_in_anchors(feat, trades)
    return StrategyResult(
        equity,
        weights,
        trades,
        events,
        episode_summary(feat, "vix_peak"),
        anchors,
        eval_start=anchors.get("first_signal"),
    )


STRATEGY = Strategy(
    description=(
        "Buy a VIX spike once it stabilizes: VIX passed a spike level, peaked, and has been "
        "drifting down gradually for several days; scale in, hold a fixed period, then sell."
    ),
    run=run,
    params=PARAMS,
    sensitivity_grid=SENSITIVITY_GRID,
)
