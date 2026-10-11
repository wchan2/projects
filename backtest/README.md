# Backtest

A modular Python backtester. It loads (and caches) price data for any ticker, runs every strategy in
`strategies/` on top of it, and reports trades, performance, buy-and-hold benchmarks and parameter
sensitivity.

Any ticker works, so the same code runs on TQQQ, FNGU, QQQ, SSO, UPRO, or a plain stock.

The design is built in layers, each doing one job and depending only on the one below it:

| Layer | Job | Example |
|---|---|---|
| **Data** | Real prices, VIX and the risk-free rate in one table | `price`, `signal`, `vix`, `risk_free` |
| **Indicators** | Numbers calculated from the data | the RSI value, how far price is below its high |
| **Signals** | Neutral yes/no conditions built on indicators | "RSI is below 30" (oversold) |
| **Strategies** | Combine signals into buying and selling | "buy when VIX fades, RSI bounces and we are in a dip" |
| **Results** | Trades, equity, performance, reports | `outputs/` |

## 1. Setup

```bash
uv sync                          # creates .venv and installs exact versions from uv.lock
```

Run tests:

```bash
uv run pytest
```

Lint and format:

```bash
uv run ruff check . && uv run ruff format .
```

## 2. Run it

```bash
uv run python main.py                        # every strategy on TQQQ, last 5 years (short output)
uv run python main.py --verbose              # also print the full tables for each strategy
uv run python main.py --instrument UPRO      # any ticker
uv run python main.py --start 2018-01-01 --end 2023-12-31   # choose the backtest window
uv run python main.py --full-history         # from the instrument's first day instead of 5 years
uv run python main.py --no-sensitivity       # skip the parameter grids (fast)
uv run python main.py --refresh              # force a re-download of price data
uv run python main.py --capital 50000        # starting capital (default 10,000)
```

By default the backtest covers the last 5 years (`--start` / `--end` choose another window, `--end` alone
counts back 5 years from that date, `--full-history` uses everything). It can never begin before the
instrument existed (TQQQ: 2010-02-11). The first run downloads the full price
history from Yahoo Finance and caches it as parquet files in `data_cache/`, so different
date windows reuse the same cache.
Results are printed and written to `outputs/`: a `comparison.csv` across strategies, plus one folder
per strategy:

| Output | Contents |
|---|---|
| `report.md` | All tables below plus the assumptions |
| `episodes.csv` | The strategy's auto-detected episodes (start, end, reference extreme, triggers, ...) |
| `trades.csv` | Per trade: trigger, entry window, exit, VIX at entry, return, max drawdown in hold |
| `events.csv` | Every trigger and every skipped signal with its reason |
| `summary.csv` | Final value of $10k, CAGR, max drawdown, Sharpe/Sortino, time in market, trades |
| `sensitivity.csv` | The strategy's own parameter grid: final value, worst trade, episodes detected |
| `standalone.csv` | Each episode as its own $10k account (chained vs standalone) |
| `*.png` | Log equity curves, drawdown, VIX with entry/exit markers (episodes shaded) |

## 3. Strategies

Each strategy is a module (or folder) under `strategies/` that exposes a `STRATEGY`, and `main.py`
backtests every one it finds. Most are built by composing the reusable signals in `signals.py`.

| Strategy | Idea |
|---|---|
| `stabilized_crash_low/` | After the index falls 25%+ from its high and makes no new low for 63 trading days, scale in over 8 weeks, hold 2 years, sell. Crash episodes are auto-detected, never hardcoded, and that logic stays private to this folder. |
| `vix_spike_fade.py` | Entry signal `vix_stabilizing`: VIX closed above 30, peaked, fell 25% from the peak and keeps drifting down. |
| `rsi_oversold_bounce.py` | Entry signal `rsi_bounce`: RSI(14) fell below 30, made no new low for 5 days and bounced 5 points. |
| `capitulation_confluence.py` | Entry only when all three agree: `vix_stabilizing`, `rsi_bounce` (each within the last 10 days) and a `deep_dip` in the index. |
| `buy_and_hold.py` | Buy at `start`, sell at `end` (default: whole history). Also the benchmark: every other strategy is compared with $10k bought at the moment it entered. |

All parameters live in the strategy's `params` (the signals' defaults plus the scale-in settings), so
tuning means changing those. The defaults are starting guesses, not optimized.

## 4. How it works

```
main.py ──► data.py ──► (price, signal, vix, risk_free)
              │                   │
        cached parquet            ▼
                          indicators.py ──► signals.py ──► strategies/* ──► StrategyResult ──► report.py
                          (numbers)         (yes/no)       strategy.py       │
                                                           (contract,        metrics.py · benchmarks.py
                                                            scale-in engine) sensitivity.py
                                                            portfolio.py
```

**Design principles**
- **Causal:** every indicator, signal and decision at day *t* uses only data up to day *t*. Tests check
  this by cutting off later data and confirming nothing earlier changes.
- **Neutral signals:** a signal only says whether a condition holds. The strategy decides whether that
  means buy, sell or nothing.
