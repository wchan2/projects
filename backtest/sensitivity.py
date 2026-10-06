"""Parameter grid runner: CRASH_THRESHOLD x STABLE_DAYS x HOLD_YEARS x VIX_MAX (any keys)."""
import copy
import itertools

import numpy as np
import pandas as pd

from benchmarks import hold_equity
from metrics import window
from strategy import run_strategy


def set_path(d: dict, dotted: str, value) -> None:
    *head, last = dotted.split(".")
    for k in head:
        d = d.setdefault(k, {})
    d[last] = value


def run_grid(data: pd.DataFrame, strategy_cfg: dict, episodes_cfg: dict, grid: dict,
             capital: float = 10_000, trading_days: int = 252) -> pd.DataFrame:
    """One row per grid cell. Value columns use the window from each cell's first signal, so
    cells are comparable with the buy-and-hold from that same date."""
    keys = list(grid)
    rows = []
    for combo in itertools.product(*grid.values()):
        st, ep = copy.deepcopy(strategy_cfg), copy.deepcopy(episodes_cfg)
        for k, v in zip(keys, combo):
            set_path(ep if k.split(".")[0] in ep else st, k, v)
        r = run_strategy(data, {**st, "chained": True}, ep, capital, trading_days)
        start = r.anchors.get("first_signal")
        if start is None:
            final = hold = capital
        else:
            final = float(window(r.equity, start, capital).iloc[-1])
            hold = float(hold_equity(data["price"], start, capital).iloc[-1])
        rows.append({**dict(zip(keys, combo)), "n_episodes": len(r.episodes),
                     "n_trades": len(r.trades), "final_value": final, "hold_final": hold,
                     "worst_trade": float(r.trades["return"].min()) if len(r.trades) else np.nan})
    out = pd.DataFrame(rows)
    out["beats_hold"] = out["final_value"] > out["hold_final"]
    return out
