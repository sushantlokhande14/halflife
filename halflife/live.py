"""The live runner: find new filings as they land, decide, and keep score.

Every 20 seconds it asks the SEC search index for today's 8-Ks. A new one from an S&P 500
company is looked up in that company's submissions file for its exact acceptance time,
and recorded as detected, with how many seconds it took to notice.

Ten trading minutes after the last price before the filing, the runner pulls fresh
2-minute bars, computes the same features the model was trained on from the part of
the path that exists, and records a prediction: the probability the move continues, the
stance that follows, and every input. Filings that have not moved their stock are
recorded too, as skipped, so nothing is left out of the record.

After the settling close, it records what actually happened against each prediction.
All of it goes into the hash-chained ledger in results/ledger.jsonl.
"""

from __future__ import annotations

import json
import logging
import pickle
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from .clock import Clock, session, trading_days
from .config import DATA, ET, MARKET, RESULTS, UTC
from .diffusion import build_path
from .features import DECISION_MINUTES, MIN_REACTION_Z, features, known_at
from .http import FetchError, Fetcher
from .ledger import Ledger
from .model import COST_EXTENDED_BPS, COST_REGULAR_BPS, columns_for, stance
from .sources import prices, sec
from .study import daily_context

log = logging.getLogger("halflife.live")

LEDGER = RESULTS / "ledger.jsonl"
STATE = DATA / "live_state.json"
MODEL = DATA / "model.pkl"

# NYSE full-day closures. Early closes (the day after Thanksgiving, Christmas Eve) are
# treated as full days; a filing on one of those afternoons is judged a little late.
HOLIDAYS = {
    date(2026, 11, 26), date(2026, 12, 25),
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26), date(2027, 5, 31),
    date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25), date(2027, 12, 24),
}
STANCE_NAMES = {1: "with the move", -1: "against the move", 0: "stand aside"}


@dataclass
class Tracked:
    accession: str
    ticker: str
    yahoo: str
    cik: int
    category: str
    items: str
    scheduled: bool
    accepted_at: str
    detected_at: str
    decided: bool = False
    prediction_hash: str | None = None
    side: int = 0
    car_d: float = 0.0
    cost_bps: float = 0.0
    horizon: str | None = None
    resolved: bool = False


@dataclass
class State:
    seen: list[str] = field(default_factory=list)
    tracked: list[Tracked] = field(default_factory=list)

    def save(self) -> None:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"seen": self.seen, "tracked": [asdict(t) for t in self.tracked]}, indent=1), encoding="utf-8")

    @classmethod
    def load(cls) -> "State":
        if not STATE.exists():
            return cls()
        raw = json.loads(STATE.read_text(encoding="utf-8"))
        return cls(seen=raw["seen"], tracked=[Tracked(**t) for t in raw["tracked"]])


def upcoming_days(start: date, count: int = 10) -> list[date]:
    days, cursor = [], start
    while len(days) < count:
        if cursor.weekday() < 5 and cursor not in HOLIDAYS:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


