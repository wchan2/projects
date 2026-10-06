"""Signals for the RSI-oversold-bounce strategy: Wilder RSI, oversold episodes and the
stabilized-and-bouncing trigger."""

import pandas as pd

from signals import apply_filters, label_windows, rising_edge, track_extreme


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (causal)."""
    change = close.diff()
    avg_gain = change.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = (
        (-change.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    )
    return 100 - 100 / (1 + avg_gain / avg_loss)


def build_features(data: pd.DataFrame, params: dict) -> pd.DataFrame:
    strength = rsi(data["signal"], params["rsi_period"])
    episode_id = pd.Series(
        label_windows(
            (strength < params["oversold"]).to_numpy(),
            (strength >= params["reset_level"]).to_numpy(),
        ),
        index=data.index,
    )
    low = track_extreme(strength, episode_id, "min")
    signal = (
        (episode_id >= 0)
        & (low["days_since_ref"] >= params["stable_days"])
        & (strength >= low["ref_value"] + params["bounce"])
    )
    feat = data.assign(rsi=strength, episode_id=episode_id, trigger=rising_edge(signal)).join(low)
    return feat.join(apply_filters(feat, params["filters"]))
