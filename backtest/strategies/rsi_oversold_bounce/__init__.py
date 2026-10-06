"""Buy when RSI is oversold and starts to stabilize.

RSI (Wilder, `rsi_period`) is computed on the signal series. An episode opens when RSI closes below
`oversold` and closes when it recovers to `reset_level`. Inside an episode, the signal fires once:
  * RSI has made no new low for `stable_days` trading days, and
  * RSI has bounced at least `bounce` points off that low.
Then scale in over `buy_weeks` weekly tranches, hold `hold_years`, sell.
"""

import pandas as pd

from signals import episode_summary
from strategy import Context, Strategy, StrategyResult, scale_in, scale_in_anchors

from .signals import build_features

PARAMS = {
    "rsi_period": 14,
    "oversold": 30,  # RSI close below this opens an episode
    "reset_level": 50,  # RSI at or above this closes the episode
    "stable_days": 5,  # trading days since the RSI low
    "bounce": 5,  # RSI points above its low
    "buy_weeks": 8,
    "tranche_step_days": 5,
    "hold_years": 1,
    "chained": True,
    "filters": {},  # optional tranche filters (see signals.py)
}

SENSITIVITY_GRID = {
    "oversold": [25, 30, 35],
    "stable_days": [3, 5, 10],
    "bounce": [3, 5, 8],
    "hold_years": [1, 2],
}


def run(data: pd.DataFrame, params: dict, ctx: Context) -> StrategyResult:
    """data: price, signal, vix, rf."""
    feat = build_features(data, params)
    equity, weights, trades, events = scale_in(feat, params, ctx)
    trades = trades.rename(columns={"ref_value": "rsi_low", "ref_date": "rsi_low_date"})
    anchors = scale_in_anchors(feat, trades)
    return StrategyResult(
        equity,
        weights,
        trades,
        events,
        episode_summary(feat, "rsi_low"),
        anchors,
        eval_start=anchors.get("first_signal"),
    )


STRATEGY = Strategy(
    description=(
        "Buy oversold RSI once it stabilizes: RSI fell below the oversold level, stopped making "
        "new lows and has bounced a few points; scale in, hold a fixed period, then sell."
    ),
    run=run,
    params=PARAMS,
    sensitivity_grid=SENSITIVITY_GRID,
)
