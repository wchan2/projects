"""Backtest every strategy in strategies/ on one instrument.

    uv run python main.py                    # TQQQ
    uv run python main.py --instrument UPRO  # any ticker
    uv run python main.py --start 2018-01-01 --end 2023-12-31
    uv run python main.py --verbose          # full tables for every strategy

Data settings live in data.py (DataSettings / SIGNAL_INDEX), strategy parameters and sensitivity
grids live with each strategy in strategies/.
"""

import argparse
from dataclasses import replace
from pathlib import Path

import pandas as pd

from benchmarks import build_benchmarks, standalone_summary
from data import DEFAULT_SETTINGS, DataSettings, build_dataset
from metrics import performance, window
from report import (
    ASSUMPTIONS,
    plot_drawdown,
    plot_equity,
    plot_vix,
    save_csv,
    write_report,
)
from sensitivity import run_grid
from strategies import discover
from strategy import Context, Strategy

EMPTY_EPISODES = pd.DataFrame(columns=["start_date", "recovery_date"])


def backtest_strategy(
    name: str,
    strategy: Strategy,
    data: pd.DataFrame,
    info: dict,
    ctx: Context,
    instrument: str,
    out_dir: Path,
    run_sensitivity: bool,
    verbose: bool,
) -> pd.DataFrame | None:
    """Run one strategy, write its tables / charts / report, return its summary table."""
    capital = ctx.initial_capital
    res = strategy.run(data, strategy.params, ctx)
    start = res.eval_start
    if start is None:
        print(f"\n[{name}] no signal was ever confirmed on {instrument}; skipped")
        return None

    holds = build_benchmarks(data, res.anchors, ctx)  # $10k bought when the strategy entered
    rows = {f"{name} [{instrument}]": performance(res, data, capital, ctx.trading_days)}
    for hold_name, held in holds.items():
        rows[f"{hold_name} [{instrument}]"] = performance(held, data, capital, ctx.trading_days)
    summary = pd.DataFrame(rows).T.rename_axis("approach")
    episodes = res.episodes if res.episodes is not None else EMPTY_EPISODES

    tables = {
        "episodes": episodes,
        "trades": res.trades,
        "events": res.events,
        "summary": summary,
    }
    sections = {
        "Strategy": strategy.description,
        "Data window": data_window(instrument, info, len(data)),
        "Episodes (auto-detected)": episodes,
        "Trades": res.trades,
        "Summary": summary.reset_index(),
        "Skipped signals / events": res.events,
    }
    if "chained" in strategy.params:
        standalone = strategy.run(data, {**strategy.params, "chained": False}, ctx)
        table = standalone_summary(standalone.trades, capital)
        tables["standalone"] = table
        sections["Chained vs standalone ($10k per episode)"] = table
    if run_sensitivity and strategy.sensitivity_grid:
        grid = run_grid(strategy, data, ctx)
        tables["sensitivity"] = grid
        sections["Sensitivity grid"] = grid
        sections["Sensitivity summary"] = (
            f"{len(grid)} cells; {(grid.final_value > capital).mean():.0%} ended above "
            f"${capital:,.0f}; {grid.beats_hold.mean():.0%} beat buy-and-hold from the same "
            f"start; worst single trade across cells: {grid.worst_trade.min():.1%}."
        )

    for table_name, df in tables.items():
        save_csv(out_dir, table_name, df)
    curves = {f"{name} [{instrument}]": window(res.equity, start, capital)}
    for hold_name, held in holds.items():
        curves[hold_name] = window(held.equity, held.eval_start, capital)
    plot_equity(out_dir, curves, episodes, f"{instrument}: {name} vs buy-and-hold")
    plot_drawdown(out_dir, {k: curves[k] for k in list(curves)[:2]}, episodes)
    plot_vix(out_dir, data["vix"], res.trades, episodes, data.index[0])
    write_report(out_dir, f"Backtest report: {name} on {instrument}", sections)
    if verbose:
        print_console(name, strategy, episodes, res.trades, res.events, summary, sections)
    else:
        print(f"{name}: {len(res.trades)} trades -> {out_dir}/report.md")
        if "Sensitivity summary" in sections:
            print(f"  sensitivity: {sections['Sensitivity summary']}")
    return summary


