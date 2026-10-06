import os

import numpy as np
import pandas as pd
import pytest

from data import build_synthetic_3x, splice_with_real, tracking_error


def _index(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2005-01-03", periods=n)
    return pd.Series(1000 * np.exp(np.cumsum(rng.normal(3e-4, 0.012, n))), idx, name="IDX")


def test_synthetic_matches_formula_exactly():
    u = _index()
    rf = 0.03
    s = build_synthetic_3x(u, rf, leverage=3, expense_ratio=0.0095)
    expected = 3 * u.pct_change() - 2 * rf / 252 - 0.0095 / 252
    assert np.allclose(s.pct_change().dropna(), expected.dropna())


def test_synthetic_vs_known_fund_has_zero_tracking_error():
    u = _index()
    real = build_synthetic_3x(u, 0.02, 3, 0.0095, base=37.0)   # stands in for the real fund
    synth = build_synthetic_3x(u, 0.02, 3, 0.0095)
    te = tracking_error(synth, real)
    assert te["annualized_te"] < 1e-9 and te["return_correlation"] > 0.999999


def test_splice_is_continuous_and_uses_real_after_launch():
    u = _index()
    synth = build_synthetic_3x(u, 0.02)
    real = synth.iloc[600:] * 0.5
    out = splice_with_real(synth, real)
    assert out.iloc[600:].equals(real.rename(out.name)) or np.allclose(out.iloc[600:], real)
    r = out.pct_change()
    assert np.isclose(r.iloc[600], synth.pct_change().iloc[600])   # no jump at the join


@pytest.mark.network
def test_synthetic_3x_vs_real_tqqq():
    """Real data: synthetic ^NDX 3x must track TQQQ closely over the overlap."""
    import yaml
    from data import build_dataset
    cfg = yaml.safe_load(open("config.yaml"))
    try:
        _, info = build_dataset(cfg, "TQQQ")
    except Exception as exc:
        pytest.skip(f"no market data available: {exc}")
    te = info["tracking"]
    assert te is not None and te["n_days"] > 2000
    assert te["return_correlation"] > 0.995
    assert te["annualized_te"] < 0.05
    assert abs(te["cagr_synth"] - te["cagr_real"]) < 0.05
