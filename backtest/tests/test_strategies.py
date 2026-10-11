"""Strategies: checks for every strategy, then what each one buys and sells and why."""

import numpy as np
import pandas as pd
import pytest

from signals import all_of, any_of, deep_dip, not_, signal
from strategies import buy_and_hold, capitulation_confluence, discover
from strategy import cluster_ids, scale_in_strategy
from tests.conftest import CTX, piecewise

STRATEGIES = discover()
# most strategies are exercised on the noisy crash market; the strict one needs its own
OWN_MARKET = {"capitulation_confluence": "capitulation_market"}


def market_for(name, request):
    return request.getfixturevalue(OWN_MARKET.get(name, "noisy_market"))


# ---- checks for every strategy (new ones are picked up automatically) ---------------------------
@pytest.mark.parametrize("name", STRATEGIES)
def test_every_strategy_buys_on_a_market_built_for_it(name, request):
    data = market_for(name, request)
    result = STRATEGIES[name].run(data, STRATEGIES[name].params, CTX)
    assert len(result.trades) >= 1  # so the checks below are not trivially about an empty account


@pytest.mark.parametrize("name", STRATEGIES)
def test_a_strategy_never_invests_more_than_the_account_is_worth(name, request):
    data = market_for(name, request)
    result = STRATEGIES[name].run(data, STRATEGIES[name].params, CTX)
    assert result.weights.between(0, 1 + 1e-9).all()
    assert (result.equity > 0).all()


@pytest.mark.parametrize("name", STRATEGIES)
def test_a_strategy_makes_the_same_decisions_when_later_data_is_removed(name, request):
    data = market_for(name, request)
    strategy = STRATEGIES[name]
    full = strategy.run(data, strategy.params, CTX)
    for cut in (500, 700, 900, 1000):
        earlier = strategy.run(data.iloc[:cut], strategy.params, CTX)
        np.testing.assert_allclose(earlier.weights.to_numpy(), full.weights.iloc[:cut].to_numpy())
        np.testing.assert_allclose(earlier.equity.to_numpy(), full.equity.iloc[:cut].to_numpy())


@pytest.mark.parametrize("name", STRATEGIES)
def test_every_sensitivity_grid_key_points_at_a_real_parameter(name):
    """A key that is not in the parameters would make the sweep silently do nothing."""
    strategy = STRATEGIES[name]
    for dotted in strategy.sensitivity_grid:
        node = strategy.params
        for key in dotted.split("."):
            assert key in node, f"{name}: grid key {dotted!r} not in params"
            node = node[key]


# ---- buy_and_hold -------------------------------------------------------------------------------
def test_buy_and_hold_returns_what_the_price_returned_between_start_and_end(noisy_market):
    start, end = noisy_market.index[100], noisy_market.index[600]
    result = buy_and_hold.run(noisy_market, {"start": start, "end": end}, CTX)
    price = noisy_market["price"]
    assert result.equity.loc[end] / result.equity.loc[start] == pytest.approx(
        price.loc[end] / price.loc[start]
    )
    assert result.weights.loc[start] == 1  # bought at the start close
    assert result.weights.loc[end] == 0  # sold at the end close
    assert result.trades.iloc[0]["return"] == pytest.approx(price.loc[end] / price.loc[start] - 1)
    assert not result.trades.iloc[0].held_open


def test_buy_and_hold_with_no_dates_buys_on_day_one_and_never_sells(noisy_market):
    result = buy_and_hold.run(noisy_market, buy_and_hold.PARAMS, CTX)
    assert result.eval_start == noisy_market.index[0]
    assert result.trades.iloc[0].held_open


# ---- buying and selling because signals agree (or do not) ---------------------------------------
@signal("vix_is_high", limit=30)
def vix_is_high(data, limit):
    return data["vix"] > limit


@signal("price_is_low", limit=80)
def price_is_low(data, limit):
    return data["price"] < limit


def scenario(vix_points, price_points):
    price = piecewise(price_points)
    vix = piecewise(vix_points)
    return pd.DataFrame({"price": price, "signal": price, "vix": vix.to_numpy(), "risk_free": 0.0})


