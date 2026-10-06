"""Signals for the VIX-spike-fade strategy: spike episodes and the stabilizing-decline trigger."""

import pandas as pd

from signals import apply_filters, label_windows, rising_edge, track_extreme


def build_features(data: pd.DataFrame, params: dict) -> pd.DataFrame:
    vix = data["vix"]
    episode_id = pd.Series(
        label_windows(
            (vix >= params["spike_level"]).to_numpy(),
            (vix < params["reset_level"]).to_numpy(),
        ),
        index=data.index,
    )
    peak = track_extreme(vix, episode_id, "max")
    smooth = vix.rolling(params["smooth_days"]).mean()
    falling = smooth < smooth.shift(params["smooth_days"])
    signal = (
        (episode_id >= 0)
        & (peak["days_since_ref"] >= params["stable_days"])
        & (vix <= peak["ref_value"] * (1 - params["pullback"]))
        & falling
    )
    feat = data.assign(episode_id=episode_id, trigger=rising_edge(signal)).join(peak)
    return feat.join(apply_filters(feat, params["filters"]))
