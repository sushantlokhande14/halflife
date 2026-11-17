"""How much to believe what made money at the open.

Two things did, out of sample: the rule "go with the opening move", and gradient boosting.
A mean return with a t-statistic over a few hundred trades can still be one lucky week, a
handful of huge winners, many trades on the same day that are really one bet, or a model
setting that happened to fit. Each check below removes one of those ways of fooling yourself.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from .model import clustered_t, decision_days, t_stat, trade_returns, walk_forward


def bootstrap_mean(values: np.ndarray, rng: np.random.Generator, draws: int = 5000) -> tuple[float, float]:
    boot = rng.choice(values, size=(draws, len(values)), replace=True).mean(axis=1)
    return float(np.quantile(boot, 0.05)), float(np.quantile(boot, 0.95))


def summarize(frame: pd.DataFrame, label: str, rng: np.random.Generator, cost_bps: float = 10.0) -> dict:
    gross = frame["remaining"].to_numpy() * 1e4  # going with the move: the remaining move is the return
    net = gross - cost_bps
    days = decision_days(frame)
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
        "t_events": t_stat(net),
        "t_days": clustered_t(net, days),
    }


def with_the_move(data: pd.DataFrame, seed: int = 5) -> pd.DataFrame:
    """The rule has nothing fitted, so it can be tested on every event, not only the
    out-of-sample weeks."""
    rng = np.random.default_rng(seed)
    data = data.copy()
    rows = [summarize(data, "all events", rng)]
    weeks = data["decided_at"].dt.tz_convert("America/New_York").dt.tz_localize(None).dt.to_period("W-SUN")
    for week in sorted(weeks.unique()):
        rows.append(summarize(data[weeks == week], f"week of {week.start_time:%b %d}", rng))
    busiest = weeks.isin(weeks.value_counts().nlargest(2).index)
    rows.append(summarize(data[~busiest.to_numpy()], "outside the two busiest weeks", rng))
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


def boosting_breakdown(predictions: pd.DataFrame, name: str = "gradient boosting") -> pd.DataFrame:
    """Where a model's out-of-sample money came from: each week, and each stance."""
    trades = trade_returns(predictions, predictions[name].to_numpy())
    side, net = trades["side"].to_numpy(), trades["net_bps"].to_numpy()
    weeks = predictions["decided_at"].dt.tz_convert("America/New_York").dt.tz_localize(None).dt.to_period("W-SUN")
    rows = []

    def add(label: str, mask: np.ndarray) -> None:
        taken = mask & (side != 0)
        rows.append(
            {
                "slice": label,
                "trades": int(taken.sum()),
                "with_the_move_share": float(np.mean(side[taken] == 1)) if taken.any() else float("nan"),
                "mean_net_bps": float(net[taken].mean()) if taken.any() else float("nan"),
                "t_net": t_stat(net[taken]),
            }
        )

    for week in sorted(weeks.unique()):
        add(f"week of {week.start_time:%b %d}", (weeks == week).to_numpy())
    add("with the move", side == 1)
    add("against the move", side == -1)
    return pd.DataFrame(rows)


USED = (2, 0.05, 150)  # the setting in model.candidates()


def boosting_neighbors(data: pd.DataFrame) -> pd.DataFrame:
    """Gradient boosting, walk-forward, at the settings around the one used. A real edge
    survives a nudge to tree depth, learning rate or rounds; a lucky fit moves."""
    rows = []
    for depth in (2, 3):
        for rate in (0.03, 0.05, 0.1):
            for rounds in (100, 150, 200):

                def factory(depth=depth, rate=rate, rounds=rounds):
                    return HistGradientBoostingClassifier(
                        max_depth=depth, max_iter=rounds, learning_rate=rate, l2_regularization=1.0, min_samples_leaf=20, random_state=0
                    )

                predictions = walk_forward(data, models={"gradient boosting": factory}).predictions
                probability = predictions["gradient boosting"].to_numpy()
                trades = trade_returns(predictions, probability)
                taken = trades["side"].to_numpy() != 0
                net = trades["net_bps"].to_numpy()[taken]
                rows.append(
                    {
                        "max_depth": depth,
                        "learning_rate": rate,
                        "rounds": rounds,
                        "used": (depth, rate, rounds) == USED,
                        "auc": roc_auc_score(predictions["continues"], probability),
                        "decisions": int(taken.sum()),
                        "mean_net_bps": float(net.mean()) if len(net) else float("nan"),
                        "t_net": t_stat(net),
                        "t_net_days": clustered_t(net, decision_days(predictions)[taken]),
                    }
                )
    return pd.DataFrame(rows)
