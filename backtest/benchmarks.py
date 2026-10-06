"""Benchmarks (buy and hold entered at the same time as a strategy) and the standalone view."""

import numpy as np
import pandas as pd

from strategies import buy_and_hold
from strategy import Context, StrategyResult


def hold_from(data: pd.DataFrame, start, ctx: Context) -> StrategyResult:
    """What the instrument returned if bought at the close on `start` and held to the end."""
    return buy_and_hold.run(data, {"start": start, "end": None}, ctx)


def build_benchmarks(
    data: pd.DataFrame,
    anchors: dict,
    ctx: Context,
) -> dict[str, StrategyResult]:
    """hold_<anchor> for each anchor date a strategy reports (first_signal, first_entry, ...)."""
    return {f"hold_{name}": hold_from(data, date, ctx) for name, date in anchors.items()}


def standalone_summary(trades: pd.DataFrame, capital: float = 10_000) -> pd.DataFrame:
    """Each episode as its own account: final value of `capital` per trade, plus a total row."""
    if trades.empty:
        return pd.DataFrame()
    out = trades[["episode", "entry_start", "exit", "return", "max_dd_during_hold"]].copy()
    out["final_value"] = capital * (1 + out["return"])
    held_days = (out["exit"] - out["entry_start"]).dt.days
    out["cagr"] = (1 + out["return"]) ** (365.25 / held_days) - 1
    geo_return = float(np.expm1(np.log1p(out["return"]).mean()))
    total = {
        "episode": "ALL (geo-mean)",
        "return": geo_return,
        "final_value": capital * (1 + geo_return),
        "max_dd_during_hold": float(out["max_dd_during_hold"].min()),
        "cagr": float((1 + out["cagr"]).prod() ** (1 / len(out)) - 1),
    }
    return pd.concat([out, pd.DataFrame([total])], ignore_index=True)
