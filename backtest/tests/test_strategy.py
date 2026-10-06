import numpy as np
import pandas as pd
import pytest

from strategy import run_strategy
from tests.conftest import piecewise
import yaml

CFG = yaml.safe_load(open("config.yaml"))
EP, ST = CFG["episodes"], dict(CFG["strategy"])


def test_scale_in_and_timed_exit(noisy_market):
    st = {**ST, "hold_years": 1, "execution_lag": 0, "filters": {}}
    r = run_strategy(noisy_market, st, EP, 10_000)
    t = r.trades.iloc[0]
    assert t.n_tranches == st["buy_weeks"]
    first = t.entry_start
    gap_days = (t.exit - first).days
    assert 360 <= gap_days <= 372                       # ~1 year after the first tranche
    assert (r.events.event == "triggered").sum() >= 1


def test_weights_bounded_and_equity_positive(noisy_market):
    r = run_strategy(noisy_market, ST, EP, 10_000)
    assert r.weights.between(0, 1 + 1e-9).all() and (r.equity > 0).all()


def test_execution_lag_delays_first_fill(noisy_market):
    a = run_strategy(noisy_market, {**ST, "execution_lag": 0, "filters": {}}, EP, 1e4)
    b = run_strategy(noisy_market, {**ST, "execution_lag": 1, "filters": {}}, EP, 1e4)
    assert (b.trades.entry_start.iloc[0] - a.trades.entry_start.iloc[0]).days >= 1


def test_trigger_during_open_position_is_skipped_and_logged():
    # two crashes, second stabilizes while the (long) hold from the first is still open
    s = piecewise([(0, 100), (40, 60), (200, 60.5), (260, 101), (300, 101), (340, 60),
                   (520, 60.5), (700, 130)])
    d = pd.DataFrame({"price": s, "signal": s, "vix": 20.0, "rf": 0.0})
    st = {**ST, "hold_years": 5, "filters": {}, "merge_gap_days": 5, "buy_weeks": 2}
    r = run_strategy(d, st, {**EP, "merge_gap_days": 5}, 1e4)
    skipped = r.events[r.events.event == "skipped"]
    assert len(r.trades) == 1 and (skipped.detail == "position_open").any()


def test_filter_blocks_entry(noisy_market):
    nm = noisy_market.assign(vix=60.0)
    r = run_strategy(nm, ST, EP, 1e4)
    assert r.trades.empty and (r.events.event == "no_entry").any()


def test_standalone_mode_runs_each_episode_independently(noisy_market):
    r = run_strategy(noisy_market, {**ST, "chained": False, "filters": {}}, EP, 1e4)
    assert r.equity is None and len(r.trades) == r.trades.episode.nunique() >= 1


def test_strategy_has_no_lookahead(noisy_market):
    """Weights up to t are identical when all data after t is removed."""
    full = run_strategy(noisy_market, ST, EP, 1e4)
    for cut in (500, 700, 900, 1000, 1150):
        part = run_strategy(noisy_market.iloc[:cut], ST, EP, 1e4)
        np.testing.assert_allclose(part.weights.to_numpy(), full.weights.iloc[:cut].to_numpy())
        np.testing.assert_allclose(part.equity.to_numpy(), full.equity.iloc[:cut].to_numpy())
