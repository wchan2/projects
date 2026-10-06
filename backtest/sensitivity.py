"""Parameter grid runner. The grid belongs to the strategy (`Strategy.sensitivity_grid`)."""

import copy
import itertools

import numpy as np
import pandas as pd

from benchmarks import hold_from
from metrics import window
from strategy import Context, Strategy


def set_path(d: dict, dotted: str, value) -> None:
    *head, last = dotted.split(".")
    for k in head:
        d = d.setdefault(k, {})
    d[last] = value


def run_grid(
    strategy: Strategy,
    data: pd.DataFrame,
    ctx: Context,
    params: dict | None = None,
    grid: dict | None = None,
) -> pd.DataFrame:
    """One row per grid cell (default grid and params: the strategy's own). Value columns are
    measured from each cell's own eval_start, so they compare with buy-and-hold from that date."""
    params = strategy.params if params is None else params
    grid = strategy.sensitivity_grid if grid is None else grid
    capital = ctx.initial_capital
    keys, rows = list(grid), []
    for combo in itertools.product(*grid.values()):
        p = copy.deepcopy(params)
        for k, v in zip(keys, combo, strict=True):
            set_path(p, k, v)
        if "chained" in p:
            p["chained"] = True  # the grid needs a single equity curve
        r = strategy.run(data, p, ctx)
        if r.eval_start is None or r.equity is None:
            final = hold = capital
        else:
            final = float(window(r.equity, r.eval_start, capital).iloc[-1])
            held = hold_from(data, r.eval_start, ctx)
            hold = float(window(held.equity, held.eval_start, capital).iloc[-1])
        has_trades = r.trades is not None and len(r.trades)
        rows.append(
            {
                **dict(zip(keys, combo, strict=True)),
                "n_episodes": len(r.episodes) if r.episodes is not None else np.nan,
                "n_trades": len(r.trades) if r.trades is not None else 0,
                "final_value": final,
                "hold_final": hold,
                "worst_trade": float(r.trades["return"].min()) if has_trades else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    out["beats_hold"] = out["final_value"] > out["hold_final"]
    return out
