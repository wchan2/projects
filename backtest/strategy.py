"""Strategy contract and the shared scale-in / timed-exit engine.

A strategy is a `Strategy` object: a description, default `params`, a
`run(data, params, ctx) -> StrategyResult` function and its own sensitivity grid. Feed `run` the
standard dataset (price, signal, vix, risk_free) and extract performance with `metrics.performance`.

Strategies live in `strategies/`. The ones built on "wait for a signal, scale in, hold, sell" only
need to produce a feature frame and hand it to `scale_in()`.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from portfolio import EventLog, Portfolio
from signals import Signal, rising_edge


@dataclass(frozen=True)
class Context:
    """Backtest-wide settings shared by every strategy."""

    initial_capital: float = 10_000
    trading_days: int = 252
    execution_lag: int = 1  # decided at close t, filled at close t+lag
    cash_earns_risk_free: bool = True  # False = cash earns 0
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
    risk_free: pd.Series,
    weights: pd.Series,
    ctx: Context,
) -> pd.Series:
    """Equity of a book that holds `weights[t-1]` of the instrument over day t (weights are
    post-trade at each close) and keeps the rest in cash."""
    returns = price.pct_change().fillna(0)
    cash_returns = (
        (risk_free.shift(1) / ctx.trading_days).fillna(0)
        if ctx.cash_earns_risk_free
        else 0 * returns
    )
    held = weights.shift(1).fillna(0)
    turnover = weights.diff().abs().fillna(weights.abs())
    daily = held * returns + (1 - held) * cash_returns - turnover * ctx.cost_bps / 1e4
    return (ctx.initial_capital * (1 + daily).cumprod()).rename("equity")


# ---- scale-in / timed-exit engine ----------------------------------------------------------------
# Required feature columns: price, risk_free, vix, episode_id (-1 = none), trigger, filters_pass,
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


# ---- build a strategy from an entry signal ------------------------------------------------------
SCALE_IN_DEFAULTS = {
    "buy_weeks": 8,  # equal weekly tranches
    "tranche_step_days": 5,
    "hold_years": 1,  # sold this long after the first tranche
    "chained": True,  # proceeds redeployed at the next signal; False = standalone $ per episode
    "cooldown_days": 21,  # entry-signal days closer than this belong to the same episode
}


def scale_in_strategy(
    description: str,
    entry: Signal,
    sensitivity_grid: dict | None = None,
    tranche_filter: Signal | None = None,
    signal_params: dict | None = None,
    **scale_in_params,
) -> Strategy:
    """A strategy that buys when `entry` turns true: scale in over `buy_weeks` tranches (each
    must pass `tranche_filter`, if given), hold `hold_years`, sell. `signal_params` overrides the
    defaults of individual signals, e.g. {"deep_dip": {"lookback_days": 252}}. Any other keyword
    overrides SCALE_IN_DEFAULTS."""
    params = {**SCALE_IN_DEFAULTS, **scale_in_params}
    for sig in (entry, tranche_filter):
        if sig is not None:
            params.update(sig.all_defaults())
    for name, overrides in (signal_params or {}).items():
        params[name] = {**params[name], **overrides}

    def run(data: pd.DataFrame, params: dict, ctx: Context) -> StrategyResult:
        active = entry(data, params)
        feat = data.assign(
            episode_id=cluster_ids(active, params["cooldown_days"]),
            trigger=rising_edge(active),
            ref_value=data["signal"],
            ref_date=data.index,
        )
        if tranche_filter is None:
            feat["filters_pass"], feat["first_fail"] = True, ""
        else:
            feat["filters_pass"] = tranche_filter(data, params)
            feat["first_fail"] = tranche_filter.first_failing(data, params)
        equity, weights, trades, events = scale_in(feat, params, ctx)
        trades = trades.rename(columns={"ref_value": "signal_level"})
        trades = trades.drop(columns="ref_date", errors="ignore")
        anchors = scale_in_anchors(feat, trades)
        return StrategyResult(
            equity,
            weights,
            trades,
            events,
            signal_episodes(feat),
            anchors,
            eval_start=anchors.get("first_signal"),
        )

    return Strategy(description, run, params, sensitivity_grid or {})


def cluster_ids(active: pd.Series, cooldown_days: int) -> pd.Series:
    """Episode id (1-based) on each day `active` is true, -1 elsewhere. Active days fewer than
    `cooldown_days` trading days after the previous one belong to the same episode."""
    flags = active.to_numpy()
    ids = np.full(len(flags), -1, dtype=int)
    current, last_active = 0, None
    for i in range(len(flags)):
        if flags[i]:
            if last_active is None or i - last_active > cooldown_days:
                current += 1
            ids[i], last_active = current, i
    return pd.Series(ids, index=active.index)


def signal_episodes(feat: pd.DataFrame) -> pd.DataFrame:
    """One row per entry-signal episode: when it started and ended, and how often it fired."""
    columns = ["episode_id", "start_date", "recovery_date", "active_days", "triggers"]
    rows = []
    for episode, days in feat[feat["episode_id"] >= 0].groupby("episode_id"):
        rows.append(
            {
                "episode_id": int(episode),
                "start_date": days.index[0],
                "recovery_date": days.index[-1],  # last day the signal was on
                "active_days": len(days),
                "triggers": int(days["trigger"].sum()),
            }
        )
    return pd.DataFrame(rows, columns=columns)


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
    risk_free = feat["risk_free"].fillna(0).to_numpy()
    lag, chained = ctx.execution_lag, params["chained"]
    pf = Portfolio(ctx.initial_capital, cost_bps=ctx.cost_bps)
    log = EventLog()
    pending, schedule = defaultdict(list), {}
    traded, trades, active, exit_idx, scaling_end = set(), [], None, None, -1
    active_trigger, sched_ep = -1, None
    equity, weights = np.empty(n), np.empty(n)

    for i in range(n):
        if i > 0 and ctx.cash_earns_risk_free:
            pf.accrue(risk_free[i - 1] / ctx.trading_days)

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
