"""Cash / position ledger and the event log (including skipped signals)."""
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Portfolio:
    cash: float
    units: float = 0.0
    cost_bps: float = 0.0

    def value(self, price: float) -> float:
        return self.cash + self.units * price

    def accrue(self, daily_rate: float) -> None:
        self.cash *= 1.0 + daily_rate

    def buy(self, amount: float, price: float) -> float:
        """Spend up to `amount` of cash (fees come out of it). Returns cash spent."""
        spend = min(amount, self.cash)
        self.cash -= spend
        self.units += spend * (1 - self.cost_bps / 1e4) / price
        return spend

    def sell_all(self, price: float) -> float:
        proceeds = self.units * price * (1 - self.cost_bps / 1e4)
        self.cash += proceeds
        self.units = 0.0
        return proceeds


@dataclass
class EventLog:
    rows: list = field(default_factory=list)

    def add(self, date, episode, event: str, detail: str = "") -> None:
        self.rows.append({"date": date, "episode": episode, "event": event, "detail": detail})

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=["date", "episode", "event", "detail"])
