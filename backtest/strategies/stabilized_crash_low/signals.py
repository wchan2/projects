"""Signals for the stabilized-crash-low strategy: low tracking, stabilization, false starts and
triggers. Every value at date t depends only on data <= t."""

import numpy as np
import pandas as pd

from signals import apply_filters

from .episodes import label_episodes


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
                fs += 1  # stabilization was confirmed, then a new low
            cmin, cpos = px[i], i
        low[i], low_i[i], since[i] = cmin, cpos, i - cpos
        false_starts[i] = fs
        prev_since = since[i]
    dates = signal.index
    out = pd.DataFrame(
        {
            "ep_low": low,
            "ep_low_date": [dates[j] if j >= 0 else pd.NaT for j in low_i],
            "days_since_low": since,
            "false_starts": false_starts,
        },
        index=dates,
    )
    out["stable"] = (out["days_since_low"] >= stable_days) & (episode_id.to_numpy() >= 0)
    out["trigger"] = out["stable"] & ~out["stable"].shift(1, fill_value=False)
    return out


def build_features(data: pd.DataFrame, params: dict) -> pd.DataFrame:
    """data columns: price, signal, vix, rf. Returns data + episode labels, lows, triggers and
    filters."""
    lab = label_episodes(
        data["signal"],
        params["crash_threshold"],
        params["merge_gap_days"],
        params.get("override") or None,
    )
    trk = track_lows(data["signal"], lab["episode_id"], params["stable_days"])
    feat = data.join(lab).join(trk)
    return feat.join(apply_filters(feat, params.get("filters", {})))
