"""Rules: how a strategy turns signals and its own state into a decision.

A strategy is a set of signals plus a *rule*. Each day the rule looks at today's signal values and
the strategy's current state (flat or holding, how long) and returns an action:

    def rule(signals: SignalValues, state: State, params: dict) -> Action:
        if state.flat:
            return Action.BUY if signals.dip and signals.rsi_up else Action.HOLD
        if state.days_held >= params["min_hold_days"] and signals.overbought:
            return Action.SELL
        return Action.HOLD

Signals stay neutral yes/no conditions (`signals.py`); the rule decides what they mean, and the same
signal can mean different things depending on the state. A rule is a pure function: no prices, no
money, no side effects, so it can be tested with plain values.

Where things live when a strategy runs:
- Signals are computed once, up front, over the whole history (using the indicators). `Signal`
  (signals.py) is the definition; `SignalValues` (here) is one day's readings of them.
- The `State` belongs to the daily runner, not to the strategy: the runner creates it at the start
  of a run, replaces it each day, and hands the rule a read-only snapshot.
- The rule only ever sees `SignalValues`, `State` and its parameters, never prices or cash. The
  account (cash and shares) is the runner's business now and a portfolio ledger's later.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import Enum

import pandas as pd


class Action(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(frozen=True)
class State:
    """The state of ONE position in ONE asset, within a single run: what a strategy knows about
    itself on a given day. Immutable: every change returns a new State, and the owner (the runner)
    replaces its copy.

    The `Strategy` object itself is stateless, so one strategy can be reused across runs, assets and
    parameter sweeps; the state belongs to a (strategy, asset) pair for the length of a run. With
    several assets there is one State per asset, and a portfolio ledger (later) would keep them,
    together with cash and profit, privately in a separate portfolio state.

    holding         True while a position is held.
    days_held       trading days since the buy was filled (0 on the day it fills).
    days_since_sale trading days since the last sale, or None if nothing was ever sold. None is not
                    a cooldown: a strategy that has never sold is free to buy.
    entry_day       the day the current position was bought, or None when flat.
    """

    holding: bool = False
    days_held: int = 0
    days_since_sale: int | None = None
    entry_day: pd.Timestamp | None = None

    @property
    def flat(self) -> bool:
        return not self.holding

    def cooled_down(self, days: int) -> bool:
        """True if it has been at least `days` trading days since the last sale (or none yet)."""
        return self.days_since_sale is None or self.days_since_sale >= days

    def advance(self) -> State:
        """The state one trading day later, with nothing bought or sold."""
        if self.holding:
            return replace(self, days_held=self.days_held + 1)
        if self.days_since_sale is not None:
            return replace(self, days_since_sale=self.days_since_sale + 1)
        return self

    def bought(self, day: pd.Timestamp) -> State:
        """The state right after a buy fills on `day`."""
        return State(holding=True, days_held=0, days_since_sale=None, entry_day=day)

    def sold(self) -> State:
        """The state right after a sale fills: flat, with the cooldown clock starting at 0."""
        return State(holding=False, days_held=0, days_since_sale=0, entry_day=None)


class SignalValues:
    """Today's value of every signal a strategy uses, read as attributes (`signals.rsi_up`).

    A `Signal` (signals.py) is the definition, a function that computes a yes/no series over the
    whole history; `SignalValues` is its readings for one day, handed to the rule.

    Read-only: setting or deleting an attribute raises. Values are booleans for the signals we have
    now; numbers are allowed so rules can read numeric indicators later.
    """

    def __init__(self, values: Mapping[str, bool | float]):
        object.__setattr__(self, "_values", dict(values))

    def __getattr__(self, name: str) -> bool | float:
        values = object.__getattribute__(self, "_values")
        try:
            return values[name]
        except KeyError:
            raise AttributeError(f"no signal named '{name}'; available: {sorted(values)}") from None

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("signal values are read-only")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("signal values are read-only")

    def __repr__(self) -> str:
        return f"SignalValues({self._values})"

    @property
    def names(self) -> list[str]:
        return list(self._values)

    def true_names(self) -> list[str]:
        """Names of the signals that are on today, in the order they were given. Used to explain a
        decision in the event log ("BUY because: crash, vix_fading, rsi_up")."""
        return [name for name, value in self._values.items() if value]


# A rule: today's signals, the strategy's state and its parameters in, an action out.
Rule = Callable[[SignalValues, State, dict], Action]
