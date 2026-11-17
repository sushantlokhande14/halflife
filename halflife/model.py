"""Will the rest of the move continue or reverse?

For each filing that has visibly moved its stock ten trading minutes in, the model gives
a probability that the move continues to the settling close. That probability is the
confidence; a fixed rule turns it into a stance:

    p >= 0.55   with the move
    p <= 0.45   against it
    otherwise   stand aside

Evaluation is walk-forward. The events are split into calendar weeks; each week is
predicted by a model trained only on events whose outcome was already known before that
week began. Every stance pays a round-trip cost: 10 bps in the regular session, 30 bps
in pre- and post-market trading, where spreads are wider.

This is a research measurement. It does not place orders and it is not advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from .clock import session as session_of
from .config import ET, UTC
from .diffusion import Path
from .features import DECISION_MINUTES, FEATURE_NAMES, MIN_REACTION_Z, features, known_at, outcome

WITH, AGAINST = 0.55, 0.45
COST_REGULAR_BPS = 10.0
COST_EXTENDED_BPS = 30.0


def settle_time(reaction_day) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(pd.Timestamp(reaction_day).date(), time(16, 0), ET)).tz_convert(UTC)


# Two decision points. "ten_minutes": ten trading minutes after the last price before
# the filing. "at_open": for filings released before their reaction day's regular
# session, right after its first 2-minute bar, which is where the study finds most
# earnings news is priced.
MODES = ("ten_minutes", "at_open")


def open_index(clock, path: Path, event) -> int | None:
    opening = clock.regular_open(pd.Timestamp(event.reaction_day).date())
    if pd.Timestamp(event.accepted_at) >= opening:
        return None
    return clock.position(opening + pd.Timedelta(minutes=clock.step)) - path.ref_index


def dataset(events: pd.DataFrame, paths: dict[str, Path], clock, mode: str = "ten_minutes") -> pd.DataFrame:
    rows = []
    for event in events.itertuples(index=False):
        path = paths.get(event.event_id)
        if path is None or not np.isfinite(event.sigma):
            continue
        index = None
        if mode == "at_open":
            index = open_index(clock, path, event)
            if index is None:
                continue
        view = known_at(path, index=index)
        if view is None:
            continue
        values = features(view, event.sigma, event.dollar_volume, event.session, event.category, event.scheduled)
        if not np.isfinite(values["abs_z_d"]) or values["abs_z_d"] < MIN_REACTION_Z:
            continue
        decided_at = clock.grid[path.ref_index + len(view.tau) - 1]
        rows.append(
            {
                "event_id": event.event_id,
                "ticker": event.ticker,
                "category": event.category,
                "session": event.session,
                "accepted_at": event.accepted_at,
                "decided_at": decided_at,
                "decision_session": session_of(decided_at),
                "known_at": settle_time(event.reaction_day),
                **values,
                **outcome(path, index=len(view.tau) - 1),
            }
        )
    frame = pd.DataFrame(rows).sort_values("accepted_at").reset_index(drop=True)
    frame["cost_bps"] = np.where(frame["decision_session"] == "regular", COST_REGULAR_BPS, COST_EXTENDED_BPS)
    return frame


def candidates() -> dict:
    """The models compared. Small, regularized, and few: the sample is hundreds, not millions."""
    return {
        "base rate": None,
        "reaction size only": lambda: make_pipeline(
            SimpleImputer(), StandardScaler(), LogisticRegression(C=0.5, max_iter=1000)
        ),
        "logistic, all features": lambda: make_pipeline(
            SimpleImputer(), StandardScaler(), LogisticRegression(C=0.3, max_iter=2000)
        ),
        "gradient boosting": lambda: HistGradientBoostingClassifier(
            max_depth=2, max_iter=150, learning_rate=0.05, l2_regularization=1.0, min_samples_leaf=20, random_state=0
        ),
    }


def columns_for(name: str) -> list[str]:
    return ["abs_z_d"] if name == "reaction size only" else FEATURE_NAMES


@dataclass
class WalkForward:
    predictions: pd.DataFrame
    folds: list[dict] = field(default_factory=list)


def walk_forward(data: pd.DataFrame, min_train: int = 80, models: dict | None = None) -> WalkForward:
    models = candidates() if models is None else models
    # Calendar weeks in New York time. (Periods carry no timezone, hence the explicit localize below.)
    weeks = data["accepted_at"].dt.tz_convert(ET).dt.tz_localize(None).dt.to_period("W-SUN")
    results = []
    folds = []
    for week in sorted(weeks.unique()):
        start = pd.Timestamp(week.start_time).tz_localize(ET).tz_convert(UTC)
        test = data[weeks == week]
        train = data[data["known_at"] < start]
        if len(train) < min_train or len(test) == 0 or train["continues"].nunique() < 2:
            continue
        fold = {"week": str(week), "start": start, "train": len(train), "test": len(test)}
        frame = test[["event_id", "accepted_at", "decided_at", "decision_session", "category", "session", "continues", "remaining", "cost_bps"]].copy()
        for name, factory in models.items():
            if factory is None:
                frame[name] = float(train["continues"].mean())
                continue
            model = factory()
            columns = columns_for(name)
            model.fit(train[columns].to_numpy(), train["continues"].to_numpy())
            frame[name] = model.predict_proba(test[columns].to_numpy())[:, 1]
        results.append(frame)
        folds.append(fold)
    predictions = pd.concat(results).reset_index(drop=True) if results else pd.DataFrame()
    return WalkForward(predictions=predictions, folds=folds)


def stance(probability: np.ndarray) -> np.ndarray:
    return np.where(probability >= WITH, 1, np.where(probability <= AGAINST, -1, 0))


def trade_returns(predictions: pd.DataFrame, probability: np.ndarray) -> pd.DataFrame:
    side = stance(probability)
    gross = side * predictions["remaining"].to_numpy() * 1e4
    net = gross - np.where(side != 0, predictions["cost_bps"].to_numpy(), 0.0)
    return pd.DataFrame({"side": side, "gross_bps": gross, "net_bps": net})


def t_stat(values: np.ndarray) -> float:
    if len(values) < 3 or np.std(values, ddof=1) == 0:
        return float("nan")
    return float(np.mean(values) / (np.std(values, ddof=1) / np.sqrt(len(values))))


def clustered_t(values: np.ndarray, clusters: np.ndarray) -> float:
    """t-statistic of the mean with one observation per cluster (the cluster mean): events
    decided on the same day share that day's market and count once."""
    frame = pd.DataFrame({"v": values, "c": clusters})
    means = frame.groupby("c")["v"].mean().to_numpy()
    if len(means) < 3:
        return float("nan")
    return float(means.mean() / (means.std(ddof=1) / np.sqrt(len(means))))