- **Each component owns its state** and shares only read-only views of it (the data table is the
  market history, a strategy tracks its own position, and the planned portfolio ledger will keep cash and
  profit private). See the roadmap.

### Data (`data.py`)
- Downloads adjusted closes for the instrument, its signal index, `^VIX` and a risk-free rate
  (`^IRX`), and caches each ticker to parquet. Settings are the `DataSettings` dataclass.
- Prices are real only: a backtest starts when the instrument started trading, and `--start` /
  `--end` limit the window (default: the last 5 years). Nothing is ever simulated before the
  instrument existed.
- `build_dataset()` returns one standard frame (`price`, `signal`, `vix`, `risk_free`) that every strategy
  consumes. `signal` is the series strategies read their signals from: the index a leveraged fund
  tracks (`SIGNAL_INDEX`, e.g. `^NDX` for TQQQ) or the instrument itself.

### Strategy interface (`strategy.py`)
- A `Strategy` is a description, default `params`, a `run(data, params, ctx)` function and its own
  `sensitivity_grid`. Data goes in, a `StrategyResult` (equity, weights, trades, events, episodes)
  comes out, and `metrics.performance(result, data)` extracts the performance.
- `Context` holds backtest-wide settings: capital, execution lag, cash earning the risk-free rate,
  slippage.
- The "wait for a signal, scale in, hold, sell" strategies share one engine, `scale_in()`: equal weekly
  tranches (each checked against an optional tranche-filter signal), a timed exit, cash earning the
  risk-free rate, proceeds redeployed at the next episode (**chaining**), and triggers during an open
  position logged as `skipped`. A strategy only has to supply its entry signal.
- **No lookahead:** decisions use only data up to that date, and orders fill `execution_lag` days later.

### Indicators (`indicators.py`)
- An indicator turns the data into a number for each day, and says nothing about what the number
  means: `rsi` (Wilder's relative strength index, 0-100), `drawdown_from_high` (how far price is below
  its high, e.g. -0.25), `moving_average`, and `run_length` (how many days in a row a condition has held).
- They are plain functions of the history they are given: nothing is stored between calls, so a
  backtest has no hidden indicator state. (RSI is a running average that depends on all earlier data
  with decaying weight, not just the last 14 closes; a live system would either keep a rolling history
  buffer or keep the running averages.)
- A signal turns an indicator into a label by thresholding it: "RSI below 30" is *oversold*, "RSI at
  or above 70" is *overbought*.

### Signals and composing strategies (`signals.py`)
- A `Signal` is a reusable, parameterized condition built on the indicators: `signal(data, params)` returns a boolean series,
  true on the days the condition holds, using only data up to that day. The library has `vix_below`,
  `above_moving_average`, `deep_dip`, `vix_stabilizing` and `rsi_bounce`.
- Signals combine with `all_of`, `any_of`, `not_` and `recently(signal, days)`, and a combination is
  itself a signal. Each signal reads its own namespace of `params` (`params["rsi_bounce"]["oversold"]`),
  so a sensitivity grid can sweep any signal's parameters (`"rsi_bounce.oversold": [25, 30, 35]`).
- `scale_in_strategy(entry=..., tranche_filter=...)` in `strategy.py` turns any entry signal into a
  full strategy. A new strategy is then a few lines:
  ```python
  STRATEGY = scale_in_strategy(
      description="...",
      entry=all_of(recently(vix_stabilizing, 10), recently(rsi_bounce, 10), deep_dip),
  )
  ```
- A new signal is one decorated function: `@signal("name", threshold=5)` over `f(data, threshold)`.
- Anything specific to one strategy stays inside its folder (the crash episode detector in
  `stabilized_crash_low/`) and is not used by the rest of the code.

### Comparison and analysis
- `benchmarks.py`: runs the `buy_and_hold` strategy from each date a strategy reports (first signal,
  first entry, ...), so you see what $10k put in at the same time would have done.
- `metrics.py`: CAGR, max drawdown, Sharpe, Sortino, time in market.
- `sensitivity.py`: runs a strategy over its own grid (dotted keys reach nested params).
- `report.py`: writes the tables and charts.

## 5. Extending it

| To add... | Do this |
|---|---|
| A strategy | Add a module in `strategies/` exposing `STRATEGY` (usually `scale_in_strategy(entry=<signal>)`); it is picked up automatically |
| An indicator | Add a causal function that returns a number per day to `indicators.py` |
| A signal | Decorate a function with `@signal("name", **defaults)` in `signals.py` (usually a threshold on an indicator), then combine it with `all_of` / `any_of` / `recently` |
| An instrument | Nothing: any ticker works. To read signals from an index instead, add it to `SIGNAL_INDEX` in `data.py` |
| A data source | `@register("fetcher", "name")` on a function in `data.py` |

## 6. Glossary

Terms used in the code and reports, and where they live.

