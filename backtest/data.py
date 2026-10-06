"""Price loading (cached) and the standard dataset every strategy consumes."""

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
    start: str | None = None  # backtest window start; None = `lookback_years` before the end
    end_date: str | None = None  # backtest window end (END_DATE); None = latest data (today)
    lookback_years: int | None = 5  # default window length when no start is given; None = all
    signal_index: str | None = None  # None = SIGNAL_INDEX[instrument], else the instrument itself
    vix_ticker: str = "^VIX"
    rf_ticker: str = "^IRX"  # 13-week T-bill yield, quoted in percent
    rf_default: float = 0.02  # annual rf where rf_ticker has no data


DEFAULT_SETTINGS = DataSettings()

# The series a strategy reads its signals from, per instrument (e.g. the index a leveraged fund
# tracks). Any instrument not listed uses its own prices, so any ticker works as-is.
SIGNAL_INDEX = {
    "TQQQ": "^NDX",
    "FNGU": "^NDX",
    "UPRO": "^GSPC",
    "SSO": "^GSPC",
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
        # always fetch and cache the full history; start / end are applied in build_dataset
        s = get("fetcher", settings.fetcher)(ticker, start=None, end=None, csv_dir=settings.csv_dir)
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


def build_dataset(
    instrument: str = "TQQQ",
    settings: DataSettings = DEFAULT_SETTINGS,
    refresh: bool = False,
    today: pd.Timestamp | None = None,
):
    """Standard frame for strategies, one row per trading day of the instrument:

    - price:  the instrument's adjusted close (the thing being bought and sold),
    - signal: the series strategies compute their signals from, e.g. ^NDX for TQQQ, so crashes
              and moving averages are measured on the index rather than on the leveraged fund
              (the instrument itself if it has no entry in SIGNAL_INDEX),
    - vix:    VIX close (NaN where unavailable),
    - rf:     annual risk-free rate as a decimal.

    Only real prices are used. The window is `settings.start` .. `settings.end_date`; with no
    start it is `lookback_years` before the end (default 5 years before today), and None means
    the whole history. It never begins before the instrument's first trading day. Returns
    (frame, info).
    """
    signal_ticker = settings.signal_index or SIGNAL_INDEX.get(instrument, instrument)
    tickers = [instrument, signal_ticker, settings.vix_ticker, settings.rf_ticker]
    optional = {settings.vix_ticker, settings.rf_ticker}
    raw = load_prices(tickers, settings, refresh, optional=optional)

    price = raw[instrument].dropna().rename("price")
    df = pd.DataFrame({"price": price})
    df["signal"] = raw[signal_ticker].reindex(price.index).ffill(limit=5)
    if settings.vix_ticker in raw:
        df["vix"] = raw[settings.vix_ticker].reindex(price.index).ffill(limit=5)
    else:
        df["vix"] = np.nan
    if settings.rf_ticker in raw:
        rf = raw[settings.rf_ticker] / 100.0
        df["rf"] = rf.reindex(price.index).ffill().fillna(settings.rf_default)
    else:
        df["rf"] = settings.rf_default

    end = pd.Timestamp(settings.end_date) if settings.end_date else (today or pd.Timestamp.today())
    start = settings.start
    if start is None and settings.lookback_years:
        start = end.normalize() - pd.DateOffset(years=settings.lookback_years)
    df = df.dropna(subset=["signal"]).loc[start:end]  # days with no signal value can't be traded
    if df.empty:
        raise ValueError(f"{instrument}: no data between {start} and {settings.end_date}")
    info = {
        "instrument": instrument,
        "signal": signal_ticker,
        "first_date": df.index[0],
        "last_date": df.index[-1],
    }
    return df, info
