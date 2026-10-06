"""Automatic crash-episode detection from price data alone (no hardcoded dates).

`label_episodes` is a causal state machine (value at t uses data <= t only); the episode table
is aggregated from its labels, so the strategy and the table share one definition.
"""
import numpy as np
import pandas as pd


def label_episodes(signal: pd.Series, threshold: float, merge_gap_days: int,
                   override=None) -> pd.DataFrame:
    """Per date: dd (drawdown from running all-time high), in_episode, episode_id (-1 = none).

    An episode starts when dd <= -threshold and ends at the first new high. A new crash that
    starts < merge_gap_days (calendar) after the previous recovery continues the same episode.
    `override` = [{start, end}, ...] replaces auto-detection with fixed windows.
    """
    px = signal.to_numpy(float)
    n = len(px)
    dates = signal.index
    run_max = np.maximum.accumulate(px)
    dd = px / run_max - 1.0
    ep = np.full(n, -1, dtype=int)

    if override:
        for k, w in enumerate(override, 1):
            m = (dates >= pd.Timestamp(w["start"])) & (dates <= pd.Timestamp(w["end"]))
            ep[m] = k
    else:
        in_ep, cur, nxt, last_end = False, -1, 1, None
        for i in range(n):
            if not in_ep:
                if dd[i] <= -threshold:
                    if cur >= 0 and last_end is not None and \
                            (dates[i] - dates[last_end]).days < merge_gap_days:
                        pass                    # merge: keep the previous episode id
                    else:
                        cur, nxt = nxt, nxt + 1
                    in_ep = True
            elif dd[i] >= 0.0:                  # new all-time high: episode over
                in_ep, last_end = False, i
            ep[i] = cur if in_ep else -1
    return pd.DataFrame({"dd": dd, "in_episode": ep >= 0, "episode_id": ep}, index=dates)


def detect_crash_episodes(signal: pd.Series, vix: pd.Series | None = None,
                          crash_threshold: float = 0.25, merge_gap_days: int = 60,
                          end_date=None, override=None) -> pd.DataFrame:
    """Episode table. days_to_trough = trading days peak->trough; days_to_recovery = trading
    days trough->new high (NaN while still open). Hindsight table: for reporting only."""
    signal = signal.dropna()
    if end_date is not None:
        signal = signal.loc[: pd.Timestamp(end_date)]
    lab = label_episodes(signal, crash_threshold, merge_gap_days, override)
    px, dates, dd = signal.to_numpy(float), signal.index, lab["dd"].to_numpy()
    run_max = np.maximum.accumulate(px)
    cols = ["episode_id", "start_date", "peak_date", "trough_date", "trough_depth",
            "days_to_trough", "days_to_recovery", "recovery_date", "vix_peak", "open"]
    rows = []
    for eid in sorted(e for e in lab["episode_id"].unique() if e >= 0):
        pos = np.flatnonzero(lab["episode_id"].to_numpy() == eid)
        s, e = pos[0], pos[-1]
        peak = np.flatnonzero(px[: s + 1] == run_max[s])[0] if not override else \
            int(np.argmax(px[: s + 1]))
        t = s + int(np.argmin(dd[s: e + 1]))
        is_open = e == len(px) - 1 or not (e + 1 < len(px) and dd[e + 1] >= 0)
        rec = None if is_open else e + 1
        v_end = dates[rec] if rec is not None else dates[-1]
        rows.append({
            "episode_id": int(eid), "start_date": dates[s], "peak_date": dates[peak],
            "trough_date": dates[t], "trough_depth": float(dd[t]),
            "days_to_trough": t - peak,
            "days_to_recovery": (rec - t) if rec is not None else np.nan,
            "recovery_date": dates[rec] if rec is not None else pd.NaT,
            "vix_peak": float(vix.loc[dates[peak]: v_end].max()) if vix is not None
            and vix.loc[dates[peak]: v_end].notna().any() else np.nan,
            "open": bool(is_open),
        })
    return pd.DataFrame(rows, columns=cols)