| Term | Meaning | Where |
|---|---|---|
| **Instrument** | The thing being bought and sold, e.g. TQQQ. | `data.py` (`price` column) |
| **Signal index** | The series signals are computed from, e.g. `^NDX` for TQQQ. The `signal` column in the data. | `data.py` (`SIGNAL_INDEX`) |
| **Indicator** | A number calculated from the data each day (RSI value, drawdown from the high, moving average). It has no opinion about what the number means. | `indicators.py` |
| **RSI** | Relative strength index, 0-100: how strong recent gains are compared with recent losses. | `indicators.py` |
| **Overbought / oversold** | RSI labels: *overbought* means RSI is high (commonly 70 or more, after a strong run), *oversold* means it is low (commonly 30 or less, after a sharp fall). | `signals.py` |
| **Elevated fear / calm** | VIX is a fear gauge, so it is not called overbought or oversold: high VIX is elevated fear (panic), low VIX is calm. | `signals.py` |
| **Signal** | A reusable yes/no condition about the market on each day ("VIX is fading after a spike"), usually a threshold on an indicator. Uses only data up to that day. | `signals.py` |
| **Entry signal** | The signal that says "start buying". Signals combine with `all_of`, `any_of`, `not_`, `recently`. | `signals.py` |
| **Filter / tranche filter** | A signal that must also be true on the day each tranche is bought. If it is false that day, that tranche is skipped (e.g. "VIX is below 30"). It is a check on the buying, not on the decision to start. | `scale_in_strategy(tranche_filter=...)` |
| **Strategy** | A description, parameters and a `run` function. It turns data into trades and an equity curve. | `strategy.py`, `strategies/` |
| **Trigger** | The first day an entry signal turns on. | `strategy.py` |
| **Episode** | A stretch of time during which a signal is on. For the entry signal, "on" days closer together than `cooldown_days` belong to one episode. The engine buys at most once per episode and logs repeat triggers as skipped. In the crash strategy, an episode is a market fall of 25%+ from a high until a new high. | `strategy.py`, `strategies/stabilized_crash_low/episodes.py` |
| **Tranche** | One of the equal pieces a position is bought in (default: 8 weekly pieces). Buying in pieces is scaling in. | `strategy.py` |
| **Hold period** (`hold_years`) | How long after the first tranche the position is sold. | `strategy.py` |
| **Chaining** | Sale proceeds sit in cash and are reused at the next entry. `chained: false` gives each episode its own standalone account instead. | `strategy.py` |
| **Stabilization** | No new low for a number of days after a fall (the crash strategy waits 63 trading days). | `stabilized_crash_low/` |
| **Sensitivity grid** | A list of alternative parameter values (e.g. hold 1 year vs 2) a strategy is re-run over, to see whether its result depends on one lucky setting. Each strategy declares its own. | `sensitivity.py`, each strategy |
| **Benchmark** | A simple alternative to compare against, usually buy-and-hold from the same start date. | `benchmarks.py` |
| **Risk-free rate** | What cash earns: the T-bill yield (`^IRX`). Sharpe and Sortino are measured above it. | `data.py` (`risk_free` column) |
| **Sharpe / Sortino** | Return above the risk-free rate per unit of volatility (Sortino counts only downside volatility). | `metrics.py` |
| **Drawdown** | How far the account is below its previous peak. | `metrics.py` |
| **Fill lag** (`execution_lag`) | Orders decided at one close are filled this many days later. | `strategy.py` (`Context`) |
| **Slippage** (`cost_bps`) | Extra cost per trade, in basis points (0.01%). | `strategy.py` (`Context`) |
| **Lookahead** | Using information from after the day being decided. The tests check that nothing does. | `tests/` |

## 7. Roadmap

Planned, not built. Each step gets its own plan and its own commit.

1. **Indicators and signals (in progress):** the indicator layer is done. Next: new signals
   (`rsi_oversold`, `rsi_overbought`, `rsi_overbought_for`, `crash_active`).
2. **Rule-based strategies:** a strategy becomes a set of signals plus a rule that looks at today's
   signals and its current state (flat or holding, days held) and returns BUY, SELL or HOLD. Every
   strategy writes its own exit, so nothing is held by default. First use: hold at least a year, then
   sell once RSI has stayed at 70 or above for a number of days.
3. **Portfolio ledger:** a separate component that privately tracks cash, shares, cost basis and
   profit so far, and gives rules a read-only snapshot.
4. **Sizing:** buying and selling in portions, e.g. a larger position when more signals agree.
5. **Multi-asset portfolio:** one rule per asset and an allocation and rebalancing layer on top.
6. **Execution:** composable fill models (which day, which price in the day, slippage and spread) and
   open/high/low data.
7. **Fundamentals** (undervalued / overvalued), with point-in-time data to avoid lookahead.
8. **Machine-learning strategies:** a learned rule on numeric indicators, with walk-forward training.

## 8. Assumptions and caveats

- Taxes and slippage are excluded unless configured (`Context.cost_bps`).
- Only real prices are used, so history is short (TQQQ has only 2010 onward) and covers few crashes.
- Episodes and the benchmark anchors (first low, first signal) are identified with hindsight. The
  strategies themselves are causal.
- The number of independent episodes is small for the slow strategies, so results are illustrative, not
  predictive.
