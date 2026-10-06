"""Price loading (cached), synthetic leveraged series, splicing and tracking error."""

import time
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from registry import get, register


@dataclass(frozen=True)
class DataSettings:
    cache_dir: str = "data_cache"
    max_age_days: int = 7  # re-download when the cached parquet is older than this
    fetcher: str = "yfinance"  # registered fetcher: yfinance | csv
    csv_dir: str | None = None  # fetcher="csv": <csv_dir>/<TICKER>.csv with Date,Close columns
    start: str | None = None  # None = max history
    end_date: str | None = None  # END_DATE: data is cut here
    signal_index: str | None = None  # None = the instrument's underlying, else the instrument
    vix_ticker: str = "^VIX"
    rf_ticker: str = "^IRX"  # 13-week T-bill yield, quoted in percent
    rf_default: float = 0.02  # annual rf where rf_ticker has no data
    financing_spread: float = 0.0  # added to rf when costing leverage
    trading_days: int = 252


@dataclass(frozen=True)
class Instrument:
    """Synthetic-history recipe for a leveraged fund; the real fund is spliced in once it exists."""

    underlying: str
    leverage: float
    expense_ratio: float


DEFAULT_SETTINGS = DataSettings()

# Instrument registry. Any ticker not listed is used as-is (real prices only).
INSTRUMENTS = {
    "TQQQ": Instrument("^NDX", 3, 0.0095),
    "FNGU": Instrument("^NDX", 3, 0.0095),  # proxy: no FANG+ history before launch
    "UPRO": Instrument("^GSPC", 3, 0.0091),
    "SSO": Instrument("^GSPC", 2, 0.0089),
}


@register("fetcher", "yfinance")
def fetch_yfinance(ticker: str, start=None, end=None, **_) -> pd.Series:
    import yfinance as yf

    kw = {"start": start, "end": end} if start else {"period": "max"}  # default would be 1 month
    df = yf.download(ticker, auto_adjust=True, progress=False, multi_level_index=False, **kw)
    if df is None or df.empty:
        raise ValueError(f"no data returned for {ticker}")
    return _clean(df["Close"], ticker)


@register("fetcher", "csv")
def fetch_csv(ticker: str, csv_dir=None, **_) -> pd.Series:
    df = pd.read_csv(Path(csv_dir) / f"{ticker}.csv", index_col=0, parse_dates=True)
    return _clean(df["Close"], ticker)


def _clean(s: pd.Series, name: str) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce").dropna().astype(float)
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    return s[~s.index.duplicated()].sort_index().rename(name)


def _cache_path(cache_dir, ticker: str) -> Path:
    safe = "".join(c if c.isalnum() else "_" for c in ticker)
    return Path(cache_dir) / f"{safe}.parquet"


def load_series(
    ticker: str,
    settings: DataSettings = DEFAULT_SETTINGS,
    refresh: bool = False,
) -> pd.Series:
    """One ticker's adjusted closes. Uses the parquet cache unless stale / refresh; a failed
    download falls back to a stale cache with a warning."""
    path = _cache_path(settings.cache_dir, ticker)
    age_limit = settings.max_age_days * 86400
    fresh = path.exists() and (time.time() - path.stat().st_mtime) < age_limit
    if fresh and not refresh:
        return pd.read_parquet(path)["close"].rename(ticker)
    try:
        s = get("fetcher", settings.fetcher)(
            ticker,
            start=settings.start,
            end=None,
            csv_dir=settings.csv_dir,
        )
    except Exception as exc:
        if path.exists():
            warnings.warn(f"{ticker}: download failed ({exc}); using stale cache", stacklevel=2)
            return pd.read_parquet(path)["close"].rename(ticker)
        raise
    path.parent.mkdir(parents=True, exist_ok=True)
    s.rename("close").to_frame().to_parquet(path)
    return s


def load_prices(
    tickers,
    settings: DataSettings = DEFAULT_SETTINGS,
    refresh: bool = False,
    optional=(),
) -> pd.DataFrame:
    """Outer-joined adjusted closes. Tickers in `optional` are skipped if unavailable."""
    cols = {}
    for t in dict.fromkeys(tickers):
        try:
            cols[t] = load_series(t, settings, refresh)
        except Exception as exc:
            if t not in optional:
                raise
            warnings.warn(f"optional ticker {t} unavailable: {exc}", stacklevel=2)
    return pd.DataFrame(cols).sort_index()


