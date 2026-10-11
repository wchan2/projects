"""Signals: each test says when a signal does or does not match, and why."""

import numpy as np
import pandas as pd
import pytest

from signals import (
    above_moving_average,
    all_of,
    any_of,
    deep_dip,
    label_windows,
    not_,
    recently,
    rsi,
    rsi_bounce,
    signal,
    track_extreme,
    vix_below,
    vix_stabilizing,
)
from tests.conftest import piecewise

LIBRARY = [vix_below, above_moving_average, deep_dip, vix_stabilizing, rsi_bounce]


def market(vix_points=None, price_points=None):
    price = piecewise(price_points or [(0, 100), (300, 100)])
    vix = piecewise(vix_points)[: len(price)] if vix_points else pd.Series(20.0, price.index)
    return pd.DataFrame({"price": price, "signal": price, "vix": vix.to_numpy(), "risk_free": 0.0})


def truth_table():
    """Four days covering every combination of two yes/no columns, a and b."""
    days = pd.bdate_range("2020-01-01", periods=4)
    return pd.DataFrame({"a": [False, False, True, True], "b": [False, True, False, True]}, days)


@signal("a_holds")
def a_holds(data):
    return data["a"]


@signal("b_holds")
def b_holds(data):
    return data["b"]


# ---- what every signal promises -----------------------------------------------------------------
@pytest.mark.parametrize("sig", LIBRARY, ids=lambda s: s.name)
def test_every_signal_answers_true_or_false_for_each_day(sig, noisy_market):
    answer = sig(noisy_market)
    assert answer.dtype == bool
    assert answer.index.equals(noisy_market.index)


@pytest.mark.parametrize("sig", LIBRARY, ids=lambda s: s.name)
def test_a_signal_never_uses_data_from_after_the_day_it_answers_for(sig, noisy_market):
    full = sig(noisy_market)
    for cut in (300, 600, 900, 1150):
        assert sig(noisy_market.iloc[:cut]).equals(full.iloc[:cut])


def test_a_missing_vix_never_counts_as_a_match(noisy_market):
    assert not vix_below(noisy_market.assign(vix=np.nan)).any()


def test_moving_average_signal_does_not_match_until_it_has_enough_history(noisy_market):
    assert not above_moving_average(noisy_market.iloc[:100]).any()  # needs 200 days


# ---- parameters ---------------------------------------------------------------------------------
def test_a_signal_reads_its_threshold_from_its_own_entry_in_params(noisy_market):
    calm_everywhere = vix_below(noisy_market, {"vix_below": {"limit": 1000}})
    never_calm = vix_below(noisy_market, {"vix_below": {"limit": 5}})
    assert calm_everywhere.all()
    assert not never_calm.any()


def test_a_signal_falls_back_to_its_default_when_params_have_no_entry(noisy_market):
    default = vix_below(noisy_market)
    explicit = vix_below(noisy_market, {"vix_below": {"limit": 30}})  # 30 is the default
    assert default.equals(explicit)


def test_a_new_signal_is_one_decorated_function_with_overridable_defaults():
    @signal("price_above", level=105)
    def price_above(data, level):
        return data["price"] > level

    data = pd.DataFrame({"price": [100, 110, 250, 300, 150]})
    assert price_above(data).tolist() == [False, True, True, True, True]  # default level 105
    above_200 = price_above(data, {"price_above": {"level": 200}})
    assert above_200.tolist() == [False, False, True, True, False]  # only 250 and 300 exceed 200
    assert price_above.all_defaults() == {"price_above": {"level": 105}}


# ---- combining signals --------------------------------------------------------------------------
def test_all_of_matches_only_on_days_when_every_signal_matches():
    assert all_of(a_holds, b_holds)(truth_table()).tolist() == [False, False, False, True]


def test_any_of_matches_on_days_when_either_signal_matches():
    assert any_of(a_holds, b_holds)(truth_table()).tolist() == [False, True, True, True]


def test_not_of_matches_on_days_when_the_signal_does_not():
    assert not_(a_holds)(truth_table()).tolist() == [True, True, False, False]


