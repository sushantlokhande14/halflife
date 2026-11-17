"""How a piece of news moves into a price.

For one event, the path is the stock's log return relative to the benchmark, measured
on the trading clock from the last price before the filing (tau = 0). The total move is
that path's value at H, the first regular close that gives the news time to settle.
Incorporation at tau is the path divided by the total move: 0 before anything has
happened, 1 once the price is where it ends up.

Two ways to say how fast that happened:

* first passage: the first tau at which incorporation reaches 50% (t50) or 90% (t90).
  Non-parametric and easy to audit.
* a partial-adjustment model, CAR(tau) = A (1 - exp(-tau / kappa)), whose half-life is
  kappa ln 2. Fitted per event and, with two speeds, to whole groups.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from .clock import Clock

PRE_WINDOW_MINUTES = 60
LN2 = float(np.log(2.0))


@dataclass
class Path:
    tau: np.ndarray  # trading minutes since the last price before the event
    car: np.ndarray  # cumulative abnormal log return since then
    raw: np.ndarray  # the stock's own log return since then
    market: np.ndarray  # the benchmark's log return since then
    traded: np.ndarray  # whether the stock traded in each step
    volume: np.ndarray
    i_h: int  # index of H, the first settling close
    i_h2: int  # index of the next trading day's close
    pre_car: float  # abnormal return over the hour before the event
    ref_index: int  # grid position of tau = 0

    @property
    def car_h(self) -> float:
        return float(self.car[self.i_h])

    @property
    def car_h2(self) -> float:
        return float(self.car[self.i_h2])

    def at(self, minutes: float) -> float:
        """The path at the last step at or before `minutes` (never after it)."""
        index = int(np.searchsorted(self.tau, minutes, side="right")) - 1
        return float(self.car[max(index, 0)])


def build_path(clock: Clock, stock: pd.DataFrame, market: pd.DataFrame, t0) -> Path | None:
    """stock and market are frames already placed on the clock's grid (Clock.on_grid)."""
    ref = clock.index_before(t0)
    pre = ref - PRE_WINDOW_MINUTES // clock.step
    horizons = clock.horizons(t0)
    if pre < 0 or horizons is None:
        return None
    try:
        i_h = clock.position(horizons[0])
        i_h2 = clock.position(horizons[1])
    except KeyError:
        return None
    close = stock["close"].to_numpy()
    bench = market["close"].to_numpy()
    window = slice(ref, i_h2 + 1)
    s = np.log(close[window])
    m = np.log(bench[window])
    if not np.all(np.isfinite(s)) or not np.all(np.isfinite(m)) or not np.isfinite(close[pre]) or not np.isfinite(bench[pre]):
        return None
    raw = s - s[0]
    mkt = m - m[0]
    pre_car = float((s[0] - np.log(close[pre])) - (m[0] - np.log(bench[pre])))
    return Path(
        tau=np.arange(len(s), dtype=float) * clock.step,
        car=raw - mkt,
        raw=raw,
        market=mkt,
        traded=stock["traded"].to_numpy()[window],
        volume=stock["volume"].to_numpy()[window],
        i_h=i_h - ref,
        i_h2=i_h2 - ref,
        pre_car=pre_car,
        ref_index=ref,
    )


def first_passage(tau: np.ndarray, ratio: np.ndarray, level: float) -> float:
    hits = np.nonzero(ratio >= level)[0]
    return float(tau[hits[0]]) if len(hits) else float("nan")


def exponential(tau, amplitude, kappa):
    return amplitude * (1.0 - np.exp(-tau / kappa))


def two_speed(tau, a_fast, k_fast, a_slow, k_slow):
    return a_fast * (1.0 - np.exp(-tau / k_fast)) + a_slow * (1.0 - np.exp(-tau / k_slow))


def r_squared(y: np.ndarray, fitted: np.ndarray) -> float:
    total = float(np.sum((y - y.mean()) ** 2))
    return 1.0 - float(np.sum((y - fitted) ** 2)) / total if total > 0 else float("nan")


def fit_exponential(tau: np.ndarray, car: np.ndarray, min_kappa: float = 0.5, max_kappa: float = 20000.0):
    """(amplitude, kappa, r2) for the single-speed model, or NaNs if it cannot be fitted."""
    keep = tau > 0
    x, y = tau[keep], car[keep]
    if len(x) < 4 or not np.any(y):
        return float("nan"), float("nan"), float("nan")
    guess = float(y[-1]) or float(y[np.argmax(np.abs(y))])
    try:
        (amplitude, kappa), _ = curve_fit(
            exponential, x, y, p0=(guess, 30.0), bounds=([-2.0, min_kappa], [2.0, max_kappa]), maxfev=20000
        )
    except (RuntimeError, ValueError):
        return float("nan"), float("nan"), float("nan")
    return float(amplitude), float(kappa), r_squared(y, exponential(x, amplitude, kappa))


def fit_two_speed(tau: np.ndarray, ratio: np.ndarray):
    """Fit a fast and a slow component to an incorporation curve. Returns a dict, or None."""
    keep = tau > 0
    x, y = tau[keep], ratio[keep]
    if len(x) < 8:
        return None
    try:
        params, _ = curve_fit(
            two_speed,
            x,
            y,
            p0=(0.6, 5.0, 0.4, 240.0),
            bounds=([-1.0, 0.5, -1.0, 30.0], [2.0, 30.0, 2.0, 50000.0]),
            maxfev=50000,
        )
    except (RuntimeError, ValueError):
        return None
    a_fast, k_fast, a_slow, k_slow = (float(p) for p in params)
    total = a_fast + a_slow
    return {
        "fast_share": a_fast / total if total else float("nan"),
        "fast_half_life": k_fast * LN2,
        "slow_half_life": k_slow * LN2,
        "r2": r_squared(y, two_speed(x, *params)),
        "params": params.tolist(),
    }


# Trading minutes after the last pre-event price at which incorporation is reported.
CHECKPOINTS = (2, 4, 6, 10, 16, 30, 60, 120, 240)


def measure(path: Path) -> dict:
    """Everything the study reports about one event's path."""
    h = path.i_h
    tau = path.tau[1 : h + 1]
    car_h = path.car_h
    out = {
        "car_h": car_h,
        "car_h2": path.car_h2,
        "drift_next_day": path.car_h2 - car_h,
        "pre_car": path.pre_car,
        "minutes_to_h": float(path.tau[h]),
        "traded_share": float(np.mean(path.traded[1 : h + 1])) if h > 0 else float("nan"),
    }
    if car_h != 0 and h > 0:
        ratio = path.car[1 : h + 1] / car_h
        out["t50"] = first_passage(tau, ratio, 0.5)
        out["t90"] = first_passage(tau, ratio, 0.9)
        out["peak_ratio"] = float(np.max(ratio))
        for minutes in CHECKPOINTS:
            out[f"r{minutes}"] = path.at(minutes) / car_h if minutes <= path.tau[h] else float("nan")
    amplitude, kappa, r2 = fit_exponential(path.tau[: h + 1], path.car[: h + 1])
    out.update({"fit_amplitude": amplitude, "fit_kappa": kappa, "fit_r2": r2, "fit_half_life": kappa * LN2})
    return out
