import numpy as np
import pandas as pd
import pytest

from data import DataSettings, build_dataset, load_series

TODAY = pd.Timestamp("2014-12-31")


def csv_settings(tmp_path, **overrides):
    """Offline data source: CSV 'tickers' in a temp dir. FAKE only exists from 2012; VIX and the
    rate (IRX) go back to 2010. The full history is used unless a test says otherwise."""
    overrides.setdefault("lookback_years", None)
    index = pd.bdate_range("2010-01-04", TODAY)
    rng = np.random.default_rng(0)
    for name, first in (("FAKE", "2012-01-02"), ("VIX", "2010-01-04"), ("IRX", "2010-01-04")):
        days = index[index >= first]
        if name == "FAKE":
            close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(days))))
        else:
            close = 20.0
        frame = pd.DataFrame({"Close": close}, index=pd.Index(days, name="Date"))
        frame.to_csv(tmp_path / f"{name}.csv")
    return DataSettings(
        fetcher="csv",
        csv_dir=str(tmp_path),
        cache_dir=str(tmp_path / "cache"),
        vix_ticker="VIX",
        rf_ticker="IRX",
        **overrides,
    )


def test_dataset_has_the_standard_columns(tmp_path):
    data, info = build_dataset("FAKE", csv_settings(tmp_path))
    assert list(data.columns) == ["price", "signal", "vix", "rf"]
    assert info["signal"] == "FAKE"  # no SIGNAL_INDEX entry: the instrument is its own signal
    assert (data["rf"] == 0.2).all()  # the IRX column holds 20 (percent) -> 0.20


def test_backtest_starts_when_the_instrument_started_to_exist(tmp_path):
    data, _ = build_dataset("FAKE", csv_settings(tmp_path))
    assert data.index[0] == pd.Timestamp("2012-01-02")  # not 2010, when VIX and IRX begin
    assert data.index[-1] == TODAY


def test_start_before_the_instrument_existed_does_not_invent_history(tmp_path):
    data, _ = build_dataset("FAKE", csv_settings(tmp_path, start="2010-06-01"))
    assert data.index[0] == pd.Timestamp("2012-01-02")


def test_start_and_end_limit_the_window_but_not_the_cache(tmp_path):
    narrow = csv_settings(tmp_path, start="2013-03-01", end_date="2013-09-30")
    data, _ = build_dataset("FAKE", narrow)
    assert pd.Timestamp("2013-03-01") <= data.index[0] < pd.Timestamp("2013-03-08")
    assert data.index[-1] <= pd.Timestamp("2013-09-30")
    assert load_series("FAKE", narrow).index[0] == pd.Timestamp("2012-01-02")  # cache is complete
    wide, _ = build_dataset("FAKE", csv_settings(tmp_path))
    assert len(wide) > len(data)


def test_default_window_is_five_years_back_from_today(tmp_path):
    five, _ = build_dataset("FAKE", csv_settings(tmp_path, lookback_years=5), today=TODAY)
    assert five.index[0] == pd.Timestamp("2012-01-02")  # 5 years back is before FAKE existed
    one, _ = build_dataset("FAKE", csv_settings(tmp_path, lookback_years=1), today=TODAY)
    assert pd.Timestamp("2013-12-31") <= one.index[0] < pd.Timestamp("2014-01-08")
    assert one.index[-1] == TODAY


def test_lookback_counts_back_from_an_explicit_end_and_start_wins(tmp_path):
    only_end = csv_settings(tmp_path, end_date="2013-12-31", lookback_years=1)
    data, _ = build_dataset("FAKE", only_end, today=TODAY)
    assert pd.Timestamp("2012-12-31") <= data.index[0] < pd.Timestamp("2013-01-08")
    assert data.index[-1] == pd.Timestamp("2013-12-31")
    explicit = csv_settings(tmp_path, start="2012-06-01", lookback_years=1)
    data, _ = build_dataset("FAKE", explicit, today=TODAY)
    assert pd.Timestamp("2012-06-01") <= data.index[0] < pd.Timestamp("2012-06-08")


def test_empty_window_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="no data between"):
        build_dataset("FAKE", csv_settings(tmp_path, start="2030-01-01"))
