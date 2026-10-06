"""'Buy the stabilized crash low': scale-in entry, timed exit, sizing, chaining."""
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from episodes import detect_crash_episodes
from portfolio import EventLog, Portfolio
from signals import build_features


@dataclass
class StrategyResult:
    equity: pd.Series | None          # None for standalone (non-chained) runs
    weights: pd.Series | None         # fraction of equity in the instrument at each close
    trades: pd.DataFrame
    events: pd.DataFrame              # triggered / tranche_skipped / skipped / no_entry ...
    episodes: pd.DataFrame            # auto-detected table + false_starts
    anchors: dict = field(default_factory=dict)   # dates used by the buy-and-hold comparisons


def tranche_days(trigger_idx: int, n: int, step: int) -> list[int]:
    return [trigger_idx + k * step for k in range(n)]


def exit_index(dates: pd.DatetimeIndex, entry_idx: int, hold_years: float) -> int:
    """First trading day >= entry + hold_years (== len(dates) if beyond the data)."""
    target = dates[entry_idx] + pd.DateOffset(months=round(hold_years * 12))
    return int(dates.searchsorted(target))


def _simulate(feat: pd.DataFrame, cfg: dict, capital: float, trading_days: int,
              only_episode: int | None = None):
    """Day loop. Order each day: accrue cash -> decisions at the close (using data <= t) ->
    fills scheduled for today -> timed exit -> record. Orders decided at t fill at t+lag."""
    dates, n = feat.index, len(feat)
    price, rf = feat["price"].to_numpy(), feat["rf"].fillna(0).to_numpy()
    lag, chained = cfg["execution_lag"], cfg["chained"]
    pf = Portfolio(capital, cost_bps=cfg["cost_bps"])
    log = EventLog()
    pending, schedule = defaultdict(list), {}
    traded, trades, active, exit_idx, scaling_end = set(), [], None, None, -1
    active_trigger, sched_ep = -1, None
    equity, weights = np.empty(n), np.empty(n)

    for i in range(n):
        if i > 0 and cfg["cash_earns_rf"]:
            pf.accrue(rf[i - 1] / trading_days)

        # ---- decisions at the close of day i -------------------------------------------------
        if feat["trigger"].iat[i]:
            ep = int(feat["episode_id"].iat[i])
            if only_episode is None or ep == only_episode:
                busy = active is not None or i <= scaling_end
                if chained and busy:
                    log.add(dates[i], ep, "skipped", "position_open")
                elif ep in traded:
                    log.add(dates[i], ep, "skipped", "episode_already_traded")
                else:
                    amount = (pf.cash if chained else capital) / cfg["buy_weeks"]
                    for k, d in enumerate(tranche_days(i, cfg["buy_weeks"], cfg["tranche_step_days"])):
                        schedule[d] = (k, amount, ep)
                    scaling_end = max(schedule) + lag
                    traded.add(ep)
                    sched_ep = ep
                    log.add(dates[i], ep, "triggered", f"low={feat['ep_low'].iat[i]:.2f}")
                    active_trigger = i
        if i in schedule:
            k, amount, ep = schedule.pop(i)
            if feat["filters_pass"].iat[i]:
                pending[i + lag].append((amount, ep, k))
            else:
                log.add(dates[i], ep, "tranche_skipped",
                        f"tranche {k + 1}/{cfg['buy_weeks']}: filter {feat['first_fail'].iat[i]}")

        # ---- fills ----------------------------------------------------------------------------
        for amount, ep, k in pending.pop(i, []):
            spent = pf.buy(amount, price[i])
            if spent <= 0:
                continue
            if active is None:
                active = {"episode": ep, "trigger_i": active_trigger, "entry_i": i,
                          "cost": 0.0, "units": 0.0, "n": 0}
                exit_idx = exit_index(dates, i, cfg["hold_years"])
            active["cost"] += spent
            active["units"] += spent * (1 - cfg["cost_bps"] / 1e4) / price[i]
            active["n"] += 1
            active["entry_end_i"] = i
        if i == scaling_end and active is None:
            traded.discard(sched_ep)          # nothing was bought: the episode may re-trigger
            log.add(dates[i], sched_ep, "no_entry", "every tranche failed the filters")

        # ---- timed exit: HOLD_YEARS after the first tranche ------------------------------------
        if active is not None and i == exit_idx:
            proceeds = pf.sell_all(price[i])
            trades.append(_close_trade(feat, active, i, proceeds, held_open=False))
            log.add(dates[i], active["episode"], "exit", f"proceeds={proceeds:.2f}")
            active, exit_idx = None, None

        equity[i] = pf.value(price[i])
        weights[i] = pf.units * price[i] / equity[i] if equity[i] > 0 else 0.0

    if active is not None:                              # still held at the end: mark to market
        trades.append(_close_trade(feat, active, n - 1, pf.units * price[-1], held_open=True))
    return (pd.Series(equity, dates, name="equity"), pd.Series(weights, dates, name="weight"),
            trades, log)


