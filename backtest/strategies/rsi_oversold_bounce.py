"""Buy when RSI is oversold and starts to recover (see `rsi_bounce`). Scale in, hold, sell."""

from signals import rsi_bounce
from strategy import scale_in_strategy

STRATEGY = scale_in_strategy(
    description=(
        "Buy oversold RSI once it stabilizes: RSI fell below the oversold level, stopped making "
        "new lows and has bounced a few points; scale in, hold a fixed period, then sell."
    ),
    entry=rsi_bounce,
    sensitivity_grid={
        "rsi_bounce.oversold": [25, 30, 35],
        "rsi_bounce.stable_days": [3, 5, 10],
        "rsi_bounce.bounce": [3, 5, 8],
        "hold_years": [1, 2],
    },
)
