"""Buy and hold: buy at the close on `start`, sell at the close on `end`.

Also the benchmark for every other strategy: it is run with `start` set to the date the other
strategy entered, i.e. what $10k put in at the same time would have done. `start` / `end` of None
mean the first / last date of the data. Cash outside the window earns the risk-free rate.
"""

import numpy as np
import pandas as pd

from strategy import Context, Strategy, StrategyResult, equity_from_weights

PARAMS = {
    "start": None,  # e.g. "2009-03-09"; None = first date of the data
    "end": None,  # e.g. "2013-03-09"; None = held to the last date
}


def run(data: pd.DataFrame, params: dict, ctx: Context) -> StrategyResult:
    """data: price, vix, rf. Held from the close of the first trading day >= start until the
    close of the first trading day >= end (still held at the last date if end is None)."""
    price, dates = data["price"], data.index
    first = int(dates.searchsorted(pd.Timestamp(params["start"]))) if params.get("start") else 0
    last = int(dates.searchsorted(pd.Timestamp(params["end"]))) if params.get("end") else len(dates)
    if first >= len(dates) or last <= first:
        return StrategyResult(None, None, pd.DataFrame(), pd.DataFrame(), None)

    held = np.zeros(len(dates))
    held[first : min(last, len(dates))] = 1.0  # weight is post-trade: flat again at the exit close
    weights = pd.Series(held, dates, name="weight")
    equity = equity_from_weights(price, data["rf"], weights, ctx)

    exit_i = min(last, len(dates) - 1)
    path = price.iloc[first : exit_i + 1]
    trade = {
        "episode": 1,
        "trigger": dates[first],
        "entry_start": dates[first],
        "entry_end": dates[first],
        "n_tranches": 1,
        "exit": dates[exit_i],
        "held_open": last >= len(dates),
        "vix_at_entry": data["vix"].iat[first],
        "avg_entry_price": price.iat[first],
        "exit_price": price.iat[exit_i],
        "return": price.iat[exit_i] / price.iat[first] - 1,
        "max_dd_during_hold": float((path / path.cummax() - 1).min()),
    }
    return StrategyResult(
        equity,
        weights,
        pd.DataFrame([trade]),
        pd.DataFrame(columns=["date", "episode", "event", "detail"]),
        None,
        eval_start=dates[first],
    )


STRATEGY = Strategy(
    description=(
        "Buy and hold the instrument between a start and an end date (default: the whole "
        "history). Used as the benchmark for every other strategy."
    ),
    run=run,
    params=PARAMS,
)