def _close_trade(feat, a: dict, exit_i: int, proceeds: float, held_open: bool) -> dict:
    d = feat.index
    path = feat["price"].iloc[a["entry_i"]: exit_i + 1]
    t = a["trigger_i"]
    return {
        "episode": a["episode"], "trigger": d[t], "low": feat["ep_low"].iat[t],
        "low_date": feat["ep_low_date"].iat[t],
        "entry_start": d[a["entry_i"]], "entry_end": d[a["entry_end_i"]],
        "n_tranches": a["n"], "exit": d[exit_i], "held_open": held_open,
        "vix_at_entry": feat["vix"].iat[a["entry_i"]],
        "avg_entry_price": a["cost"] / a["units"] if a["units"] else np.nan,
        "exit_price": feat["price"].iat[exit_i],
        "return": proceeds / a["cost"] - 1 if a["cost"] else np.nan,
        "max_dd_during_hold": float((path / path.cummax() - 1).min()),
    }


def run_strategy(data: pd.DataFrame, cfg: dict, episodes_cfg: dict, initial_capital: float,
                 trading_days: int = 252) -> StrategyResult:
    """data: price, signal, vix, rf. cfg: the `strategy` block; episodes_cfg: the `episodes` block."""
    feat = build_features(data, episodes_cfg, cfg)
    table = detect_crash_episodes(data["signal"], data["vix"], episodes_cfg["crash_threshold"],
                                  episodes_cfg["merge_gap_days"],
                                  override=episodes_cfg.get("override") or None)

    if cfg["chained"]:
        equity, weights, trades, log = _simulate(feat, cfg, initial_capital, trading_days)
    else:                                               # each episode is its own standalone account
        trades, logs = [], []
        equity = weights = None
        for ep in sorted(e for e in feat["episode_id"].unique() if e >= 0):
            _, _, t, lg = _simulate(feat, cfg, initial_capital, trading_days, only_episode=int(ep))
            trades += t
            logs.append(lg.frame())
        log = EventLog()
        log.rows = [r for f in logs for r in f.to_dict("records")]

    trades_df = pd.DataFrame(trades)
    events = log.frame()
    if len(table):                                      # same ids in labels, events and table
        fs = feat.groupby("episode_id")["false_starts"].max()
        trig = feat[feat["trigger"]].groupby("episode_id").size()
        table["false_starts"] = table["episode_id"].map(fs).fillna(0).astype(int)
        table["stabilizations_confirmed"] = table["episode_id"].map(trig).fillna(0).astype(int)
    anchors = {}
    trig_dates = feat.index[feat["trigger"]]
    if len(trig_dates):
        anchors["first_signal"] = trig_dates[0]
    if len(table):
        anchors["first_low"] = table["trough_date"].iloc[0]
    if len(trades_df):
        anchors["first_entry"] = trades_df["entry_start"].min()
    return StrategyResult(equity, weights, trades_df, events, table, anchors)
