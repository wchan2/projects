from dataclasses import replace

import pandas as pd

from strategies.stabilized_crash_low import STRATEGY
from tests.conftest import CTX, PARAMS, piecewise

NO_FILTERS = {**PARAMS, "filters": {}}


def run(data, params=PARAMS, ctx=CTX):
    return STRATEGY.run(data, params, ctx)


def test_scale_in_and_timed_exit(noisy_market):
    params = {**NO_FILTERS, "hold_years": 1}
    r = run(noisy_market, params, replace(CTX, execution_lag=0))
    t = r.trades.iloc[0]
    assert t.n_tranches == params["buy_weeks"]
    assert 360 <= (t.exit - t.entry_start).days <= 372  # ~1 year after the first tranche
    assert (r.events.event == "triggered").sum() >= 1


def test_weights_bounded_and_equity_positive(noisy_market):
    r = run(noisy_market)
    assert r.weights.between(0, 1 + 1e-9).all()
    assert (r.equity > 0).all()


def test_execution_lag_delays_first_fill(noisy_market):
    a = run(noisy_market, NO_FILTERS, replace(CTX, execution_lag=0))
    b = run(noisy_market, NO_FILTERS, replace(CTX, execution_lag=1))
    assert (b.trades.entry_start.iloc[0] - a.trades.entry_start.iloc[0]).days >= 1


def test_trigger_during_open_position_is_skipped_and_logged():
    # two crashes; the second stabilizes while the (long) hold from the first is still open
    s = piecewise(
        [
            (0, 100),
            (40, 60),
            (200, 60.5),
            (260, 101),
            (300, 101),
            (340, 60),
            (520, 60.5),
            (700, 130),
        ]
    )
    data = pd.DataFrame({"price": s, "signal": s, "vix": 20.0, "rf": 0.0})
    params = {**NO_FILTERS, "hold_years": 5, "merge_gap_days": 5, "buy_weeks": 2}
    r = run(data, params)
    skipped = r.events[r.events.event == "skipped"]
    assert len(r.trades) == 1
    assert (skipped.detail == "position_open").any()


def test_filter_blocks_entry(noisy_market):
    r = run(noisy_market.assign(vix=60.0))
    assert r.trades.empty
    assert (r.events.event == "no_entry").any()


def test_standalone_mode_runs_each_episode_independently(noisy_market):
    r = run(noisy_market, {**NO_FILTERS, "chained": False})
    assert r.equity is None
    assert len(r.trades) == r.trades.episode.nunique() >= 1
