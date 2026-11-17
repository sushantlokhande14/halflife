"""What is known at decision time, and what happened afterwards.

The decision is taken DECISION_MINUTES of trading time after the last price before the
filing. Features are computed from a view of the path that physically stops there: the
arrays are cut before any function sees them, so no feature can read a later price by
mistake. The outcome is computed separately, from the full path.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .diffusion import Path
from .sources.sec import CATEGORY_ORDER

DECISION_MINUTES = 10
MIN_REACTION_Z = 0.5  # act only when the stock has moved at least half a daily s.d.

CATEGORIES = [name for name, _ in CATEGORY_ORDER] + ["misc"]
SESSIONS = ["pre", "regular", "post", "closed"]


@dataclass(frozen=True)
class KnownAt:
    """The part of a path visible at decision time."""

    tau: np.ndarray
    car: np.ndarray
    market: np.ndarray
    traded: np.ndarray
    pre_car: float
    minutes_to_h: float


def known_at(path: Path, decision_minutes: float = DECISION_MINUTES) -> KnownAt | None:
    index = int(np.searchsorted(path.tau, decision_minutes, side="right")) - 1
    if index < 2 or index >= path.i_h:
        return None  # too little reaction yet, or the settling close comes first
    cut = slice(0, index + 1)
    return KnownAt(
        tau=path.tau[cut].copy(),
        car=path.car[cut].copy(),
        market=path.market[cut].copy(),
        traded=path.traded[cut].copy(),
        pre_car=path.pre_car,
        # Known in advance from the calendar: how long until the settling close.
        minutes_to_h=float(path.tau[path.i_h]),
    )


def features(view: KnownAt, sigma: float, dollar_volume: float, session: str, category: str, scheduled: bool) -> dict:
    car_d = float(view.car[-1])
    scale = sigma if sigma and np.isfinite(sigma) else np.nan
    peak = float(np.max(np.abs(view.car[1:])))
    four_minutes_ago = float(view.car[max(len(view.car) - 3, 0)])
    out = {
        "z_d": car_d / scale,
        "abs_z_d": abs(car_d) / scale,
        "pre_z_aligned": np.sign(car_d) * view.pre_car / scale,
        "retrace_z": (peak - abs(car_d)) / scale,
        "late_z_aligned": np.sign(car_d) * (car_d - four_minutes_ago) / scale,
        "active_share": float(np.mean(view.traded[1:])),
        "market_aligned_bps": float(np.sign(car_d) * view.market[-1]) * 1e4,
        "log_sigma": float(np.log(scale)) if np.isfinite(scale) else np.nan,
        "log_dollar_volume": float(np.log(dollar_volume)) if dollar_volume and dollar_volume > 0 else np.nan,
        "log_minutes_to_h": float(np.log(view.minutes_to_h)),
        "scheduled": float(scheduled),
    }
    for name in SESSIONS:
        out[f"session_{name}"] = float(session == name)
    for name in CATEGORIES:
        out[f"category_{name}"] = float(category == name)
    return out


FEATURE_NAMES = list(
    features(
        KnownAt(np.arange(6.0), np.linspace(0, 0.01, 6), np.zeros(6), np.ones(6, bool), 0.0, 100.0),
        0.01,
        1e8,
        "regular",
        "earnings",
        True,
    ).keys()
)


def outcome(path: Path, decision_minutes: float = DECISION_MINUTES) -> dict:
    """Did the move continue from the decision to the settling close, and by how much
    (in the direction of the move so far)."""
    index = int(np.searchsorted(path.tau, decision_minutes, side="right")) - 1
    car_d = float(path.car[index])
    remaining = float(np.sign(car_d) * (path.car_h - car_d))
    return {"continues": int(remaining > 0), "remaining": remaining, "car_d": car_d}
