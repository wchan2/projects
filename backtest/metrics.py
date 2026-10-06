"""Performance metrics. All functions take an equity (or return) series and return numbers."""

import numpy as np
import pandas as pd


def window(equity: pd.Series, start=None, capital: float | None = None) -> pd.Series:
    """Slice from `start` and rebase so the first value equals `capital` (or stays as is)."""
    eq = equity.dropna()
    if start is not None:
        eq = eq.loc[pd.Timestamp(start) :]
    return eq / eq.iloc[0] * capital if capital is not None else eq


def cagr(eq: pd.Series) -> float:
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    return (
        float((eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1)
        if years > 0 and eq.iloc[0] > 0
        else np.nan
    )


def max_drawdown(eq: pd.Series) -> float:
    return float((eq / eq.cummax() - 1).min())


def drawdown_series(eq: pd.Series) -> pd.Series:
    return eq / eq.cummax() - 1


def sharpe(
    ret: pd.Series, risk_free_daily: pd.Series | float = 0.0, trading_days: int = 252
) -> float:
    ex = ret - risk_free_daily
    return float(ex.mean() / ex.std() * np.sqrt(trading_days)) if ex.std() > 0 else np.nan


def sortino(
    ret: pd.Series, risk_free_daily: pd.Series | float = 0.0, trading_days: int = 252
) -> float:
    ex = ret - risk_free_daily
    dd = np.sqrt((np.minimum(ex, 0) ** 2).mean())
    return float(ex.mean() / dd * np.sqrt(trading_days)) if dd > 0 else np.nan


def summarize(
    equity: pd.Series,
    weights: pd.Series | None = None,
    trades: pd.DataFrame | None = None,
    risk_free: pd.Series | None = None,
    start=None,
    capital: float = 10_000,
    trading_days: int = 252,
) -> dict:
    """final value of `capital`, CAGR, max drawdown, Sharpe/Sortino, time in market, trades."""
    eq = window(equity, start, capital)
    ret = eq.pct_change().dropna()
    daily_risk_free = (
        (risk_free.reindex(eq.index).ffill().fillna(0) / trading_days).loc[ret.index]
        if risk_free is not None
        else 0.0
    )
    w = weights.reindex(eq.index) if weights is not None else None
    tr = trades if trades is not None else pd.DataFrame()
    return {
        "start": eq.index[0],
        "end": eq.index[-1],
        "final_value": float(eq.iloc[-1]),
        "total_return": float(eq.iloc[-1] / eq.iloc[0] - 1),
        "cagr": cagr(eq),
        "max_drawdown": max_drawdown(eq),
        "volatility": float(ret.std() * np.sqrt(trading_days)),
        "sharpe": sharpe(ret, daily_risk_free, trading_days),
        "sortino": sortino(ret, daily_risk_free, trading_days),
        "time_in_market": float((w > 0.01).mean()) if w is not None else 1.0,
        "n_trades": int(len(tr)) if weights is not None or len(tr) else 1,
        "worst_trade": float(tr["return"].min()) if len(tr) else np.nan,
        "win_rate": float((tr["return"] > 0).mean()) if len(tr) else np.nan,
    }


def performance(
    result, data: pd.DataFrame, capital: float = 10_000, trading_days: int = 252
) -> dict:
    """Performance of any StrategyResult, measured from its eval_start."""
    return summarize(
        result.equity,
        result.weights,
        result.trades,
        data["risk_free"],
        result.eval_start,
        capital,
        trading_days,
    )
