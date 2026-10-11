"""Composable signals.

A `Signal` is a reusable, parameterized condition: `signal(data, params)` returns a boolean Series
that is True on the days the condition holds, using only data up to that day (no lookahead).
Signals combine with `all_of`, `any_of`, `not_` and `recently`, and a combination is itself a
Signal, so new strategies are built by composing existing ones:

    entry = all_of(vix_stabilizing, rsi_bounce, deep_dip)

Each leaf signal reads its own namespace of `params` (`params["rsi_bounce"]["oversold"]`), falling
back to its defaults, so sensitivity grids can sweep any signal's parameters by dotted key.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import reduce
from operator import and_, or_

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Signal:
    name: str
    fn: Callable[[pd.DataFrame, dict], pd.Series]
    defaults: dict = field(default_factory=dict)
    parts: tuple[Signal, ...] = ()  # the signals a combination is built from

    def __call__(self, data: pd.DataFrame, params: dict | None = None) -> pd.Series:
        """Boolean Series over data.index. Missing inputs (NaN) count as False."""
        result = self.fn(data, params or {})
        return result.fillna(False).astype(bool)

    def all_defaults(self) -> dict:
        """{signal name: default params} for this signal and everything it is built from."""
        found = {self.name: dict(self.defaults)} if self.defaults else {}
        for part in self.parts:
            found.update(part.all_defaults())
        return found

    def first_failing(self, data: pd.DataFrame, params: dict | None = None) -> pd.Series:
        """Name of the first part (or the signal itself) that is False on each day, '' if none."""
        failing = pd.Series("", index=data.index)
        for part in self.parts or (self,):
            unmet = (failing == "") & ~part(data, params)
            failing = failing.mask(unmet, part.name)
        return failing


def signal(name: str, **defaults):
    """Turn `f(data, **params) -> Series` into a Signal whose params come from `params[name]`."""

    def decorate(fn: Callable[..., pd.Series]) -> Signal:
        def run(data: pd.DataFrame, params: dict) -> pd.Series:
            return fn(data, **{**defaults, **params.get(name, {})})

        return Signal(name, run, defaults)

    return decorate


# ---- combinators --------------------------------------------------------------------------------
def all_of(*signals: Signal) -> Signal:
    names = ", ".join(s.name for s in signals)
    return Signal(
        f"all_of({names})",
        lambda data, params: reduce(and_, (s(data, params) for s in signals)),
        parts=signals,
    )


def any_of(*signals: Signal) -> Signal:
    names = ", ".join(s.name for s in signals)
    return Signal(
        f"any_of({names})",
        lambda data, params: reduce(or_, (s(data, params) for s in signals)),
        parts=signals,
    )


def not_(sig: Signal) -> Signal:
    return Signal(f"not_({sig.name})", lambda data, params: ~sig(data, params), parts=(sig,))


def recently(sig: Signal, days: int) -> Signal:
    """True if `sig` was True on any of the last `days` trading days (today included). Lets
    signals that fire a few days apart still count as agreeing."""

    def run(data: pd.DataFrame, params: dict) -> pd.Series:
        return sig(data, params).astype(float).rolling(days, min_periods=1).max() > 0

    return Signal(f"recently({sig.name}, {days})", run, parts=(sig,))


# ---- the signal library -------------------------------------------------------------------------
@signal("vix_below", limit=30)
def vix_below(data: pd.DataFrame, limit: float) -> pd.Series:
    """VIX closes below `limit` (markets are not in panic)."""
    return data["vix"] < limit


@signal("above_moving_average", window=200)
def above_moving_average(data: pd.DataFrame, window: int) -> pd.Series:
    """The signal series closes above its `window`-day moving average."""
    return data["signal"] > data["signal"].rolling(window).mean()


@signal("deep_dip", min_depth=0.15, lookback_days=None)
def deep_dip(data: pd.DataFrame, min_depth: float, lookback_days: int | None) -> pd.Series:
    """The signal series is at least `min_depth` (fraction) below its high: the running high of
    the data, or the last `lookback_days` days if given."""
    series = data["signal"]
    high = (
        series.cummax()
        if lookback_days is None
        else series.rolling(lookback_days, min_periods=1).max()
    )
    return series / high - 1 <= -min_depth


@signal(
    "vix_stabilizing", spike_level=30, reset_level=20, stable_days=10, pullback=0.25, smooth_days=5
)
def vix_stabilizing(
    data: pd.DataFrame,
    spike_level: float,
    reset_level: float,
    stable_days: int,
    pullback: float,
    smooth_days: int,
) -> pd.Series:
    """A VIX spike that is fading. A spike opens when VIX closes at or above `spike_level` and
    ends when it falls below `reset_level`. Within it, True once VIX peaked at least `stable_days`
    ago, is down `pullback` from the peak, and its `smooth_days`-day average is still falling
    (a gradual decline, not a one-day dip)."""
    vix = data["vix"]
    spike = pd.Series(
        label_windows((vix >= spike_level).to_numpy(), (vix < reset_level).to_numpy()),
        index=data.index,
    )
    peak = track_extreme(vix, spike, "max")
    smooth = vix.rolling(smooth_days).mean()
    return (
        (spike >= 0)
        & (peak["days_since_ref"] >= stable_days)
        & (vix <= peak["ref_value"] * (1 - pullback))
        & (smooth < smooth.shift(smooth_days))
    )


@signal("rsi_bounce", period=14, oversold=30, reset_level=50, stable_days=5, bounce=5)
def rsi_bounce(
    data: pd.DataFrame,
    period: int,
    oversold: float,
    reset_level: float,
    stable_days: int,
    bounce: float,
) -> pd.Series:
    """RSI recovering from oversold. An episode opens when RSI closes below `oversold` and ends
    at `reset_level`. Within it, True once RSI made no new low for `stable_days` and has bounced
    `bounce` points off that low."""
    strength = rsi(data["signal"], period)
    episode = pd.Series(
        label_windows((strength < oversold).to_numpy(), (strength >= reset_level).to_numpy()),
        index=data.index,
    )
    low = track_extreme(strength, episode, "min")
    return (
        (episode >= 0)
        & (low["days_since_ref"] >= stable_days)
        & (strength >= low["ref_value"] + bounce)
    )


# ---- building blocks (causal helpers) -----------------------------------------------------------
def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    change = close.diff()
    gains = change.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    losses = (-change.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return 100 - 100 / (1 + gains / losses)


def label_windows(arm: np.ndarray, disarm: np.ndarray) -> np.ndarray:
    """Episode ids (1-based, -1 = none): an episode opens on the first `arm` day and closes on the
    first later `disarm` day. Causal: the id at t depends only on arm / disarm up to t."""
    ids = np.full(len(arm), -1, dtype=int)
    current, next_id = -1, 1
    for i in range(len(arm)):
        if current < 0:
            if arm[i]:
                current, next_id = next_id, next_id + 1
        elif disarm[i]:
            current = -1
        ids[i] = current
    return ids


def track_extreme(values: pd.Series, episode_id: pd.Series, mode: str) -> pd.DataFrame:
    """Running max (mode="max") or min (mode="min") of `values` inside each episode, the date it
    was set, and trading days since. A value must beat the previous extreme to be a new one."""
    sign = 1.0 if mode == "max" else -1.0
    vals, ep = values.to_numpy(float), episode_id.to_numpy()
    n = len(vals)
    ref = np.full(n, np.nan)
    since = np.full(n, -1)
    ref_pos = np.full(n, -1)
    current, best, best_i = -1, np.nan, -1
    for i in range(n):
        if ep[i] < 0:
            continue
        if ep[i] != current:
            current, best, best_i = ep[i], vals[i], i
        elif sign * vals[i] > sign * best:
            best, best_i = vals[i], i
        ref[i], ref_pos[i], since[i] = best, best_i, i - best_i
    dates = values.index
    return pd.DataFrame(
        {
            "ref_value": ref,
            "ref_date": [dates[j] if j >= 0 else pd.NaT for j in ref_pos],
            "days_since_ref": since,
        },
        index=dates,
    )


def rising_edge(condition: pd.Series) -> pd.Series:
    """True on the first day a condition becomes true (and again after it turns false)."""
    return condition & ~condition.shift(1, fill_value=False)
