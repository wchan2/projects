"""Indicators: numeric, causal calculations on price data.

An indicator turns data into a number per day (an RSI value, how far price is below its high, a
moving average). It says nothing about what the number means: that is a signal's job (`signals.py`,
e.g. "RSI below 30" = oversold). Every value at day t uses only data up to day t.

Indicators are plain functions of the history they are given. Nothing is kept between calls, so
there is no hidden state to manage in a backtest; a live system can keep a rolling buffer of bars
or add incremental versions later.
"""

import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's relative strength index, 0-100. High = strong recent gains, low = strong losses.
    Uses exponentially smoothed average gain and loss, so a value depends on all earlier data with
    decaying weight (not just the last `period` closes)."""
    change = close.diff()
    gains = change.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    losses = (-change.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return 100 - 100 / (1 + gains / losses)


def drawdown_from_high(price: pd.Series, lookback_days: int | None = None) -> pd.Series:
    """Fraction `price` is below its high (0 at a high, -0.25 = 25% below). The high is the running
    high of the data, or of the last `lookback_days` days if given."""
    if lookback_days is None:
        high = price.cummax()
    else:
        high = price.rolling(lookback_days, min_periods=1).max()
    return price / high - 1


def moving_average(series: pd.Series, window: int) -> pd.Series:
    """Simple average of the last `window` values (NaN until there are enough)."""
    return series.rolling(window).mean()


def run_length(condition: pd.Series) -> pd.Series:
    """For each day, how many days in a row `condition` has been true up to and including it
    (0 where it is false). A run of three true days counts 1, 2, 3."""
    flags = condition.fillna(False).astype(bool)
    run_id = (~flags).cumsum()  # goes up every false day, so each run of true days shares one id
    return flags.astype(int).groupby(run_id).cumsum()