class Runner:
    def __init__(self, fetcher: Fetcher, universe: pd.DataFrame, bundle: dict, ledger: Ledger | None = None):
        self.fetcher = fetcher
        self.by_cik = {int(row.cik): row for row in universe.itertuples(index=False)}
        self.bundle = bundle
        self.model = bundle["model"]
        self.ledger = ledger or Ledger(LEDGER)
        self.state = State.load()

    # -- time ----------------------------------------------------------------

    def clock(self, market_bars: pd.DataFrame) -> Clock:
        past = trading_days(market_bars)
        today = datetime.now(ET).date()
        return Clock(sorted(set(past) | set(upcoming_days(today))))

    def market_bars(self) -> pd.DataFrame:
        now = datetime.now(UTC)
        return prices.bars(self.fetcher, MARKET, "2m", now - timedelta(days=7), now, cache=False)

    # -- the three steps -------------------------------------------------------

    def discover(self) -> None:
        now = datetime.now(UTC)
        today = datetime.now(ET).date()
        days = [today] if datetime.now(ET).hour >= 6 else [today - timedelta(days=1), today]
        for day in days:
            for hit in sec.filed_on(self.fetcher, day):
                if hit.accession in self.state.seen:
                    continue
                company = next((self.by_cik[c] for c in hit.ciks if c in self.by_cik), None)
                if company is None:
                    self.state.seen.append(hit.accession)  # not in the universe
                    continue
                found = [f for f in sec.filings(self.fetcher, int(company.cik), use_cache=False) if f.accession == hit.accession]
                if not found:
                    continue  # the search index saw it first; try the submissions file next round
                filing = found[0]
                self.state.seen.append(hit.accession)
                latency = (now - filing.accepted_at).total_seconds()
                entry = self.ledger.append(
                    "detected",
                    {
                        "accession": filing.accession,
                        "ticker": company.ticker,
                        "accepted_at": filing.accepted_at.isoformat(),
                        "detection_latency_seconds": round(latency, 1),
                        "items": ",".join(filing.items),
                        "category": filing.category,
                        "session": session(filing.accepted_at),
                    },
                )
                log.info("detected %s %s (%s) %.0fs after acceptance", company.ticker, filing.category, filing.accession, latency)
                self.state.tracked.append(
                    Tracked(
                        accession=filing.accession,
                        ticker=company.ticker,
                        yahoo=company.yahoo,
                        cik=int(company.cik),
                        category=filing.category,
                        items=",".join(filing.items),
                        scheduled=filing.scheduled,
                        accepted_at=filing.accepted_at.isoformat(),
                        detected_at=entry["recorded_at"],
                    )
                )

    def _path(self, item: Tracked, market_bars: pd.DataFrame):
        now = datetime.now(UTC)
        clock = self.clock(market_bars)
        stock_bars = prices.bars(self.fetcher, item.yahoo, "2m", now - timedelta(days=7), now, cache=False)
        t0 = pd.Timestamp(item.accepted_at)
        path = build_path(clock, clock.on_grid(stock_bars), clock.on_grid(market_bars), t0)
        return clock, path

    def decide(self, market_bars: pd.DataFrame) -> None:
        now = pd.Timestamp(datetime.now(UTC))
        clock = None
        for item in self.state.tracked:
            if item.decided:
                continue
            clock = clock or self.clock(market_bars)
            t0 = pd.Timestamp(item.accepted_at)
            decision_at = clock.grid[clock.index_before(t0) + DECISION_MINUTES // clock.step]
            if now < decision_at + pd.Timedelta(seconds=90):  # wait for the bar to be published
                continue
            clock, path = self._path(item, market_bars)
            horizon = clock.horizons(t0)
            item.decided = True
            if path is None or horizon is None:
                self.ledger.append("skipped", {"accession": item.accession, "ticker": item.ticker, "reason": "no price path"})
                continue
            daily = prices.bars(self.fetcher, item.yahoo, "1d", now - timedelta(days=60), now, chunk_days=400, live_ttl=3600)
            market_daily = prices.bars(self.fetcher, MARKET, "1d", now - timedelta(days=60), now, chunk_days=400, live_ttl=3600)
            sigma, dollar_volume = daily_context(daily, market_daily, clock.reaction_day(t0))
            view = known_at(path)
            if view is None or not np.isfinite(sigma):
                self.ledger.append("skipped", {"accession": item.accession, "ticker": item.ticker, "reason": "not enough history"})
                continue
            values = features(view, sigma, dollar_volume, session(t0), item.category, item.scheduled)
            base = {
                "accession": item.accession,
                "ticker": item.ticker,
                "category": item.category,
                "accepted_at": item.accepted_at,
                "decided_at": clock.grid[path.ref_index + len(view.tau) - 1].isoformat(),
                "move_so_far_bps": round(float(view.car[-1]) * 1e4, 1),
                "move_so_far_sd": round(float(values["z_d"]), 3),
                "settles_at": horizon[0].isoformat(),
            }
            if values["abs_z_d"] < MIN_REACTION_Z:
                self.ledger.append("skipped", {**base, "reason": f"moved less than {MIN_REACTION_Z} daily s.d."})
                continue
            row = np.array([[values[name] for name in columns_for(self.bundle["name"])]])
            probability = float(self.model.predict_proba(row)[0, 1])
            side = int(stance(np.array([probability]))[0])
            decision_session = session(pd.Timestamp(base["decided_at"]))
            cost = COST_REGULAR_BPS if decision_session == "regular" else COST_EXTENDED_BPS
            entry = self.ledger.append(
                "prediction",
                {
                    **base,
                    "p_continue": round(probability, 4),
                    "stance": STANCE_NAMES[side],
                    "cost_bps": cost,
                    "model": self.bundle["model_id"],
                    "features": {key: (round(float(v), 6) if np.isfinite(v) else None) for key, v in values.items()},
                },
            )
            item.prediction_hash = entry["hash"]
            item.side, item.car_d, item.cost_bps = side, float(view.car[-1]), cost
            item.horizon = horizon[0].isoformat()
            log.info("predicted %s: p=%.2f, %s", item.ticker, probability, STANCE_NAMES[side])

    def resolve(self, market_bars: pd.DataFrame) -> None:
        now = pd.Timestamp(datetime.now(UTC))
        for item in self.state.tracked:
            if not item.prediction_hash or item.resolved or now < pd.Timestamp(item.horizon) + pd.Timedelta(minutes=10):
                continue
            clock, path = self._path(item, market_bars)
            if path is None:
                continue
            car_h = path.car_h
            remaining = float(np.sign(item.car_d) * (car_h - item.car_d))
            gross = item.side * remaining * 1e4
            self.ledger.append(
                "resolution",
                {
                    "accession": item.accession,
                    "ticker": item.ticker,
                    "prediction": item.prediction_hash,
                    "move_at_settle_bps": round(car_h * 1e4, 1),
                    "remaining_bps": round(remaining * 1e4, 1),
                    "continued": remaining > 0,
                    "net_bps": round(gross - (item.cost_bps if item.side else 0.0), 1),
                },
            )
            item.resolved = True
            log.info("resolved %s: remaining %.0f bps", item.ticker, remaining * 1e4)

    def step(self) -> None:
        self.discover()
        if any(not t.decided or (t.prediction_hash and not t.resolved) for t in self.state.tracked):
            market = self.market_bars()
            self.decide(market)
            self.resolve(market)
        self.state.save()

    def run(self, minutes: float | None = None, poll_seconds: float = 20.0) -> None:
        stop = time.monotonic() + minutes * 60 if minutes else None
        while stop is None or time.monotonic() < stop:
            started = time.monotonic()
            try:
                self.step()
            except FetchError as error:
                log.warning("a source failed this round: %s", error)
            time.sleep(max(0.0, poll_seconds - (time.monotonic() - started)))


def load_bundle() -> dict:
    with open(MODEL, "rb") as handle:
        return pickle.load(handle)
