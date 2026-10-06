"""Orchestrates everything from config.yaml:  python main.py [--instrument UPRO] [--refresh]"""
import argparse
from pathlib import Path

import pandas as pd
import yaml

from benchmarks import build_benchmarks, standalone_summary
from data import build_dataset
from metrics import summarize, window
from report import (ASSUMPTIONS, plot_drawdown, plot_equity, plot_vix, save_csv, write_report)
from sensitivity import run_grid
from strategy import run_strategy


def load_config(path: str) -> dict:
    return yaml.safe_load(open(path))


def run(cfg: dict, instrument: str | None = None, refresh: bool = False,
        sensitivity: bool | None = None) -> dict:
    inst = instrument or cfg["run"]["instrument"]
    cap, td = cfg["run"]["initial_capital"], cfg["synthetic"]["trading_days"]
    out = Path(cfg["output_dir"])
    data, info = build_dataset(cfg, inst, refresh)
    res = run_strategy(data, cfg["strategy"], cfg["episodes"], cap, td)
    start = res.anchors.get("first_signal")
    if start is None:
        raise SystemExit(f"{inst}: no stabilization signal was ever confirmed; nothing to backtest")
    holds = build_benchmarks(data["price"], res.anchors, cap)

    rows = {f"strategy [{inst}]": summarize(res.equity, res.weights, res.trades, data["rf"], start, cap, td)}
    for name, eq in holds.items():
        rows[f"{name} [{inst}]"] = summarize(eq, None, None, data["rf"], None, cap, td)
    curves = {f"strategy [{inst}]": window(res.equity, start, cap),
              **{k: v for k, v in holds.items() if k != "hold_first_low"} | {"hold_first_low": holds["hold_first_low"]}}
    for other in cfg["run"].get("comparison_instruments", []):
        d2, _ = build_dataset(cfg, other, refresh)
        r2 = run_strategy(d2, cfg["strategy"], cfg["episodes"], cap, td)
        rows[f"strategy [{other}]"] = summarize(r2.equity, r2.weights, r2.trades, d2["rf"], start, cap, td)
        rows[f"hold_first_signal [{other}]"] = summarize(
            build_benchmarks(d2["price"], {"first_signal": start}, cap)["hold_first_signal"],
            None, None, d2["rf"], None, cap, td)
        curves[f"strategy [{other}]"] = window(r2.equity, start, cap)
    summary = pd.DataFrame(rows).T.rename_axis("approach")

    sections, tables = {}, {"episodes": res.episodes, "trades": res.trades,
                            "events": res.events, "summary": summary}
    sections["Episodes (auto-detected)"] = res.episodes
    sections["Trades"] = res.trades
    sections["Summary"] = summary.reset_index()
    sections["Skipped signals / events"] = res.events
    if info["tracking"]:
        te = pd.DataFrame([info["tracking"]])
        tables["tracking_error"] = te
        sections[f"Synthetic vs real {inst} (overlap)"] = te
    if cfg["run"].get("standalone_comparison"):
        sa = run_strategy(data, {**cfg["strategy"], "chained": False}, cfg["episodes"], cap, td)
        ss = standalone_summary(sa.trades, cap)
        tables["standalone"] = ss
        sections["Chained vs standalone ($10k per episode)"] = ss
    if (cfg["sensitivity"]["enabled"] if sensitivity is None else sensitivity):
        grid = run_grid(data, cfg["strategy"], cfg["episodes"], cfg["sensitivity"]["grid"], cap, td)
        tables["sensitivity"] = grid
        sections["Sensitivity grid"] = grid
        sections["Sensitivity summary"] = (
            f"{len(grid)} cells; {(grid.final_value > cap).mean():.0%} ended above ${cap:,.0f}; "
            f"{grid.beats_hold.mean():.0%} beat buy-and-hold from the same first signal; "
            f"worst single trade across cells: {grid.worst_trade.min():.1%}.")

    for name, df in tables.items():
        save_csv(out, name, df)
    plot_equity(out, curves, res.episodes, f"{inst}: strategy vs buy-and-hold (from {start.date()})")
    plot_drawdown(out, {k: curves[k] for k in list(curves)[:2]}, res.episodes)
    plot_vix(out, data["vix"], res.trades, res.episodes, start=data.index[0])
    write_report(out, f"Backtest report: {inst}", sections)
    print_console(res, summary, info, sections)
    return {"result": res, "summary": summary, "tables": tables}


def print_console(res, summary, info, sections) -> None:
    pd.set_option("display.width", 220, "display.max_columns", 30, "display.float_format", "{:,.3f}".format)
    print("\n== Episodes (auto-detected) ==\n", res.episodes.to_string(index=False))
    print("\n== Trades ==\n", res.trades.to_string(index=False) if len(res.trades) else "(none)")
    print("\n== Summary ==\n", summary[["final_value", "cagr", "max_drawdown", "sharpe", "sortino",
                                       "time_in_market", "n_trades"]].to_string())
    for k in ("Chained vs standalone ($10k per episode)", "Sensitivity summary"):
        if k in sections:
            print(f"\n== {k} ==\n", sections[k] if isinstance(sections[k], str) else sections[k].to_string(index=False))
    sk = res.events[res.events.event.isin(["skipped", "tranche_skipped", "no_entry"])]
    print("\n== Skipped signals ==\n", sk.to_string(index=False) if len(sk) else "(none)")
    print("\nAssumptions:\n" + "\n".join(f" - {a}" for a in ASSUMPTIONS))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--instrument")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--no-sensitivity", action="store_true")
    a = ap.parse_args()
    run(load_config(a.config), a.instrument, a.refresh, False if a.no_sensitivity else None)
