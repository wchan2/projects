"""Shared, causal signal building blocks (every value at date t uses data <= t): pluggable
filters, episode windows, extreme tracking and RSI. Strategy-specific logic lives in strategies/."""

import numpy as np
import pandas as pd

from registry import get, register


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


# ---- generic building blocks for indicator strategies (VIX, RSI, ...) ----------------------------
def label_windows(arm: np.ndarray, disarm: np.ndarray) -> np.ndarray:
    """Episode ids (1-based, -1 = none): an episode opens on the first `arm` day and closes on the
    first later `disarm` day. Causal: the id at t depends only on arm / disarm up to t."""
    ids = np.full(len(arm), -1, dtype=int)
    current, next_id = -1, 1
    for i in range(len(arm)):
        if current < 0:
            if arm[i]:
                current, next_id = next_id, next_id + 1
        elif disarm[i]:
            current = -1
        ids[i] = current
    return ids


def track_extreme(values: pd.Series, episode_id: pd.Series, mode: str) -> pd.DataFrame:
    """Running max (mode="max") or min (mode="min") of `values` inside each episode, the date it
    was set, and trading days since. A value must beat the previous extreme to be a new one."""
    sign = 1.0 if mode == "max" else -1.0
    vals, ep = values.to_numpy(float), episode_id.to_numpy()
    n = len(vals)
    ref = np.full(n, np.nan)
    since = np.full(n, -1)
    ref_pos = np.full(n, -1)
    current, best, best_i = -1, np.nan, -1
    for i in range(n):
        if ep[i] < 0:
            continue
        if ep[i] != current:
            current, best, best_i = ep[i], vals[i], i
        elif sign * vals[i] > sign * best:
            best, best_i = vals[i], i
        ref[i], ref_pos[i], since[i] = best, best_i, i - best_i
    dates = values.index
    return pd.DataFrame(
        {
            "ref_value": ref,
            "ref_date": [dates[j] if j >= 0 else pd.NaT for j in ref_pos],
            "days_since_ref": since,
        },
        index=dates,
    )


def rising_edge(condition: pd.Series) -> pd.Series:
    """True on the first day a condition becomes true (and again after it turns false)."""
    return condition & ~condition.shift(1, fill_value=False)


def episode_summary(feat: pd.DataFrame, ref_name: str) -> pd.DataFrame:
    """One row per episode: start, end (recovery_date; NaT while open), the reference extreme
    (named `ref_name`), and how many triggers fired."""
    rows = []
    in_ep = feat[feat["episode_id"] >= 0]
    n = len(feat)
    for eid, grp in in_ep.groupby("episode_id"):
        last_pos = feat.index.get_loc(grp.index[-1])
        rows.append(
            {
                "episode_id": int(eid),
                "start_date": grp.index[0],
                "recovery_date": feat.index[last_pos + 1] if last_pos + 1 < n else pd.NaT,
                f"{ref_name}_date": grp["ref_date"].iloc[-1],
                ref_name: grp["ref_value"].iloc[-1],
                "triggers": int(grp["trigger"].sum()),
            }
        )
    return pd.DataFrame(rows)
