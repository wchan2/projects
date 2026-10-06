# Backtest

A modular Python backtester. It loads (and caches) price data for any ticker, runs every strategy in
`strategies/` on top of it, and reports trades, performance, buy-and-hold benchmarks and parameter
sensitivity.

Any ticker works, so the same code runs on TQQQ, FNGU, QQQ, SSO, UPRO, or a plain stock.

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
uv run python main.py                        # every strategy on TQQQ (~1 min)
uv run python main.py --instrument UPRO      # any ticker
uv run python main.py --no-sensitivity       # skip the parameter grids (fast)
uv run python main.py --refresh              # force a re-download of price data
uv run python main.py --capital 50000        # starting capital (default 10,000)
```

The first run downloads prices from Yahoo Finance and caches them as parquet files in `data_cache/`.
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
| `tracking_error.csv` | Synthetic 3x vs real fund over their overlap |
| `*.png` | Log equity curves, drawdown, VIX with entry/exit markers (episodes shaded) |

## 3. Strategies

Each strategy is a folder (or module) under `strategies/` that exposes a `STRATEGY`. Its parameters
and sensitivity grid live in the same place, and `main.py` backtests every strategy it finds.

| Strategy | Idea |
|---|---|
| `stabilized_crash_low/` | After the index falls 25%+ from its high and makes no new low for 63 trading days, scale in over 8 weeks, hold 2 years, sell. Crash episodes are auto-detected, never hardcoded. |
| `vix_spike_fade/` | After VIX closes above 30, peaks, falls 25% from the peak and keeps drifting down (10+ days after the peak), scale in, hold 1 year, sell. |
| `rsi_oversold_bounce/` | After RSI(14) drops below 30, makes no new low for 5 days and bounces 5 points, scale in, hold 1 year, sell. |
| `buy_and_hold.py` | Buy at `start`, sell at `end` (default: whole history). Also the benchmark: every other strategy is compared with $10k bought at the same moment it entered. |

All parameters are in each strategy's `PARAMS`, so tuning means editing that dict (or passing different
params to `STRATEGY.run`). The default values above are starting guesses, not optimized.

## 4. How it works

```
main.py ──► data.py ──► (price, signal, vix, rf) ──► strategies/* ──► StrategyResult ──► report.py
              │                                          │                  │
        cached parquet                      strategy.py (contract,     metrics.py · benchmarks.py
                                            scale-in engine) ·         sensitivity.py
                                            signals.py · portfolio.py
```

### Data (`data.py`)
- Downloads adjusted closes for the instrument, its signal index, `^VIX` and a risk-free rate
  (`^IRX`), and caches each ticker to parquet. Settings are the `DataSettings` dataclass.
- Before a leveraged fund existed, history is **synthetic**:
  `L x daily index return - (L-1) x rf / 252 - expense ratio / 252`. It is spliced onto the real fund
  at its launch, and `tracking_error()` reports how well the synthetic series matches the overlap.
- `build_dataset()` returns one standard frame (`price`, `signal`, `vix`, `rf`) that every strategy
  consumes. Leveraged instruments are recipes in the `INSTRUMENTS` dict.

### Strategy interface (`strategy.py`)
- A `Strategy` is a description, default `params`, a `run(data, params, ctx)` function and its own
  `sensitivity_grid`. Data goes in, a `StrategyResult` (equity, weights, trades, events, episodes)
  comes out, and `metrics.performance(result, data)` extracts the performance.
- `Context` holds backtest-wide settings: capital, execution lag, cash earning the risk-free rate,
  slippage.
- The "wait for a signal, scale in, hold, sell" strategies share one engine, `scale_in()`: equal weekly
  tranches (each checked against optional filters), a timed exit, cash earning rf, proceeds redeployed
  at the next episode (**chaining**), and triggers during an open position logged as `skipped`. A
  strategy only has to produce its trigger.
- **No lookahead:** decisions use only data up to that date, and orders fill `execution_lag` days later.

### Signals
- `signals.py` holds the shared, causal building blocks: pluggable filters, episode windows, extreme
  tracking.
- Anything specific to one strategy lives inside that strategy's folder (for example the crash
  episode detector in `stabilized_crash_low/episodes.py`, or RSI in `rsi_oversold_bounce/signals.py`),
  and is not used by the rest of the code.

### Comparison and analysis
- `benchmarks.py`: runs the `buy_and_hold` strategy from each date a strategy reports (first signal,
  first entry, ...), so you see what $10k put in at the same time would have done.
- `metrics.py`: CAGR, max drawdown, Sharpe, Sortino, time in market.
- `sensitivity.py`: runs a strategy over its own grid (dotted keys reach nested params).
- `report.py`: writes the tables and charts.

## 5. Extending it

| To add... | Do this |
|---|---|
| A strategy | Add a module or folder in `strategies/` exposing `STRATEGY = Strategy(...)`; it is picked up automatically |
| An instrument | Add a line to `INSTRUMENTS` in `data.py` (any other ticker works as-is) |
| A filter | `@register("filter", "name")` on a function in `signals.py` |
| A data source | `@register("fetcher", "name")` on a function in `data.py` |

## 6. Assumptions and caveats

- Taxes and slippage are excluded unless configured (`Context.cost_bps`).
- Pre-launch leveraged data is synthetic. The index excludes dividends, so tracking is approximate.
- Episodes and the benchmark anchors (first low, first signal) are identified with hindsight. The
  strategies themselves are causal.
- The number of independent episodes is small for the slow strategies, so results are illustrative, not
  predictive.
