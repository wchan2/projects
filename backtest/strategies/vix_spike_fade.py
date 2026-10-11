"""Buy when a VIX spike starts to fade: VIX closed above 30, peaked, and has been drifting down
gradually (see `vix_stabilizing`). Scale in, hold a year, sell."""

from signals import vix_stabilizing
from strategy import scale_in_strategy

STRATEGY = scale_in_strategy(
    description=(
        "Buy a VIX spike once it stabilizes: VIX passed a spike level, peaked, and has been "
        "drifting down gradually for several days; scale in, hold a fixed period, then sell."
    ),
    entry=vix_stabilizing,
    sensitivity_grid={
        "vix_stabilizing.spike_level": [25, 30, 40],
        "vix_stabilizing.stable_days": [5, 10, 20],
        "vix_stabilizing.pullback": [0.15, 0.25, 0.35],
        "hold_years": [1, 2],
    },
)
