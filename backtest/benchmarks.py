"""Buy-and-hold comparisons and the standalone ($10k per episode) view."""
import numpy as np
import pandas as pd


def hold_equity(price: pd.Series, start, capital: float = 10_000) -> pd.Series:
    """Buy at the close on `start` (first trading day >= start) and hold to the end."""
    p = price.loc[pd.Timestamp(start):].dropna()
    return (p / p.iloc[0] * capital).rename("equity")


def build_benchmarks(price: pd.Series, anchors: dict, capital: float = 10_000) -> dict:
    """hold_<anchor> for each anchor date (first_signal, first_low, first_entry, ...)."""
    return {f"hold_{k}": hold_equity(price, d, capital) for k, d in anchors.items()}


def standalone_summary(trades: pd.DataFrame, capital: float = 10_000) -> pd.DataFrame:
    """Each episode as its own account: final value of `capital` per trade, plus a total row."""
    if trades.empty:
        return pd.DataFrame()
    out = trades[["episode", "entry_start", "exit", "return", "max_dd_during_hold"]].copy()
    out["final_value"] = capital * (1 + out["return"])
    out["cagr"] = (1 + out["return"]) ** (365.25 / (out["exit"] - out["entry_start"]).dt.days) - 1
    agg = {"episode": "ALL (geo-mean)", "return": float(np.expm1(np.log1p(out["return"]).mean())),
           "final_value": float(out["final_value"].mean()),
           "max_dd_during_hold": float(out["max_dd_during_hold"].min()), "cagr": out["cagr"].mean()}
    return pd.concat([out, pd.DataFrame([agg])], ignore_index=True)
