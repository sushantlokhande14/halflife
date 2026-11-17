"""The event study: how fast each kind of filing is priced in.

For every 8-K in the window this builds the event's path on the trading clock, measures
it, and places it against the stock's own volatility. An event is "informative" when the
abnormal move by the settling close is at least two of the stock's daily standard
deviations; the rest are kept, but half-lives are only read from informative events,
because the half-life of a move that did not happen is noise.

Two placebos keep the threshold honest:

* random moments: pseudo-events at random trading times for each stock, with no filing
  nearby. Whatever share of them clears the bar is the false-positive rate.
* shareholder-vote results (item 5.07): scheduled, routine filings that rarely carry
  news. They should look like the random moments, not like earnings.
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import asdict

import numpy as np
import pandas as pd

from .clock import Clock, minute_of_day, session, trading_days
from .config import DATA, MARKET, RESULTS, UTC
from .diffusion import CHECKPOINTS, Path, build_path, fit_two_speed, measure
from .ingest import load_bars
from .sources.sec import CATEGORY_ORDER

log = logging.getLogger("halflife.study")

INFORMATIVE_Z = 2.0
MERGE_MINUTES = 30
SIGMA_SESSIONS = 20
PLACEBO_PER_STOCK = 3
PRIORITY = {name: rank for rank, (name, _) in enumerate(CATEGORY_ORDER)}


def merge_bursts(filings: pd.DataFrame) -> pd.DataFrame:
    """A company often files two 8-Ks minutes apart about the same news. Within 30 minutes
    they count as one event: the first timestamp, the most significant category."""
    rows = []
    for _, group in filings.sort_values("accepted_at").groupby("ticker", sort=False):
        current = None
        for row in group.itertuples(index=False):
            if current is not None and (row.accepted_at - current["accepted_at"]).total_seconds() <= MERGE_MINUTES * 60:
                if PRIORITY.get(row.category, 99) < PRIORITY.get(current["category"], 99):
                    current["category"] = row.category
                    current["scheduled"] = row.scheduled
                current["items"] = ",".join(sorted(set(current["items"].split(",")) | set(row.items.split(","))))
                current["filings"] += 1
                continue
            if current is not None:
                rows.append(current)
            current = row._asdict() | {"filings": 1}
        if current is not None:
            rows.append(current)
    return pd.DataFrame(rows).sort_values("accepted_at").reset_index(drop=True)


def daily_context(stock_daily: pd.DataFrame, market_daily: pd.DataFrame, before_day) -> tuple[float, float]:
    """Trailing volatility of the stock's market-adjusted daily return, and its median daily
    dollar volume, from sessions strictly before `before_day`. Nothing from the event day
    or later goes in."""
    cutoff = pd.Timestamp(before_day).tz_localize(UTC) if pd.Timestamp(before_day).tzinfo is None else pd.Timestamp(before_day)
    stock = stock_daily[stock_daily.index < cutoff].tail(SIGMA_SESSIONS + 1)
    market = market_daily.reindex(stock.index)
    if len(stock) < 11 or market["close"].isna().any():
        return float("nan"), float("nan")
    abnormal = np.diff(np.log(stock["close"].to_numpy())) - np.diff(np.log(market["close"].to_numpy()))
    dollar_volume = float(np.median((stock["close"] * stock["volume"]).to_numpy()[1:]))
    return float(np.std(abnormal, ddof=1)), dollar_volume


def open_shares(clock: Clock, path: Path, t0) -> dict:
    """For an event before its reaction day's regular open: the share of the move priced
    in before the open, and the share added by the first two minutes of the session."""
    day = clock.reaction_day(t0)
    opening = clock.regular_open(day)
    if pd.Timestamp(t0) >= opening or path.car_h == 0:
        return {"done_before_open": float("nan"), "opening_jump": float("nan")}
    first_bar = clock.position(opening + pd.Timedelta(minutes=clock.step)) - path.ref_index
    before = float(path.car[first_bar - 1])
    return {"done_before_open": before / path.car_h, "opening_jump": (float(path.car[first_bar]) - before) / path.car_h}


def _event_row(event: dict, path: Path, sigma: float, dollar_volume: float, clock: Clock) -> dict:
    measured = measure(path) | open_shares(clock, path, event["accepted_at"])
    z = measured["car_h"] / sigma if sigma and np.isfinite(sigma) else float("nan")
    return {
        **event,
        **measured,
        "sigma": sigma,
        "dollar_volume": dollar_volume,
        "z": z,
        "informative": bool(np.isfinite(z) and abs(z) >= INFORMATIVE_Z),
    }


def build(placebo_seed: int = 17) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Path]]:
    """Events and placebo pseudo-events, each with its measurements, and every path."""
    universe = pd.read_parquet(DATA / "universe.parquet")
    filings = merge_bursts(pd.read_parquet(DATA / "filings.parquet"))
    market_bars = load_bars("2m", MARKET)
    market_daily = load_bars("1d", MARKET)
    clock = Clock(trading_days(market_bars))
    market = clock.on_grid(market_bars)
    first, last = clock.grid[0], clock.grid[-1]
    filings = filings[(filings["accepted_at"] > first) & (filings["accepted_at"] < last)]
    rng = np.random.default_rng(placebo_seed)

    rows, placebo_rows, paths = [], [], {}
    by_ticker = dict(tuple(filings.groupby("ticker")))
    for company in universe.itertuples(index=False):
        bars = load_bars("2m", company.yahoo)
        daily = load_bars("1d", company.yahoo)
        if bars is None or daily is None or bars.empty:
            continue
        stock = clock.on_grid(bars)
        events = by_ticker.get(company.ticker)
        event_times = [] if events is None else list(events["accepted_at"])
        for event in ([] if events is None else events.to_dict("records")):
            path = build_path(clock, stock, market, event["accepted_at"])
            if path is None:
                continue
            reaction = clock.reaction_day(event["accepted_at"])
            sigma, dollar_volume = daily_context(daily, market_daily, reaction)
            event_id = event["accession"]
            paths[event_id] = path
            rows.append(
                _event_row(
                    {
                        "event_id": event_id,
                        "ticker": company.ticker,
                        "sector": company.sector,
                        "accepted_at": event["accepted_at"],
                        "category": event["category"],
                        "scheduled": bool(event["scheduled"]),
                        "items": event["items"],
                        "filings": event["filings"],
                        "session": session(event["accepted_at"]),
                        "minute_of_day": minute_of_day(event["accepted_at"]),
                        "reaction_day": reaction,
                    },
                    path,
                    sigma,
                    dollar_volume,
                    clock,
                )
            )
        # Placebo moments: random trading times at least two trading days from any filing.
        candidates = rng.choice(len(clock.grid) - 2, size=PLACEBO_PER_STOCK * 4, replace=False)
        taken = 0
        for position in candidates:
            moment = clock.grid[position] + pd.Timedelta(seconds=int(rng.integers(1, 119)))
            if any(abs((moment - t).total_seconds()) < 2 * 86400 for t in event_times):
                continue
            path = build_path(clock, stock, market, moment)
            if path is None:
                continue
            reaction = clock.reaction_day(moment)
            sigma, dollar_volume = daily_context(daily, market_daily, reaction)
            placebo_id = f"placebo-{company.ticker}-{position}"
            paths[placebo_id] = path
            placebo_rows.append(
                _event_row(
                    {
                        "event_id": placebo_id,
                        "ticker": company.ticker,
                        "sector": company.sector,
                        "accepted_at": moment,
                        "category": "placebo",
                        "scheduled": False,
                        "items": "",
                        "filings": 0,
                        "session": session(moment),
                        "minute_of_day": minute_of_day(moment),
                        "reaction_day": reaction,
                    },
                    path,
                    sigma,
                    dollar_volume,
                    clock,
                )
            )
            taken += 1
            if taken >= PLACEBO_PER_STOCK:
                break
    events = pd.DataFrame(rows).sort_values("accepted_at").reset_index(drop=True)
    placebo = pd.DataFrame(placebo_rows).sort_values("accepted_at").reset_index(drop=True)
    log.info("events: %d measured, %d placebo moments", len(events), len(placebo))
    return events, placebo, paths


def bootstrap_median(values: np.ndarray, rng: np.random.Generator, draws: int = 2000) -> tuple[float, float, float]:
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return float("nan"), float("nan"), float("nan")
    medians = np.median(rng.choice(values, size=(draws, len(values)), replace=True), axis=1)
    return float(np.median(values)), float(np.quantile(medians, 0.05)), float(np.quantile(medians, 0.95))


def summarize(frame: pd.DataFrame, keys: list[str], rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for key, group in frame.groupby(keys):
        key = key if isinstance(key, tuple) else (key,)
        informative = group[group["informative"]]
        t50, t50_low, t50_high = bootstrap_median(informative["t50"].to_numpy(), rng)
        rows.append(
            {
                **dict(zip(keys, key)),
                "events": len(group),
                "informative": len(informative),
                "informative_share": len(informative) / len(group),
                "median_abs_move_bps": float(np.median(np.abs(group["car_h"]))) * 1e4,
                "median_abs_move_informative_bps": float(np.median(np.abs(informative["car_h"]))) * 1e4 if len(informative) else float("nan"),
                "t50_median": t50,
                "t50_low": t50_low,
                "t50_high": t50_high,
                "t90_median": float(np.nanmedian(informative["t90"])) if len(informative) else float("nan"),
                "fit_half_life_median": float(np.nanmedian(informative["fit_half_life"])) if len(informative) else float("nan"),
                "done_by_10min": float(np.nanmedian(informative["r10"])) if len(informative) else float("nan"),
                "done_by_60min": float(np.nanmedian(informative["r60"])) if len(informative) else float("nan"),
                "done_before_open": float(np.nanmedian(informative["done_before_open"])) if informative["done_before_open"].notna().any() else float("nan"),
                "opening_jump": float(np.nanmedian(informative["opening_jump"])) if informative["opening_jump"].notna().any() else float("nan"),
                "pre_event_share": float(np.nanmedian(informative["pre_car"] / informative["car_h"])) if len(informative) else float("nan"),
                "overshoot_share": float(np.mean(informative["peak_ratio"] > 1.25)) if len(informative) else float("nan"),
                "next_day_continues": float(np.mean(np.sign(informative["drift_next_day"]) == np.sign(informative["car_h"]))) if len(informative) else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def mean_curve(frame: pd.DataFrame, paths: dict[str, Path], tau_max: float, rng: np.random.Generator, draws: int = 1000):
    """Average incorporation (path / move at H) across events, at every 2-minute step up to
    tau_max, with a bootstrap band. Each event counts only up to its own H."""
    taus = np.arange(0, tau_max + 1e-9, 2.0)
    matrix = np.full((len(frame), len(taus)), np.nan)
    for row, event_id in enumerate(frame["event_id"]):
        path = paths[event_id]
        if path.car_h == 0:
            continue
        upto = min(path.i_h, len(taus) - 1)
        matrix[row, : upto + 1] = path.car[: upto + 1] / path.car_h
    mean = np.nanmean(matrix, axis=0)
    picks = rng.integers(0, len(frame), size=(draws, len(frame)))
    boot = np.array([np.nanmean(matrix[pick], axis=0) for pick in picks])
    return taus, mean, np.nanquantile(boot, 0.05, axis=0), np.nanquantile(boot, 0.95, axis=0), np.sum(np.isfinite(matrix), axis=0)


def latency_table(frame: pd.DataFrame, paths: dict[str, Path], rng: np.random.Generator) -> pd.DataFrame:
    """What is left of the move if you act L trading minutes after the last pre-event price.

    remaining: (CAR(H) - CAR(L)) / CAR(H) for informative events: the share of the move
    still ahead of a trader who knew its direction.
    follow: sign(CAR(L)) * (CAR(H) - CAR(L)) over all events, in bps: what trading in the
    direction of the move so far earned to H, before costs. No hindsight in it.
    """
    rows = []
    informative = frame[frame["informative"]]
    for minutes in CHECKPOINTS:
        remaining = []
        for event_id in informative["event_id"]:
            path = paths[event_id]
            if minutes <= path.tau[path.i_h]:
                remaining.append((path.car_h - path.at(minutes)) / path.car_h)
        follow = []
        for event_id in frame["event_id"]:
            path = paths[event_id]
            if minutes <= path.tau[path.i_h]:
                so_far = path.at(minutes)
                if so_far != 0:
                    follow.append(np.sign(so_far) * (path.car_h - so_far))
        remaining_arr = np.asarray(remaining)
        follow_arr = np.asarray(follow) * 1e4
        med, low, high = bootstrap_median(remaining_arr, rng)
        boot = rng.choice(follow_arr, size=(2000, len(follow_arr)), replace=True).mean(axis=1) if len(follow_arr) else np.array([np.nan])
        rows.append(
            {
                "latency_minutes": minutes,
                "remaining_median": med,
                "remaining_low": low,
                "remaining_high": high,
                "follow_mean_bps": float(np.mean(follow_arr)) if len(follow_arr) else float("nan"),
                "follow_low_bps": float(np.quantile(boot, 0.05)),
                "follow_high_bps": float(np.quantile(boot, 0.95)),
                "follow_events": len(follow_arr),
            }
        )
    return pd.DataFrame(rows)


def save(events: pd.DataFrame, placebo: pd.DataFrame, paths: dict[str, Path]) -> None:
    events.to_parquet(DATA / "events.parquet")
    placebo.to_parquet(DATA / "placebo.parquet")
    with open(DATA / "paths.pkl", "wb") as handle:
        pickle.dump({key: asdict(value) for key, value in paths.items()}, handle)


def load() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Path]]:
    events = pd.read_parquet(DATA / "events.parquet")
    placebo = pd.read_parquet(DATA / "placebo.parquet")
    with open(DATA / "paths.pkl", "rb") as handle:
        raw = pickle.load(handle)
    return events, placebo, {key: Path(**value) for key, value in raw.items()}
