"""Checks that apply to every strategy in strategies/ (new ones are picked up automatically)."""

import numpy as np
import pandas as pd
import pytest

from signals import label_windows, track_extreme
from strategies import buy_and_hold, discover, rsi_oversold_bounce, vix_spike_fade
from strategies.rsi_oversold_bounce.signals import build_features as rsi_features
from strategies.rsi_oversold_bounce.signals import rsi
from strategies.vix_spike_fade.signals import build_features as vix_features
from tests.conftest import CTX, piecewise

STRATEGIES = discover()


def test_expected_strategies_are_discovered():
    assert {"buy_and_hold", "rsi_oversold_bounce", "stabilized_crash_low", "vix_spike_fade"} <= set(
        STRATEGIES
    )


@pytest.mark.parametrize("name", STRATEGIES)
def test_strategy_is_sane(name, noisy_market):
    r = STRATEGIES[name].run(noisy_market, STRATEGIES[name].params, CTX)
    assert r.eval_start is not None
    assert (r.equity > 0).all()
    assert r.weights.between(0, 1 + 1e-9).all()


@pytest.mark.parametrize("name", STRATEGIES)
def test_no_lookahead(name, noisy_market):
    """Weights and equity up to t are unchanged when all data after t is removed."""
    strategy = STRATEGIES[name]
    if name == "buy_and_hold":
        params = {**strategy.params, "start": noisy_market.index[10]}  # no end: nothing to peek at
    else:
        params = strategy.params
    full = strategy.run(noisy_market, params, CTX)
    for cut in (500, 700, 900, 1000, 1150):
        part = strategy.run(noisy_market.iloc[:cut], params, CTX)
        np.testing.assert_allclose(part.weights.to_numpy(), full.weights.iloc[:cut].to_numpy())
        np.testing.assert_allclose(part.equity.to_numpy(), full.equity.iloc[:cut].to_numpy())


# ---- buy_and_hold ------------------------------------------------------------------------------
def test_buy_and_hold_matches_price_return(noisy_market):
    start, end = noisy_market.index[100], noisy_market.index[600]
    params = {"start": start, "end": end}
    r = buy_and_hold.run(noisy_market, params, CTX)
    price = noisy_market["price"]
    assert r.equity.loc[end] / r.equity.loc[start] == pytest.approx(
        price.loc[end] / price.loc[start]
    )
    assert r.weights.loc[start] == 1 and r.weights.loc[end] == 0  # sold at the end close
    assert r.trades.iloc[0]["return"] == pytest.approx(price.loc[end] / price.loc[start] - 1)
    assert not r.trades.iloc[0].held_open


def test_buy_and_hold_defaults_to_the_whole_history(noisy_market):
    r = buy_and_hold.run(noisy_market, buy_and_hold.PARAMS, CTX)
    assert r.eval_start == noisy_market.index[0] and r.trades.iloc[0].held_open


# ---- vix_stabilization / rsi_oversold ----------------------------------------------------------
def _market(vix_points, n=None):
    vix = piecewise(vix_points)
    price = pd.Series(100.0, vix.index)
    return pd.DataFrame({"price": price, "signal": price, "vix": vix, "risk_free": 0.0})


def test_vix_signal_waits_for_peak_pullback_and_gradual_decline():
    data = _market([(0, 15), (10, 50), (20, 50), (60, 25), (100, 15), (150, 15)])
    feat = vix_features(data, vix_spike_fade.PARAMS)
    first = feat.index[feat["trigger"]][0]
    peak = feat.loc[first, "ref_value"]
    assert peak == 50
    assert feat.loc[first, "days_since_ref"] >= vix_spike_fade.PARAMS["stable_days"]
    assert data.loc[first, "vix"] <= peak * (1 - vix_spike_fade.PARAMS["pullback"])
    assert first > data.index[20]  # never fires while VIX is still at its high


def test_vix_below_spike_level_never_arms():
    feat = vix_features(_market([(0, 15), (50, 28), (100, 15)]), vix_spike_fade.PARAMS)
    assert not feat["trigger"].any() and (feat["episode_id"] == -1).all()


def test_rsi_is_bounded_and_oversold_signal_needs_a_bounce():
    close = piecewise([(0, 100), (60, 100), (90, 60), (110, 60), (150, 80)])
    strength = rsi(close, 14).dropna()
    assert strength.between(0, 100).all() and strength.min() < 30
    data = pd.DataFrame({"price": close, "signal": close, "vix": 20.0, "risk_free": 0.0})
    feat = rsi_features(data, rsi_oversold_bounce.PARAMS)
    first = feat.index[feat["trigger"]][0]
    assert (
        feat.loc[first, "rsi"]
        >= feat.loc[first, "ref_value"] + rsi_oversold_bounce.PARAMS["bounce"]
    )
    assert feat.loc[first, "days_since_ref"] >= rsi_oversold_bounce.PARAMS["stable_days"]


def test_window_labelling_helpers():
    arm = np.array([0, 1, 0, 0, 0, 1, 0], dtype=bool)
    disarm = np.array([0, 0, 0, 1, 0, 0, 0], dtype=bool)
    assert label_windows(arm, disarm).tolist() == [-1, 1, 1, -1, -1, 2, 2]
    s = pd.Series([1, 5, 3, 7, 2.0], pd.bdate_range("2020-01-01", periods=5))
    ep = pd.Series([1, 1, 1, 1, -1], s.index)
    ext = track_extreme(s, ep, "max")
    assert ext["ref_value"].iloc[:4].tolist() == [1, 5, 5, 7]
    assert ext["days_since_ref"].iloc[:4].tolist() == [0, 0, 1, 0]