def data_window(instrument: str, info: dict, n_days: int) -> str:
    return (
        f"{instrument}: {info['first_date']:%Y-%m-%d} to {info['last_date']:%Y-%m-%d} "
        f"({n_days:,} trading days, signals from {info['signal']})"
    )


def print_console(
    name: str,
    strategy: Strategy,
    episodes: pd.DataFrame,
    trades: pd.DataFrame,
    events: pd.DataFrame,
    summary: pd.DataFrame,
    sections: dict,
) -> None:
    pd.set_option("display.width", 220, "display.max_columns", 30)
    pd.set_option("display.float_format", "{:,.3f}".format)
    print(f"\n{'=' * 100}\n{name}: {strategy.description}\n{'=' * 100}")
    print("\n== Episodes ==\n", episodes.to_string(index=False) if len(episodes) else "(none)")
    print("\n== Trades ==\n", trades.to_string(index=False) if len(trades) else "(none)")
    columns = [
        "final_value",
        "cagr",
        "max_drawdown",
        "sharpe",
        "sortino",
        "time_in_market",
        "n_trades",
    ]
    print("\n== Summary ==\n", summary[columns].to_string())
    for key in ("Chained vs standalone ($10k per episode)", "Sensitivity summary"):
        if key in sections:
            body = sections[key]
            print(
                f"\n== {key} ==\n", body if isinstance(body, str) else body.to_string(index=False)
            )
    skipped = events[events.event.isin(["skipped", "tranche_skipped", "no_entry"])]
    print("\n== Skipped signals ==\n", skipped.to_string(index=False) if len(skipped) else "(none)")


def main(
    instrument: str = "TQQQ",
    settings: DataSettings = DEFAULT_SETTINGS,
    capital: float = 10_000,
    refresh: bool = False,
    run_sensitivity: bool = True,
    output_dir: str = "outputs",
    verbose: bool = False,
) -> pd.DataFrame:
    ctx = Context(initial_capital=capital)
    data, info = build_dataset(instrument, settings, refresh=refresh)
    print(data_window(instrument, info, len(data)) + "\n")
    summaries = {}
    for name, strategy in discover().items():
        summary = backtest_strategy(
            name,
            strategy,
            data,
            info,
            ctx,
            instrument,
            Path(output_dir) / name,
            run_sensitivity,
            verbose,
        )
        if summary is not None:
            summaries[name] = summary.iloc[0]  # the strategy's own row (holds are per-strategy)

    comparison = pd.DataFrame(summaries).T.rename_axis("strategy")
    if len(comparison):
        save_csv(output_dir, "comparison", comparison)
        print(f"\n{'=' * 100}\nAll strategies on {instrument}\n{'=' * 100}")
        columns = ["start", "final_value", "cagr", "max_drawdown", "sharpe", "n_trades"]
        table = comparison[columns].copy()
        table["start"] = pd.to_datetime(table["start"]).dt.date
        print(table.to_string(float_format=lambda x: f"{x:,.3f}"))
    if verbose:
        print("\nAssumptions:\n" + "\n".join(f" - {a}" for a in ASSUMPTIONS))
    else:
        print("\nIllustrative only: small sample. Run with --verbose for full tables;")
        print("assumptions are listed in each report.md.")
    return comparison


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--instrument", default="TQQQ", help="any ticker (default: TQQQ)")
    parser.add_argument(
        "--start", help="backtest start date, YYYY-MM-DD (default: 5 years before the end)"
    )
    parser.add_argument("--end", help="backtest end date, YYYY-MM-DD (default: latest data)")
    parser.add_argument(
        "--full-history",
        action="store_true",
        help="use all history from the instrument's first day (default: the last 5 years)",
    )
    parser.add_argument("--capital", type=float, default=10_000)
    parser.add_argument("--refresh", action="store_true", help="re-download price data")
    parser.add_argument("--no-sensitivity", action="store_true", help="skip the parameter grids")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--verbose", action="store_true", help="print the full tables per strategy")
    args = parser.parse_args()
    settings = replace(
        DEFAULT_SETTINGS,
        start=args.start,
        end_date=args.end,
        lookback_years=None if args.full_history else DEFAULT_SETTINGS.lookback_years,
    )
    main(
        args.instrument,
        settings,
        args.capital,
        args.refresh,
        not args.no_sensitivity,
        args.output_dir,
        args.verbose,
    )
