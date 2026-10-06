import numpy as np
import pandas as pd
import pytest
import yaml

from benchmarks import build_benchmarks, hold_equity, standalone_summary
from metrics import cagr, max_drawdown, sharpe, summarize
from sensitivity import run_grid, set_path
from strategy import run_strategy

CFG = yaml.safe_load(open("config.yaml"))


def test_metrics_known_values():
    idx = pd.bdate_range("2020-01-01", periods=253)
    eq = pd.Series(np.linspace(100, 200, 253), idx)
    assert max_drawdown(eq) == 0
    assert cagr(eq) == pytest.approx(1.0, abs=0.06)
    eq2 = pd.Series([100, 50, 100.0], pd.bdate_range("2020-01-01", periods=3))
    assert max_drawdown(eq2) == -0.5
    assert np.isnan(sharpe(pd.Series([0.01, 0.01, 0.01])))   # zero variance


def test_hold_and_summary(noisy_market):
    r = run_strategy(noisy_market, CFG["strategy"], CFG["episodes"], 1e4)
    b = build_benchmarks(noisy_market["price"], r.anchors, 1e4)
    assert set(b) == {"hold_first_signal", "hold_first_low", "hold_first_entry"}
    assert all(abs(v.iloc[0] - 1e4) < 1e-6 for v in b.values())
    s = summarize(r.equity, r.weights, r.trades, noisy_market["rf"], r.anchors["first_signal"])
    assert s["final_value"] > 0 and 0 < s["time_in_market"] < 1
    assert s["n_trades"] == len(r.trades)


def test_engine_equity_matches_weights(noisy_market):
    """Equity recomputed from the reported weights equals the simulated equity (no costs)."""
    st = {**CFG["strategy"], "cost_bps": 0.0}
    r = run_strategy(noisy_market, st, CFG["episodes"], 1e4)
    px, rf = noisy_market["price"], noisy_market["rf"]
    w = r.weights.shift(1).fillna(0)
    ret = w * px.pct_change().fillna(0) + (1 - w) * (rf.shift(1) / 252).fillna(0)
    np.testing.assert_allclose(1e4 * (1 + ret).cumprod(), r.equity, rtol=1e-9)


def test_standalone_and_grid(noisy_market):
    r = run_strategy(noisy_market, {**CFG["strategy"], "chained": False}, CFG["episodes"], 1e4)
    ss = standalone_summary(r.trades)
    assert len(ss) == len(r.trades) + 1
    g = run_grid(noisy_market, CFG["strategy"], CFG["episodes"],
                 {"crash_threshold": [0.2, 0.3], "hold_years": [1, 2], "filters.vix_max.max": [30]})
    assert len(g) == 4 and {"final_value", "worst_trade", "n_episodes"} <= set(g.columns)
    d = {}
    set_path(d, "filters.vix_max.max", 5)
    assert d == {"filters": {"vix_max": {"max": 5}}}