def decision_days(frame: pd.DataFrame) -> np.ndarray:
    return frame["decided_at"].dt.tz_convert(ET).dt.date.to_numpy()


def evaluate(predictions: pd.DataFrame) -> pd.DataFrame:
    """Skill (AUC, Brier) and money (net of costs) for each model, out of sample. Money is
    tested twice: per trade (t_net), and per trading day (t_net_days), because filings
    decided on the same day share that day's market and are not independent bets."""
    y = predictions["continues"].to_numpy()
    base = float(np.mean(y))
    days = decision_days(predictions)
    rows = []
    for name in candidates():
        p = np.clip(predictions[name].to_numpy(), 1e-4, 1 - 1e-4)
        trades = trade_returns(predictions, p)
        chosen = trades["side"].to_numpy() != 0
        taken = trades[chosen]
        hits = (np.sign(taken["gross_bps"]) > 0).mean() if len(taken) else float("nan")
        brier = brier_score_loss(y, p)
        rows.append(
            {
                "model": name,
                "events": len(y),
                "auc": roc_auc_score(y, p) if name != "base rate" else 0.5,
                "brier": brier,
                "brier_skill": 1 - brier / brier_score_loss(y, np.full(len(y), base)),
                "log_loss": log_loss(y, p, labels=[0, 1]),
                "decisions": len(taken),
                "coverage": len(taken) / len(y),
                "hit_rate": hits,
                "mean_gross_bps": float(taken["gross_bps"].mean()) if len(taken) else float("nan"),
                "mean_net_bps": float(taken["net_bps"].mean()) if len(taken) else float("nan"),
                "t_net": t_stat(taken["net_bps"].to_numpy()),
                "t_net_days": clustered_t(taken["net_bps"].to_numpy(), days[chosen]) if len(taken) else float("nan"),
            }
        )
    # Rules that need no model at all, for scale.
    remaining = predictions["remaining"].to_numpy() * 1e4
    cost = predictions["cost_bps"].to_numpy()
    for name, side in (("always with the move", 1), ("always against the move", -1)):
        net = side * remaining - cost
        rows.append(
            {
                "model": name,
                "events": len(y),
                "decisions": len(y),
                "coverage": 1.0,
                "hit_rate": float(np.mean(side * remaining > 0)),
                "mean_gross_bps": float(np.mean(side * remaining)),
                "mean_net_bps": float(np.mean(net)),
                "t_net": t_stat(net),
                "t_net_days": clustered_t(net, days),
            }
        )
    return pd.DataFrame(rows)


def reliability(predictions: pd.DataFrame, name: str, bins: int = 5) -> pd.DataFrame:
    p = predictions[name].to_numpy()
    y = predictions["continues"].to_numpy()
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    index = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    rows = []
    for b in range(bins):
        mask = index == b
        if mask.any():
            rows.append({"bin": b, "predicted": float(p[mask].mean()), "observed": float(y[mask].mean()), "events": int(mask.sum())})
    return pd.DataFrame(rows)


def fit_final(data: pd.DataFrame, name: str = "logistic, all features"):
    """The model the live runner uses: trained on every event whose outcome is known."""
    model = candidates()[name]()
    model.fit(data[columns_for(name)].to_numpy(), data["continues"].to_numpy())
    return model
