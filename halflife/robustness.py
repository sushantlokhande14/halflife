"""How much to believe the one rule that made money: go with the opening move.

A mean return with a t-statistic over a few hundred trades can still be one lucky week,
a handful of huge winners, or many trades on the same day that are really one bet.
Each check below removes one of those ways of fooling yourself.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def clustered_t(values: np.ndarray, clusters: np.ndarray) -> float:
    """t-statistic of the mean with one observation per cluster (the cluster mean): events
    on the same day count once."""
    frame = pd.DataFrame({"v": values, "c": clusters})
    means = frame.groupby("c")["v"].mean().to_numpy()
    if len(means) < 3:
        return float("nan")
    return float(means.mean() / (means.std(ddof=1) / np.sqrt(len(means))))


def bootstrap_mean(values: np.ndarray, rng: np.random.Generator, draws: int = 5000) -> tuple[float, float]:
    boot = rng.choice(values, size=(draws, len(values)), replace=True).mean(axis=1)
    return float(np.quantile(boot, 0.05)), float(np.quantile(boot, 0.95))


def summarize(frame: pd.DataFrame, label: str, rng: np.random.Generator, cost_bps: float = 10.0) -> dict:
    gross = frame["remaining"].to_numpy() * 1e4  # going with the move: the remaining move is the return
    net = gross - cost_bps
    days = frame["decided_at"].dt.tz_convert("America/New_York").dt.date.to_numpy()
    low, high = bootstrap_mean(net, rng) if len(net) > 2 else (float("nan"), float("nan"))
    trimmed = np.sort(net)[int(0.05 * len(net)) : len(net) - int(0.05 * len(net))]
    return {
        "slice": label,
        "events": len(frame),
        "days": len(set(days)),
        "hit_rate": float(np.mean(gross > 0)),
        "mean_net_bps": float(net.mean()),
        "net_low_bps": low,
        "net_high_bps": high,
        "median_net_bps": float(np.median(net)),
        "trimmed_mean_net_bps": float(trimmed.mean()) if len(trimmed) else float("nan"),
        "t_events": float(net.mean() / (net.std(ddof=1) / np.sqrt(len(net)))) if len(net) > 2 else float("nan"),
        "t_days": clustered_t(net, days),
    }


def with_the_move(data: pd.DataFrame, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data = data.copy()
    rows = [summarize(data, "all events", rng)]
    weeks = data["decided_at"].dt.tz_convert("America/New_York").dt.tz_localize(None).dt.to_period("W-SUN")
    for week in sorted(weeks.unique()):
        rows.append(summarize(data[weeks == week], f"week of {week.start_time:%b %d}", rng))
    for session, label in (("post", "filed after the close"), ("pre", "filed before the open"), ("closed", "filed overnight or on a weekend")):
        part = data[data["session"] == session]
        if len(part) >= 10:
            rows.append(summarize(part, label, rng))
    rows.append(summarize(data[data["category"] == "earnings"], "earnings", rng))
    rows.append(summarize(data[data["category"] != "earnings"], "other filings", rng))
    big = data["abs_z_d"] >= 2
    rows.append(summarize(data[big], "opening move 2+ daily s.d.", rng))
    rows.append(summarize(data[~big], "opening move 0.5-2 daily s.d.", rng))
    for cost in (20.0, 30.0):
        rows.append(summarize(data, f"all events, {cost:.0f} bps cost", rng, cost_bps=cost))
    return pd.DataFrame(rows)
