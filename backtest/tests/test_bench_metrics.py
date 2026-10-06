import numpy as np
import pandas as pd
import pytest

from benchmarks import build_benchmarks, standalone_summary
from metrics import cagr, max_drawdown, performance, sharpe, window
from sensitivity import run_grid, set_path
from strategies.stabilized_crash_low import STRATEGY
from tests.conftest import CTX, PARAMS


def test_metrics_known_values():
    idx = pd.bdate_range("2020-01-01", periods=253)
    eq = pd.Series(np.linspace(100, 200, 253), idx)
    assert max_drawdown(eq) == 0
    assert cagr(eq) == pytest.approx(1.0, abs=0.06)
    eq2 = pd.Series([100, 50, 100.0], pd.bdate_range("2020-01-01", periods=3))
    assert max_drawdown(eq2) == -0.5
    assert np.isnan(sharpe(pd.Series([0.01, 0.01, 0.01])))  # zero variance


def run(data, params=PARAMS, ctx=CTX):
    return STRATEGY.run(data, params, ctx)


def test_benchmarks_are_buy_and_hold_entered_with_the_strategy(noisy_market):
    r = run(noisy_market)
    holds = build_benchmarks(noisy_market, r.anchors, CTX)
    assert set(holds) == {"hold_first_signal", "hold_first_entry", "hold_first_low"}
    for name, held in holds.items():
        assert held.eval_start == r.anchors[name.removeprefix("hold_")]
        assert window(held.equity, held.eval_start, 1e4).iloc[0] == 1e4
    s = performance(r, noisy_market)
    assert s["final_value"] > 0 and 0 < s["time_in_market"] < 1
    assert s["n_trades"] == len(r.trades)


def test_engine_equity_matches_weights(noisy_market):
    """Equity recomputed from the reported weights equals the simulated equity (no costs)."""
    r = run(noisy_market)
    px, rf = noisy_market["price"], noisy_market["rf"]
    w = r.weights.shift(1).fillna(0)
    ret = w * px.pct_change().fillna(0) + (1 - w) * (rf.shift(1) / 252).fillna(0)
    np.testing.assert_allclose(1e4 * (1 + ret).cumprod(), r.equity, rtol=1e-9)


def test_standalone_and_grid(noisy_market):
    r = run(noisy_market, {**PARAMS, "chained": False})
    ss = standalone_summary(r.trades)
    assert len(ss) == len(r.trades) + 1
    grid = {
        "crash_threshold": [0.2, 0.3],
        "hold_years": [1, 2],
        "filters.vix_max.max": [30],
    }
    g = run_grid(STRATEGY, noisy_market, CTX, grid=grid)
    assert len(g) == 4 and {"final_value", "worst_trade", "n_episodes"} <= set(g.columns)
    d = {}
    set_path(d, "filters.vix_max.max", 5)
    assert d == {"filters": {"vix_max": {"max": 5}}}


def test_grid_comes_from_the_strategy(noisy_market):
    grid = STRATEGY.sensitivity_grid
    assert {"crash_threshold", "stable_days", "hold_years", "filters.vix_max.max"} <= set(grid)