PRICE_FALLS = [(0, 100), (100, 100), (120, 60), (200, 60), (220, 100), (700, 100)]
PRICE_STAYS = [(0, 100), (700, 100)]
VIX_SPIKES = [(0, 15), (100, 15), (120, 50), (200, 50), (220, 15), (700, 15)]
VIX_STAYS = [(0, 15), (700, 15)]


def test_buys_when_both_signals_match_and_sells_a_year_later():
    data = scenario(VIX_SPIKES, PRICE_FALLS)  # VIX > 30 and price < 80 both hold on days ~110-210
    strategy = scale_in_strategy("t", all_of(vix_is_high, price_is_low), buy_weeks=2, hold_years=1)
    trade = strategy.run(data, strategy.params, CTX).trades.iloc[0]
    assert data.index[105] <= trade.entry_start <= data.index[215]
    assert 360 <= (trade.exit - trade.entry_start).days <= 372  # sold about a year after buying


def test_does_not_buy_when_only_the_vix_signal_matches():
    data = scenario(VIX_SPIKES, PRICE_STAYS)  # VIX spikes but price never gets low
    strategy = scale_in_strategy("t", all_of(vix_is_high, price_is_low))
    assert strategy.run(data, strategy.params, CTX).trades.empty


def test_does_not_buy_when_only_the_price_signal_matches():
    data = scenario(VIX_STAYS, PRICE_FALLS)  # price falls but VIX stays calm
    strategy = scale_in_strategy("t", all_of(vix_is_high, price_is_low))
    assert strategy.run(data, strategy.params, CTX).trades.empty


def test_any_of_buys_when_just_one_signal_matches():
    data = scenario(VIX_SPIKES, PRICE_STAYS)  # only the VIX signal matches
    strategy = scale_in_strategy("t", any_of(vix_is_high, price_is_low), buy_weeks=2)
    assert len(strategy.run(data, strategy.params, CTX).trades) == 1


def test_skips_every_tranche_when_the_tranche_filter_fails_on_the_buy_days():
    data = scenario(VIX_SPIKES, PRICE_FALLS)
    strategy = scale_in_strategy(
        "t",
        all_of(vix_is_high, price_is_low),
        tranche_filter=not_(vix_is_high),  # no buying while VIX is high, and it is high here
        buy_weeks=2,
    )
    result = strategy.run(data, strategy.params, CTX)
    assert result.trades.empty
    assert "no_entry" in set(result.events.event)  # logged: every tranche failed the filter


def test_signal_parameters_can_be_overridden_per_strategy():
    strategy = scale_in_strategy("t", deep_dip, signal_params={"deep_dip": {"min_depth": 0.5}})
    assert strategy.params["deep_dip"] == {"min_depth": 0.5, "lookback_days": None}


# ---- capitulation_confluence --------------------------------------------------------------------
def test_confluence_buys_once_when_vix_rsi_and_the_dip_all_agree(capitulation_market):
    strategy = capitulation_confluence.STRATEGY
    result = strategy.run(capitulation_market, strategy.params, CTX)
    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert capitulation_market.index[400] <= trade.entry_start <= capitulation_market.index[440]
    assert 360 <= (trade.exit - trade.entry_start).days <= 372  # sold about a year later


def test_confluence_does_not_buy_when_vix_stays_calm_even_with_a_deep_dip(capitulation_market):
    calm = capitulation_market.assign(vix=15.0)  # the price still crashes and rebounds
    strategy = capitulation_confluence.STRATEGY
    assert strategy.run(calm, strategy.params, CTX).trades.empty


# ---- episodes -----------------------------------------------------------------------------------
def test_signal_days_close_together_share_an_episode_and_distant_ones_start_a_new_one():
    days = pd.bdate_range("2020-01-01", periods=12)
    on = [0, 1, 1, 0, 0, 1, 0, 0, 0, 0, 0, 1]
    ids = cluster_ids(pd.Series(on, index=days, dtype=bool), cooldown_days=3)
    # days 1-2 and day 5 are within 3 days of each other (episode 1); day 11 is 6 days later
    assert ids.tolist() == [-1, 1, 1, -1, -1, 1, -1, -1, -1, -1, -1, 2]
