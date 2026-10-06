"""Buy the stabilized crash low.

The signal index falls >= `crash_threshold` below its all-time high (an episode). Once it has
made no new low for `stable_days` trading days, scale in over `buy_weeks` weekly tranches
(each checked against the filters), hold `hold_years` from the first tranche, then sell.
Proceeds are redeployed at the next qualifying episode (`chained`).
"""

import pandas as pd

from strategy import Context, Strategy, StrategyResult, scale_in, scale_in_anchors

from .episodes import detect_crash_episodes
from .signals import build_features

PARAMS = {
    # episode detection (periods are auto-selected from the signal index)
    "crash_threshold": 0.25,  # CRASH_THRESHOLD
    "merge_gap_days": 60,  # MERGE_GAP_DAYS (calendar days between recovery and next start)
    "override": [],  # e.g. [{"start": "2000-03-10", "end": "2003-01-01"}]; empty = auto-detect
    # entry / exit
    "stable_days": 63,  # STABLE_DAYS: trading days with no new low
    "buy_weeks": 8,  # BUY_WEEKS: equal tranches, one per week
    "tranche_step_days": 5,
    "hold_years": 2,  # HOLD_YEARS after the first tranche
    "chained": True,  # proceeds redeployed at the next qualifying episode
    "filters": {  # registered in signals.py
        "vix_max": {"enabled": True, "max": 30},
        "above_ma": {"enabled": False, "window": 200},
        "min_depth": {"enabled": True, "min_depth": 0.15},
    },
}

SENSITIVITY_GRID = {
    "crash_threshold": [0.20, 0.25, 0.30],
    "stable_days": [42, 63, 84],
    "hold_years": [2, 3],
    "filters.vix_max.max": [25, 30, 40],
}


def run(data: pd.DataFrame, params: dict, ctx: Context) -> StrategyResult:
    """data: price, signal, vix, risk_free."""
    feat = build_features(data, params)
    feat["ref_value"], feat["ref_date"] = feat["ep_low"], feat["ep_low_date"]
    table = detect_crash_episodes(
        data["signal"],
        data["vix"],
        params["crash_threshold"],
        params["merge_gap_days"],
        override=params.get("override") or None,
    )
    equity, weights, trades, events = scale_in(feat, params, ctx)
    trades = trades.rename(columns={"ref_value": "low", "ref_date": "low_date"})

    if len(table):  # same ids in labels, events and table
        false_starts = feat.groupby("episode_id")["false_starts"].max()
        confirmed = feat[feat["trigger"]].groupby("episode_id").size()
        table["false_starts"] = table["episode_id"].map(false_starts).fillna(0).astype(int)
        table["stabilizations_confirmed"] = table["episode_id"].map(confirmed).fillna(0).astype(int)

    anchors = scale_in_anchors(feat, trades)
    if len(table):
        anchors["first_low"] = table["trough_date"].iloc[0]
    return StrategyResult(
        equity,
        weights,
        trades,
        events,
        table,
        anchors,
        eval_start=anchors.get("first_signal"),
    )


STRATEGY = Strategy(
    description=(
        "Buy the stabilized crash low: after a crash stabilizes (no new low for a few months), "
        "scale in over several weeks, hold a fixed period, then sell."
    ),
    run=run,
    params=PARAMS,
    sensitivity_grid=SENSITIVITY_GRID,
)
