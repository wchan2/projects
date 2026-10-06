"""Causal signal features: low tracking, stabilization, false starts and pluggable filters.
Every value at date t depends only on data <= t."""
import numpy as np
import pandas as pd

from episodes import label_episodes
from registry import available, get, register


# ---- filters: fn(features, **params) -> boolean Series (NaN inputs evaluate to False) ----------
@register("filter", "vix_max")
def vix_max(feat: pd.DataFrame, max: float = 30, **_) -> pd.Series:
    return feat["vix"] < max


@register("filter", "above_ma")
def above_ma(feat: pd.DataFrame, window: int = 200, **_) -> pd.Series:
    return feat["signal"] > feat["signal"].rolling(window).mean()


@register("filter", "min_depth")
def min_depth(feat: pd.DataFrame, min_depth: float = 0.15, **_) -> pd.Series:
    return feat["dd"] <= -min_depth


def apply_filters(feat: pd.DataFrame, filter_cfg: dict) -> pd.DataFrame:
    """One bool column f_<name> per enabled filter, plus filters_pass and first_fail (name)."""
    out = pd.DataFrame(index=feat.index)
    for name, params in filter_cfg.items():
        params = dict(params or {})
        if not params.pop("enabled", True):
            continue
        out[f"f_{name}"] = get("filter", name)(feat, **params).fillna(False).astype(bool)
    fcols = list(out.columns)
    out["filters_pass"] = out[fcols].all(axis=1) if fcols else True
    first = out[fcols].idxmin(axis=1).str[2:] if fcols else pd.Series("", index=feat.index)
    out["first_fail"] = first.where(~out["filters_pass"], "")
    return out


# ---- low tracking / stabilization --------------------------------------------------------------
def track_lows(signal: pd.Series, episode_id: pd.Series, stable_days: int) -> pd.DataFrame:
    """Running minimum close within each episode, trading days since it, stabilization flag
    (no new low for stable_days) and the cumulative count of false starts (stabilization had
    been confirmed, then a new low followed)."""
    px, ep = signal.to_numpy(float), episode_id.to_numpy()
    n = len(px)
    low = np.full(n, np.nan)
    low_i = np.full(n, -1)
    since = np.full(n, -1)
    false_starts = np.zeros(n, dtype=int)
    cur, cmin, cpos, fs, prev_since = -1, np.inf, -1, 0, -1
    for i in range(n):
        e = ep[i]
        if e < 0:
            false_starts[i] = fs if cur >= 0 else 0
            continue
        if e != cur:
            cur, cmin, cpos, fs, prev_since = e, px[i], i, 0, -1
        elif px[i] < cmin:
            if prev_since >= stable_days:
                fs += 1                          # stabilization was confirmed, then a new low
            cmin, cpos = px[i], i
        low[i], low_i[i], since[i] = cmin, cpos, i - cpos
        false_starts[i] = fs
        prev_since = since[i]
    dates = signal.index
    out = pd.DataFrame({
        "ep_low": low,
        "ep_low_date": [dates[j] if j >= 0 else pd.NaT for j in low_i],
        "days_since_low": since,
        "false_starts": false_starts,
    }, index=dates)
    out["stable"] = (out["days_since_low"] >= stable_days) & (episode_id.to_numpy() >= 0)
    out["trigger"] = out["stable"] & ~out["stable"].shift(1, fill_value=False)
    return out


def build_features(data: pd.DataFrame, episodes_cfg: dict, strategy_cfg: dict) -> pd.DataFrame:
    """data columns: price, signal, vix, rf. Returns data + episode labels, lows, triggers, filters."""
    lab = label_episodes(data["signal"], episodes_cfg["crash_threshold"],
                         episodes_cfg["merge_gap_days"], episodes_cfg.get("override") or None)
    trk = track_lows(data["signal"], lab["episode_id"], strategy_cfg["stable_days"])
    feat = data.join(lab).join(trk)
    return feat.join(apply_filters(feat, strategy_cfg.get("filters", {})))


__all__ = ["build_features", "apply_filters", "track_lows", "available"]
