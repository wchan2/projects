"""Strategy contract and the shared scale-in / timed-exit engine.

A strategy is a `Strategy` object: a description, default `params`, a
`run(data, params, ctx) -> StrategyResult` function and its own sensitivity grid. Feed `run` the
standard dataset (price, signal, vix, rf) and extract performance with `metrics.performance`.

Strategies live in `strategies/`. The ones built on "wait for a signal, scale in, hold, sell" only
need to produce a feature frame and hand it to `scale_in()`.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from portfolio import EventLog, Portfolio


@dataclass(frozen=True)
class Context:
    """Backtest-wide settings shared by every strategy."""

    initial_capital: float = 10_000
    trading_days: int = 252
    execution_lag: int = 1  # decided at close t, filled at close t+lag
    cash_earns_rf: bool = True  # False = cash earns 0
    cost_bps: float = 0.0  # slippage per fill; taxes are not modelled


@dataclass
class StrategyResult:
    equity: pd.Series | None  # None for standalone (non-chained) runs
    weights: pd.Series | None  # fraction of equity in the instrument at each close
    trades: pd.DataFrame
    events: pd.DataFrame  # triggered / tranche_skipped / skipped / no_entry ...
    episodes: pd.DataFrame | None  # the strategy's detected episodes, if it has them
    anchors: dict = field(default_factory=dict)  # dates for the buy-and-hold comparisons
    eval_start: pd.Timestamp | None = None  # where performance is measured from


@dataclass(frozen=True)
class Strategy:
    """`sensitivity_grid` maps (dotted) param names to the values to sweep. It lives with the
    strategy because only the strategy knows which of its parameters matter."""

    description: str
    run: Callable[[pd.DataFrame, dict, Context], StrategyResult]
    params: dict
    sensitivity_grid: dict = field(default_factory=dict)


def equity_from_weights(
    price: pd.Series,
    rf: pd.Series,
    weights: pd.Series,
    ctx: Context,
) -> pd.Series:
    """Equity of a book that holds `weights[t-1]` of the instrument over day t (weights are
    post-trade at each close) and keeps the rest in cash."""
    returns = price.pct_change().fillna(0)
    cash_returns = (rf.shift(1) / ctx.trading_days).fillna(0) if ctx.cash_earns_rf else 0 * returns
    held = weights.shift(1).fillna(0)
    turnover = weights.diff().abs().fillna(weights.abs())
    daily = held * returns + (1 - held) * cash_returns - turnover * ctx.cost_bps / 1e4
    return (ctx.initial_capital * (1 + daily).cumprod()).rename("equity")


# ---- scale-in / timed-exit engine ----------------------------------------------------------------
# Required feature columns: price, rf, vix, episode_id (-1 = none), trigger, filters_pass,
# first_fail, ref_value, ref_date (the signal's reference level, recorded on the trade).
# Required params: buy_weeks, tranche_step_days, hold_years, chained.


def tranche_days(trigger_idx: int, n: int, step: int) -> list[int]:
    return [trigger_idx + k * step for k in range(n)]


def exit_index(
    dates: pd.DatetimeIndex,
    entry_idx: int,
    hold_years: float,
) -> int:
    """First trading day >= entry + hold_years (== len(dates) if beyond the data)."""
    target = dates[entry_idx] + pd.DateOffset(months=round(hold_years * 12))
    return int(dates.searchsorted(target))


def scale_in(
    feat: pd.DataFrame,
    params: dict,
    ctx: Context,
) -> tuple[pd.Series | None, pd.Series | None, pd.DataFrame, pd.DataFrame]:
    """Run the engine. Returns (equity, weights, trades, events). With `chained: false` each
    episode is its own standalone account and equity / weights are None."""
    if params["chained"]:
        equity, weights, trades, log = _simulate(feat, params, ctx)
        return equity, weights, pd.DataFrame(trades), log.frame()

    trades, frames = [], []
    for ep in sorted(e for e in feat["episode_id"].unique() if e >= 0):
        _, _, t, log = _simulate(feat, params, ctx, only_episode=int(ep))
        trades += t
        frames.append(log.frame())
    events = pd.concat(frames, ignore_index=True) if frames else EventLog().frame()
    return None, None, pd.DataFrame(trades), events


def scale_in_anchors(feat: pd.DataFrame, trades: pd.DataFrame) -> dict:
    """Dates used by the buy-and-hold comparisons."""
    anchors = {}
    trigger_dates = feat.index[feat["trigger"]]
    if len(trigger_dates):
        anchors["first_signal"] = trigger_dates[0]
    if len(trades):
        anchors["first_entry"] = trades["entry_start"].min()
    return anchors


def _simulate(
    feat: pd.DataFrame,
    params: dict,
    ctx: Context,
    only_episode: int | None = None,
):
    """Day loop. Order each day: accrue cash -> decisions at the close (using data <= t) ->
    fills scheduled for today -> timed exit -> record. Orders decided at t fill at t+lag."""
    dates, n = feat.index, len(feat)
    price = feat["price"].to_numpy()
    rf = feat["rf"].fillna(0).to_numpy()
    lag, chained = ctx.execution_lag, params["chained"]
    pf = Portfolio(ctx.initial_capital, cost_bps=ctx.cost_bps)
    log = EventLog()
    pending, schedule = defaultdict(list), {}
    traded, trades, active, exit_idx, scaling_end = set(), [], None, None, -1
    active_trigger, sched_ep = -1, None
    equity, weights = np.empty(n), np.empty(n)

    for i in range(n):
        if i > 0 and ctx.cash_earns_rf:
            pf.accrue(rf[i - 1] / ctx.trading_days)

        # ---- decisions at the close of day i -----------------------------------------------
        if feat["trigger"].iat[i]:
            ep = int(feat["episode_id"].iat[i])
            if only_episode is None or ep == only_episode:
                busy = active is not None or i <= scaling_end
                if chained and busy:
                    log.add(dates[i], ep, "skipped", "position_open")
                elif ep in traded:
                    log.add(dates[i], ep, "skipped", "episode_already_traded")
                else:
                    amount = (pf.cash if chained else ctx.initial_capital) / params["buy_weeks"]
                    days = tranche_days(i, params["buy_weeks"], params["tranche_step_days"])
                    for k, d in enumerate(days):
                        schedule[d] = (k, amount, ep)
                    scaling_end = max(schedule) + lag
                    traded.add(ep)
                    sched_ep = ep
                    active_trigger = i
                    log.add(dates[i], ep, "triggered", f"ref={feat['ref_value'].iat[i]:.2f}")
        if i in schedule:
            k, amount, ep = schedule.pop(i)
            if feat["filters_pass"].iat[i]:
                pending[i + lag].append((amount, ep, k))
            else:
                log.add(
                    dates[i],
                    ep,
                    "tranche_skipped",
                    f"tranche {k + 1}/{params['buy_weeks']}: filter {feat['first_fail'].iat[i]}",
                )

        # ---- fills ---------------------------------------------------------------------------
        for amount, ep, _tranche in pending.pop(i, []):
            spent = pf.buy(amount, price[i])
            if spent <= 0:
                continue
            if active is None:
                active = {
                    "episode": ep,
                    "trigger_i": active_trigger,
                    "entry_i": i,
                    "cost": 0.0,
                    "units": 0.0,
                    "n": 0,
                }
                exit_idx = exit_index(dates, i, params["hold_years"])
            active["cost"] += spent
            active["units"] += spent * (1 - ctx.cost_bps / 1e4) / price[i]
            active["n"] += 1
            active["entry_end_i"] = i
        if i == scaling_end and active is None:
            traded.discard(sched_ep)  # nothing was bought: the episode may re-trigger
            log.add(dates[i], sched_ep, "no_entry", "every tranche failed the filters")

        # ---- timed exit: hold_years after the first tranche ----------------------------------
        if active is not None and i == exit_idx:
            proceeds = pf.sell_all(price[i])
            trades.append(_close_trade(feat, active, i, proceeds, held_open=False))
            log.add(dates[i], active["episode"], "exit", f"proceeds={proceeds:.2f}")
            active, exit_idx = None, None

        equity[i] = pf.value(price[i])
        weights[i] = pf.units * price[i] / equity[i] if equity[i] > 0 else 0.0

    if active is not None:  # still held at the end: mark to market
        proceeds = pf.units * price[-1]
        trades.append(_close_trade(feat, active, n - 1, proceeds, held_open=True))
    return (
        pd.Series(equity, dates, name="equity"),
        pd.Series(weights, dates, name="weight"),
        trades,
        log,
    )


def _close_trade(
    feat: pd.DataFrame,
    a: dict,
    exit_i: int,
    proceeds: float,
    held_open: bool,
) -> dict:
    d = feat.index
    path = feat["price"].iloc[a["entry_i"] : exit_i + 1]
    t = a["trigger_i"]
    return {
        "episode": a["episode"],
        "trigger": d[t],
        "ref_value": feat["ref_value"].iat[t],
        "ref_date": feat["ref_date"].iat[t],
        "entry_start": d[a["entry_i"]],
        "entry_end": d[a["entry_end_i"]],
        "n_tranches": a["n"],
        "exit": d[exit_i],
        "held_open": held_open,
        "vix_at_entry": feat["vix"].iat[a["entry_i"]],
        "avg_entry_price": a["cost"] / a["units"] if a["units"] else np.nan,
        "exit_price": feat["price"].iat[exit_i],
        "return": proceeds / a["cost"] - 1 if a["cost"] else np.nan,
        "max_dd_during_hold": float((path / path.cummax() - 1).min()),
    }
