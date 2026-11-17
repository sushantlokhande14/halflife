"""Tables and figures for the study, written to results/.

Charts follow one small system: a light surface, recessive grid, ink-colored text, thin
2px lines, and categorical colors assigned in a fixed order (blue, orange, aqua) and
never cycled. Every multi-series chart has a legend and direct labels, so no series is
identified by color alone, and every figure has a CSV of the numbers behind it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e4e2dd"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
MUTED = "#a3a29c"


def style(ax, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=12, fontweight="semibold")
    ax.set_xlabel(xlabel, color=INK_SECONDARY, fontsize=10)
    ax.set_ylabel(ylabel, color=INK_SECONDARY, fontsize=10)
    ax.tick_params(colors=INK_SECONDARY, labelsize=9, length=0)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)


MINUTE_TICKS = [2, 5, 10, 30, 60, 120, 240, 480, 960]


def minutes_axis(ax) -> None:
    ax.set_xscale("log")
    ax.xaxis.set_major_locator(FixedLocator(MINUTE_TICKS))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 60:g} h" if v >= 60 else f"{v:g} min"))
    ax.xaxis.set_minor_locator(FixedLocator([]))


def curves_figure(curves: list[dict], path) -> None:
    """curves: [{label, taus, mean, low, high, n}] in series order."""
    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=150)
    for index, curve in enumerate(curves):
        color = SERIES[index]
        keep = curve["taus"] >= 2
        x = curve["taus"][keep]
        ax.fill_between(x, curve["low"][keep], curve["high"][keep], color=color, alpha=0.14, linewidth=0)
        ax.plot(x, curve["mean"][keep], color=color, linewidth=2, label=f"{curve['label']} (n={curve['n']})")
        # A direct label where the curve has room, so it is not identified by color alone.
        at = curve.get("label_at", x[len(x) // 2])
        index = int(np.argmin(np.abs(x - at)))
        ax.annotate(
            curve["label"],
            (x[index], curve["mean"][keep][index]),
            xytext=curve.get("label_offset", (0, 10)),
            textcoords="offset points",
            color=INK_SECONDARY,
            fontsize=9,
            ha="center",
        )
    ax.axhline(0.5, color=MUTED, linewidth=1, linestyle=(0, (3, 3)))
    ax.axhline(1.0, color=MUTED, linewidth=1)
    ax.text(2.1, 0.52, "half the move", color=INK_SECONDARY, fontsize=8.5)
    minutes_axis(ax)
    ax.set_xlim(2, max(curve["taus"][-1] for curve in curves) * 1.6)
    ax.set_ylim(-0.1, 1.25)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
    style(
        ax,
        "Share of the eventual move priced in, by trading time after the filing",
        "Trading minutes after the last price before the filing (log scale; nights and weekends take no time)",
        "Share of the move by the settling close",
    )
    ax.legend(frameon=False, fontsize=9, labelcolor=INK_SECONDARY, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def latency_figure(table: pd.DataFrame, path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=150)
    x = table["latency_minutes"].to_numpy(dtype=float)
    ax.fill_between(x, table["remaining_low"], table["remaining_high"], color=SERIES[0], alpha=0.14, linewidth=0)
    ax.plot(x, table["remaining_median"], color=SERIES[0], linewidth=2, marker="o", markersize=4)
    for minutes, value in zip(x, table["remaining_median"]):
        if minutes in (2, 10, 60, 240):
            ax.annotate(f"{value:.0%}", (minutes, value), xytext=(0, 8), textcoords="offset points", ha="center", color=INK, fontsize=9)
    minutes_axis(ax)
    ax.set_xlim(1.6, 320)
    ax.set_ylim(0, 1.1)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
    style(
        ax,
        "What is left of an informative move when you get there",
        "Reaction latency: trading minutes after the last price before the filing (log scale)",
        "Median share of the move still ahead",
    )
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def wilson(successes: int, total: int, z: float = 1.645) -> tuple[float, float]:
    if total == 0:
        return float("nan"), float("nan")
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * np.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return centre - half, centre + half


def informative_figure(table: pd.DataFrame, path) -> None:
    """Share of events whose move cleared two daily standard deviations, by category,
    with the random-moment placebo as the reference line."""
    table = table.sort_values("informative_share")
    placebo = table[table["category"] == "placebo"]
    rows = table[table["category"] != "placebo"]
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=150)
    y = np.arange(len(rows))
    lows, highs = zip(*(wilson(int(r.informative), int(r.events)) for r in rows.itertuples()))
    ax.barh(y, rows["informative_share"], height=0.62, color=SERIES[0])
    ax.errorbar(rows["informative_share"], y, xerr=[rows["informative_share"] - np.array(lows), np.array(highs) - rows["informative_share"]], fmt="none", ecolor=INK_SECONDARY, elinewidth=1, capsize=0)
    for position, row in zip(y, rows.itertuples()):
        ax.text(max(highs[position], row.informative_share) + 0.012, position, f"{row.informative_share:.0%}  ({int(row.informative)} of {int(row.events)})", va="center", fontsize=8.5, color=INK_SECONDARY)
    if len(placebo):
        share = float(placebo["informative_share"].iloc[0])
        ax.axvline(share, color=SERIES[1], linewidth=2, linestyle=(0, (4, 3)))
        ax.text(share + 0.006, len(rows) - 0.4, f"random moments, no filing: {share:.0%}", color=INK_SECONDARY, fontsize=8.5)
    ax.set_yticks(y, rows["category"])
    ax.set_xlim(0, min(1.0, max(highs) + 0.22))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
    style(ax, "Share of filings that moved the stock at least two daily standard deviations", "Share of events (90% interval)", "")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def half_life_figure(frame: pd.DataFrame, path) -> None:
    """Time to half the move for informative earnings events, one dot per event, by
    session of the filing."""
    order = [("pre", "Before the open"), ("regular", "During the session"), ("post", "After the close")]
    fig, ax = plt.subplots(figsize=(9, 3.8), dpi=150)
    rng = np.random.default_rng(3)
    for row, (name, label) in enumerate(order):
        values = frame.loc[frame["session"] == name, "t50"].dropna().to_numpy()
        if len(values) == 0:
            continue
        jitter = rng.uniform(-0.18, 0.18, len(values))
        ax.scatter(values, np.full(len(values), row) + jitter, s=14, color=SERIES[0], alpha=0.55, linewidths=0)
        median = float(np.median(values))
        ax.plot([median, median], [row - 0.32, row + 0.32], color=INK, linewidth=2)
        ax.text(median, row + 0.38, f"median {median:g} min, n={len(values)}", ha="center", fontsize=8.5, color=INK)
    ax.set_yticks(range(len(order)), [label for _, label in order])
    minutes_axis(ax)
    ax.set_xlim(1.5, 1200)
    ax.set_ylim(-0.6, len(order) - 0.2)
    style(ax, "Time to half of the move, informative earnings releases", "Trading minutes after the last price before the filing (log scale)", "")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
