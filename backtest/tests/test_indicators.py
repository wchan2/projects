"""Indicators: each test gives a small series and the exact numbers that should come out."""

import numpy as np
import pandas as pd
import pytest

from indicators import drawdown_from_high, moving_average, rsi, run_length


def series(values):
    return pd.Series(values, pd.bdate_range("2020-01-01", periods=len(values)), dtype=float)


# ---- rsi ----------------------------------------------------------------------------------------
def test_rsi_matches_a_hand_worked_example():
    # closes 10, 11, 10, 12 with period 2 (smoothing weight 1/2):
    #   average gain: -, -, 0.5, 1.25     average loss: -, -, 0.5, 0.25
    #   day 3: gain/loss = 0.5/0.5 = 1 -> RSI 50;  day 4: 1.25/0.25 = 5 -> RSI 100 - 100/6
    result = rsi(series([10, 11, 10, 12]), period=2)
    assert result.iloc[:2].isna().all()  # not enough days yet
    assert result.iloc[2] == pytest.approx(50.0)
    assert result.iloc[3] == pytest.approx(100 - 100 / 6)


def test_rsi_is_100_when_price_only_rises_and_0_when_it_only_falls():
    assert rsi(series(range(1, 30))).iloc[-1] == 100
    assert rsi(series(range(30, 1, -1))).iloc[-1] == 0


def test_rsi_stays_between_0_and_100_on_noisy_prices():
    rng = np.random.default_rng(0)
    prices = series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 500))))
    assert rsi(prices).dropna().between(0, 100).all()


# ---- drawdown_from_high -------------------------------------------------------------------------
def test_drawdown_is_zero_at_a_high_and_negative_below_it():
    result = drawdown_from_high(series([100, 90, 95, 110, 99]))
    assert result.tolist() == pytest.approx([0, -0.10, -0.05, 0, -0.10])


def test_drawdown_with_a_lookback_forgets_highs_older_than_the_window():
    # with a 2-day lookback, day 3's high is max(90, 95) = 95, so 95 is at its high
    result = drawdown_from_high(series([100, 90, 95, 110, 99]), lookback_days=2)
    assert result.tolist() == pytest.approx([0, -0.10, 0, 0, -0.10])


# ---- moving_average -----------------------------------------------------------------------------
def test_moving_average_averages_the_last_n_values():
    result = moving_average(series([1, 2, 3, 4]), window=2)
    assert result.iloc[0] != result.iloc[0]  # NaN: only one value so far
    assert result.iloc[1:].tolist() == [1.5, 2.5, 3.5]


# ---- run_length ---------------------------------------------------------------------------------
def test_run_length_counts_consecutive_true_days_and_resets_on_a_false_day():
    condition = pd.Series([False, True, True, False, True, True, True])
    assert run_length(condition).tolist() == [0, 1, 2, 0, 1, 2, 3]


def test_run_length_treats_missing_values_as_false():
    condition = pd.Series([True, True, np.nan, True])
    assert run_length(condition).tolist() == [1, 2, 0, 1]


# ---- no lookahead -------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "indicator",
    [
        lambda s: rsi(s, 14),
        lambda s: drawdown_from_high(s),
        lambda s: drawdown_from_high(s, lookback_days=60),
        lambda s: moving_average(s, 50),
        lambda s: run_length(s.pct_change() > 0),
    ],
    ids=["rsi", "drawdown", "drawdown_lookback", "moving_average", "run_length"],
)
def test_an_indicator_never_changes_for_a_day_when_later_data_is_removed(indicator, noisy_market):
    full = indicator(noisy_market["price"])
    for cut in (300, 600, 900, 1150):
        earlier = indicator(noisy_market["price"].iloc[:cut])
        pd.testing.assert_series_equal(earlier, full.iloc[:cut], check_names=False)