def test_recently_keeps_matching_for_n_days_after_the_signal_fires():
    days = pd.bdate_range("2020-01-01", periods=10)
    data = pd.DataFrame({"price": 1.0, "signal": 1.0, "vix": [0, 0, 99, 0, 0, 0, 0, 0, 0, 0]}, days)
    spike = signal("spike", limit=50)(lambda d, limit: d["vix"] > limit)
    # the spike is on day 3 (index 2); with n=3 it counts on days 3, 4 and 5
    assert recently(spike, 3)(data).tolist() == [False, False] + [True] * 3 + [False] * 5


def test_a_combination_collects_the_defaults_of_every_signal_inside_it():
    combined = all_of(recently(vix_stabilizing, 5), deep_dip)
    assert set(combined.all_defaults()) == {"vix_stabilizing", "deep_dip"}


def test_first_failing_names_the_first_signal_that_did_not_match():
    data = market(vix_points=[(0, 50), (300, 50)])  # VIX high on every day, price flat (no dip)
    failing = all_of(vix_below, deep_dip).first_failing(data)
    assert (failing == "vix_below").all()  # both fail; the first one in the list is reported


# ---- the individual signals ---------------------------------------------------------------------
def test_deep_dip_matches_while_price_is_far_below_its_high():
    data = market(price_points=[(0, 100), (50, 100), (100, 80), (250, 80), (299, 80)])
    far_below_high = deep_dip(data, {"deep_dip": {"min_depth": 0.15}})
    assert far_below_high.iloc[-1]  # 80 is 20% under the high of 100
    assert not far_below_high.iloc[0]  # at the high on day one


def test_deep_dip_stops_matching_once_the_high_falls_outside_the_lookback_window():
    data = market(price_points=[(0, 100), (50, 100), (100, 80), (250, 80), (299, 80)])
    recent_high_only = {"deep_dip": {"min_depth": 0.15, "lookback_days": 60}}
    assert not deep_dip(data, recent_high_only).iloc[-1]  # the 100 is more than 60 days old


def test_vix_stabilizing_matches_only_after_vix_has_peaked_and_pulled_back():
    vix = [(0, 15), (10, 50), (20, 50), (60, 25), (100, 15), (150, 15)]
    data = market(vix_points=vix, price_points=[(0, 100), (150, 100)])
    matches = vix_stabilizing(data)
    first = data.index[matches][0]
    assert first > data.index[20]  # not while VIX is still sitting at its peak
    assert data.loc[first, "vix"] <= 50 * (1 - 0.25)  # down at least the 25% pullback


def test_vix_stabilizing_never_matches_if_vix_never_reaches_the_spike_level():
    data = market(vix_points=[(0, 15), (50, 28), (100, 15)], price_points=[(0, 100), (100, 100)])
    assert not vix_stabilizing(data).any()  # peak of 28 is below the spike level of 30


def test_rsi_always_stays_between_0_and_100():
    close = piecewise([(0, 100), (60, 100), (90, 60), (110, 60), (150, 80)])
    strength = rsi(close, 14).dropna()
    assert strength.between(0, 100).all()
    assert strength.min() < 30  # the 40% drop does push it into oversold territory


def test_rsi_bounce_matches_only_after_prices_turn_up_from_the_low():
    close = piecewise([(0, 100), (60, 100), (90, 60), (110, 60), (150, 80)])
    data = pd.DataFrame({"price": close, "signal": close, "vix": 20.0, "risk_free": 0.0})
    first = data.index[rsi_bounce(data)][0]
    assert first > close.index[110]  # prices bottom out on days 90-110; no match before they rise


# ---- helpers ------------------------------------------------------------------------------------
def test_label_windows_numbers_each_arm_to_disarm_stretch():
    arm = np.array([0, 1, 0, 0, 0, 1, 0], dtype=bool)
    disarm = np.array([0, 0, 0, 1, 0, 0, 0], dtype=bool)
    assert label_windows(arm, disarm).tolist() == [-1, 1, 1, -1, -1, 2, 2]


def test_track_extreme_follows_the_running_high_inside_an_episode():
    values = pd.Series([1, 5, 3, 7, 2.0], pd.bdate_range("2020-01-01", periods=5))
    episode = pd.Series([1, 1, 1, 1, -1], values.index)
    tracked = track_extreme(values, episode, "max")
    assert tracked["ref_value"].iloc[:4].tolist() == [1, 5, 5, 7]
    assert tracked["days_since_ref"].iloc[:4].tolist() == [0, 0, 1, 0]