def build_synthetic_3x(
    underlying: pd.Series,
    rf=0.0,
    leverage: float = 3.0,
    expense_ratio: float = 0.0095,
    financing_spread: float = 0.0,
    trading_days: int = 252,
    base: float = 100.0,
) -> pd.Series:
    """Daily-reset leveraged series: L*r - (L-1)*(rf+spread)/252 - expense/252.
    `rf` is an annual decimal rate, scalar or Series. Works for any leverage (2x, 3x, ...)."""
    r = underlying.pct_change()
    rf_s = rf.reindex(underlying.index).ffill() if isinstance(rf, pd.Series) else rf
    lr = (
        leverage * r
        - (leverage - 1) * (rf_s + financing_spread) / trading_days
        - expense_ratio / trading_days
    )
    lr.iloc[0] = 0.0
    lr = lr.clip(lower=-0.999)  # a daily-reset fund cannot lose more than 100%
    return (base * (1 + lr).cumprod()).rename(f"{underlying.name}_{leverage:g}x")


def splice_with_real(synth: pd.Series, real: pd.Series) -> pd.Series:
    """Synthetic history before the real series starts, real afterwards; synthetic is rescaled
    so the join is continuous."""
    real = real.dropna()
    d0 = real.index[0]
    before = synth[synth.index < d0]
    if before.empty:
        return real
    scale = real.iloc[0] / synth.loc[:d0].iloc[-1]
    return pd.concat([before * scale, real]).rename(real.name)


def tracking_error(synth: pd.Series, real: pd.Series, trading_days: int = 252) -> dict:
    """Synthetic vs real over their overlap (daily-return based)."""
    idx = synth.dropna().index.intersection(real.dropna().index)
    a, b = synth.loc[idx], real.loc[idx]
    ra, rb = a.pct_change().dropna(), b.pct_change().dropna()
    diff = ra - rb
    years = max((idx[-1] - idx[0]).days / 365.25, 1e-9)
    return {
        "overlap_start": idx[0],
        "overlap_end": idx[-1],
        "n_days": len(ra),
        "annualized_te": float(diff.std() * np.sqrt(trading_days)),
        "mean_daily_diff": float(diff.mean()),
        "return_correlation": float(ra.corr(rb)),
        "cagr_synth": float((a.iloc[-1] / a.iloc[0]) ** (1 / years) - 1),
        "cagr_real": float((b.iloc[-1] / b.iloc[0]) ** (1 / years) - 1),
    }


def build_dataset(
    instrument: str = "TQQQ",
    settings: DataSettings = DEFAULT_SETTINGS,
    refresh: bool = False,
    instruments: dict[str, Instrument] = INSTRUMENTS,
):
    """Standard frame for strategies: columns price, signal, vix, rf (annual decimal).
    Any ticker works; if it is in `instruments`, pre-launch history is synthetic.
    Returns (frame, info)."""
    spec = instruments.get(instrument)
    underlying = spec.underlying if spec else None
    signal_t = settings.signal_index or underlying or instrument
    need = [instrument, signal_t, settings.vix_ticker, settings.rf_ticker]
    if underlying:
        need.append(underlying)
    optional = {settings.vix_ticker, settings.rf_ticker}
    if underlying:
        optional.add(instrument)  # the real fund may not exist (synthetic only)
    raw = load_prices(need, settings, refresh, optional=optional)

    has_rf = settings.rf_ticker in raw
    rf = raw[settings.rf_ticker] / 100.0 if has_rf else pd.Series(dtype=float)
    info = {"instrument": instrument, "signal": signal_t, "synthetic_until": None, "tracking": None}
    if underlying:
        rf_full = rf.reindex(raw.index).ffill().fillna(settings.rf_default)
        synth = build_synthetic_3x(
            raw[underlying].dropna(),
            rf_full,
            spec.leverage,
            spec.expense_ratio,
            settings.financing_spread,
            settings.trading_days,
        )
        if instrument in raw and raw[instrument].notna().any():
            real = raw[instrument].dropna()
            info["tracking"] = tracking_error(synth, real, settings.trading_days)
            info["synthetic_until"] = real.index[0]
            price = splice_with_real(synth, real)
        else:
            info["synthetic_until"] = synth.index[-1]
            price = synth
    else:
        price = raw[instrument].dropna()
    price = price.rename("price")

    idx = price.index
    df = pd.DataFrame({"price": price})
    df["signal"] = raw[signal_t].reindex(idx).ffill(limit=5)
    if settings.vix_ticker in raw:
        df["vix"] = raw[settings.vix_ticker].reindex(idx).ffill(limit=5)
    else:
        df["vix"] = np.nan
    if has_rf:
        df["rf"] = rf.reindex(idx).ffill().fillna(settings.rf_default)
    else:
        df["rf"] = settings.rf_default
    df = df.dropna(subset=["signal"])
    if settings.end_date:
        df = df.loc[: pd.Timestamp(settings.end_date)]
    return df, info
