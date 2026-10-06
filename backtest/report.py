"""Tables (CSV), charts (PNG) and the markdown report."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from metrics import drawdown_series, window

ASSUMPTIONS = [
    "Taxes and slippage are excluded unless configured (`strategy.cost_bps`).",
    "Pre-launch history of leveraged funds is synthetic (3 x daily index return - financing "
    "- expense ratio); see the tracking-error table for how well it matches the real fund.",
    "The sample of independent crashes is small, so results are illustrative, not predictive.",
    "Episodes and the first-low / first-signal buy-and-hold anchors are detected with hindsight; "
    "the strategy itself only uses data available on each date.",
    "Orders decided at a close fill at the close `execution_lag` trading days later.",
]


def save_csv(outdir, name: str, df: pd.DataFrame) -> Path:
    p = Path(outdir) / f"{name}.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=not isinstance(df.index, pd.RangeIndex))
    return p


def _shade(ax, episodes: pd.DataFrame, end) -> None:
    for _, e in episodes.iterrows():
        ax.axvspan(e["start_date"], e["recovery_date"] if pd.notna(e["recovery_date"]) else end,
                   color="tab:red", alpha=0.10, lw=0)


def plot_equity(outdir, curves: dict, episodes: pd.DataFrame, title: str) -> Path:
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for name, s in curves.items():
        ax.plot(s.index, s.values, label=name, lw=1.4)
    _shade(ax, episodes, max(s.index[-1] for s in curves.values()))
    ax.set_yscale("log"); ax.set_title(title); ax.set_ylabel("value of $10k (log)")
    ax.legend(fontsize=8); ax.grid(alpha=.3)
    return _save(fig, outdir, "equity_curves.png")


def plot_drawdown(outdir, curves: dict, episodes: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(11, 4))
    for name, s in curves.items():
        d = drawdown_series(s)
        ax.plot(d.index, d.values * 100, label=name, lw=1.1)
    _shade(ax, episodes, max(s.index[-1] for s in curves.values()))
    ax.set_ylabel("drawdown %"); ax.set_title("Drawdown"); ax.legend(fontsize=8); ax.grid(alpha=.3)
    return _save(fig, outdir, "drawdown.png")


def plot_vix(outdir, vix: pd.Series, trades: pd.DataFrame, episodes: pd.DataFrame, start=None) -> Path:
    v = vix.dropna().loc[start:] if start is not None else vix.dropna()
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(v.index, v.values, color="0.3", lw=.8)
    _shade(ax, episodes, v.index[-1])
    if len(trades):
        ent, ex = trades["entry_start"], trades["exit"]
        ax.scatter(ent, v.reindex(ent, method="nearest"), marker="^", c="tab:green", s=60, label="entry", zorder=3)
        ax.scatter(ex, v.reindex(ex, method="nearest"), marker="v", c="tab:blue", s=60, label="exit", zorder=3)
    ax.set_title("VIX with entries / exits (red = crash episodes)"); ax.legend(); ax.grid(alpha=.3)
    return _save(fig, outdir, "vix_entries_exits.png")


def _save(fig, outdir, name) -> Path:
    p = Path(outdir) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig)
    return p


def md_table(df: pd.DataFrame, floatfmt: str = "{:,.3f}") -> str:
    if df.empty:
        return "_(none)_"
    d = df.copy()
    for c in d.columns:
        d[c] = d[c].map(lambda x: floatfmt.format(x) if isinstance(x, float) else
                        (x.strftime("%Y-%m-%d") if isinstance(x, pd.Timestamp) and pd.notna(x) else
                         ("" if pd.isna(x) else str(x))))
    lines = ["| " + " | ".join(map(str, d.columns)) + " |", "|" + "---|" * len(d.columns)]
    lines += ["| " + " | ".join(r) + " |" for r in d.astype(str).values.tolist()]
    return "\n".join(lines)


def write_report(outdir, title: str, sections: dict[str, pd.DataFrame | str]) -> Path:
    parts = [f"# {title}\n"]
    for h, body in sections.items():
        parts.append(f"## {h}\n\n" + (md_table(body) if isinstance(body, pd.DataFrame) else body) + "\n")
    parts.append("## Assumptions\n\n" + "\n".join(f"- {a}" for a in ASSUMPTIONS) + "\n")
    p = Path(outdir) / "report.md"
    p.write_text("\n".join(parts))
    return p
