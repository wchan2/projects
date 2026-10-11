"""Buy only when three independent signals agree.

  * `vix_stabilizing`: a VIX spike is fading,
  * `rsi_bounce`:      RSI was oversold and is recovering,
  * `deep_dip`:        the index is well below its recent high.

Each fires on its own schedule, so the two timing signals count if they fired within the last
`CONFIRMATION_DAYS` trading days. The dip must hold on the day itself.
"""

from signals import all_of, deep_dip, recently, rsi_bounce, vix_stabilizing
from strategy import scale_in_strategy

CONFIRMATION_DAYS = 10

STRATEGY = scale_in_strategy(
    description=(
        "Buy only when VIX has stabilized after a spike, RSI is bouncing off oversold, and the "
        "index is in a deep dip, all at about the same time; scale in, hold, then sell."
    ),
    entry=all_of(
        recently(vix_stabilizing, CONFIRMATION_DAYS),
        recently(rsi_bounce, CONFIRMATION_DAYS),
        deep_dip,
    ),
    signal_params={"deep_dip": {"min_depth": 0.15, "lookback_days": 252}},
    sensitivity_grid={
        "deep_dip.min_depth": [0.10, 0.15, 0.20],
        "vix_stabilizing.spike_level": [25, 30],
        "rsi_bounce.oversold": [30, 35],
        "hold_years": [1, 2],
    },
)
