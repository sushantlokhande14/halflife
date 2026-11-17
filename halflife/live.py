"""The live runner: find new filings as they land, decide, and keep score.

Every 20 seconds during trading hours (every two minutes overnight) it asks the SEC
search index for today's 8-Ks. A new one from an S&P 500 company is looked up in that
company's submissions file for its exact acceptance time and recorded as detected, with
how long it took to notice.

Each filing gets up to two decisions, the two the backtest studied:

* ten minutes: ten trading minutes after the last price before the filing, the model's
  probability that the move continues, and the stance its thresholds give.
* at the open: for a filing released before the regular session, right after the
  session's first 2-minute bar, the fixed policy's stance (with the move) and its
  confidence (the historical continuation rate for that kind of filing).

A filing that has not moved its stock by a decision is recorded as skipped. After the
settling close, each prediction gets a resolution. All of it goes into the hash-chained
ledger in results/ledger.jsonl, and nothing is decided late: a decision more than ten
minutes overdue is recorded as skipped instead.
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
from .features import DECISION_MINUTES, MIN_REACTION_Z, decision_index, features, known_at
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
LATE = pd.Timedelta(minutes=10)
PUBLISH_WAIT = pd.Timedelta(seconds=90)  # a bar shows up on Yahoo a little after it ends


@dataclass
class Decision:
    mode: str  # "ten_minutes" or "at_open"
    due: str
    done: bool = False
    prediction: str | None = None  # hash of the ledger entry
    side: int = 0
    model_side: int = 0  # at the open: gradient boosting's stance, scored alongside the rule's
    car_d: float = 0.0
    cost_bps: float = 0.0
    settles: str | None = None
    resolved: bool = False


@dataclass
class Tracked:
    accession: str
    ticker: str
    yahoo: str
    category: str
    scheduled: bool
    accepted_at: str
    decisions: list[Decision] = field(default_factory=list)


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
        tracked = []
        for item in raw["tracked"]:
            decisions = [Decision(**d) for d in item.pop("decisions")]
            tracked.append(Tracked(**item, decisions=decisions))
        return cls(seen=raw["seen"], tracked=tracked)


def model_change(entries: list[dict], current: dict) -> dict | None:
    """The change to record when the runner restarts with other models or another policy
    than the ledger last named, or None. Every decision then traces to what made it."""
    last = None
    for entry in entries:
        if entry["kind"] in ("started", "models changed"):
            last = {"models": entry["payload"]["models"], "policy_version": entry["payload"]["policy_version"]}
    if last is None or last == current:
        return None
    return {**current, "replaces": last}


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
        self.ledger = ledger or Ledger(LEDGER)
        self.state = State.load()
        self.baselined = bool(self.state.seen)
        if self.baselined:
            change = model_change(self.ledger.entries(), self.deciding())
            if change is not None:
                self.ledger.append("models changed", {**change, "note": bundle["policy"].get("supersedes", {}).get("why")})

    def deciding(self) -> dict:
        """What makes the decisions: recorded when the runner first starts, and again
        whenever it restarts with different models or a different policy."""
        return {
            "models": {mode: self.bundle[mode]["model_id"] for mode in ("ten_minutes", "at_open")},
            "policy_version": self.bundle["policy"]["version"],
        }

    # -- time ----------------------------------------------------------------

    def market_bars(self) -> pd.DataFrame:
        now = datetime.now(UTC)
        return prices.bars(self.fetcher, MARKET, "2m", now - timedelta(days=7), now, cache=False)

    def clock(self, market_bars: pd.DataFrame) -> Clock:
        """Past trading days from the benchmark, plus the coming ones from the calendar, so
        decision times and settling closes in the future have a place on the grid."""
        today = datetime.now(ET).date()
        return Clock(sorted(set(trading_days(market_bars)) | set(upcoming_days(today))))

    # -- finding filings -------------------------------------------------------

    def discover(self, clock: Clock) -> None:
        now = datetime.now(UTC)
        local = datetime.now(ET)
        days = [local.date()] if local.hour >= 6 else [local.date() - timedelta(days=1), local.date()]
        hits = [hit for day in days for hit in sec.filed_on(self.fetcher, day)]
        if not self.baselined:
            # Whatever is already filed when the runner first starts is history, not news.
            self.state.seen.extend(hit.accession for hit in hits)
            self.baselined = True
            self.ledger.append("started", {"ignored_earlier_filings": len(hits), **self.deciding()})
            return
        for hit in hits:
            if hit.accession in self.state.seen:
                continue
            company = next((self.by_cik[c] for c in hit.ciks if c in self.by_cik), None)
            if company is None:
                self.state.seen.append(hit.accession)  # not in the S&P 500
                continue
            found = [f for f in sec.filings(self.fetcher, int(company.cik), use_cache=False) if f.accession == hit.accession]
            if not found:
                continue  # the search index saw it first; the submissions file will catch up
            filing = found[0]
            self.state.seen.append(hit.accession)
            t0 = pd.Timestamp(filing.accepted_at)
            decisions = [Decision("ten_minutes", clock.grid[clock.index_before(t0) + DECISION_MINUTES // clock.step].isoformat())]
            opening = clock.regular_open(clock.reaction_day(t0))
            if t0 < opening:
                decisions.append(Decision("at_open", (opening + pd.Timedelta(minutes=clock.step)).isoformat()))
            latency = (now - filing.accepted_at).total_seconds()
            self.ledger.append(
                "detected",
                {
                    "accession": filing.accession,
                    "ticker": company.ticker,
                    "category": filing.category,
                    "items": ",".join(filing.items),
                    "accepted_at": filing.accepted_at.isoformat(),
                    "session": session(t0),
                    "detection_latency_seconds": round(latency, 1),
                    "decisions_due": {d.mode: d.due for d in decisions},
                },
            )
            log.info("detected %s %s %.0fs after acceptance", company.ticker, filing.category, latency)
            self.state.tracked.append(
                Tracked(
                    accession=filing.accession,
                    ticker=company.ticker,
                    yahoo=company.yahoo,
                    category=filing.category,
                    scheduled=filing.scheduled,
                    accepted_at=filing.accepted_at.isoformat(),
                    decisions=decisions,
                )
            )

    # -- deciding ----------------------------------------------------------------

    def _path(self, clock: Clock, item: Tracked, market_bars: pd.DataFrame):
        now = datetime.now(UTC)
        stock_bars = prices.bars(self.fetcher, item.yahoo, "2m", now - timedelta(days=7), now, cache=False)
        return build_path(clock, clock.on_grid(stock_bars), clock.on_grid(market_bars), pd.Timestamp(item.accepted_at))

    def decide(self, clock: Clock, market_bars: pd.DataFrame) -> None:
        now = pd.Timestamp(datetime.now(UTC))
        for item in self.state.tracked:
            for decision in item.decisions:
                due = pd.Timestamp(decision.due)
                if decision.done or now < due + PUBLISH_WAIT:
                    continue
                decision.done = True
                base = {"accession": item.accession, "ticker": item.ticker, "decision": decision.mode}
                if now > due + PUBLISH_WAIT + LATE:
                    self.ledger.append("skipped", {**base, "reason": "too late to decide on time"})
                    continue
                self._decide_one(clock, market_bars, item, decision, base)

    def _decide_one(self, clock: Clock, market_bars: pd.DataFrame, item: Tracked, decision: Decision, base: dict) -> None:
        t0 = pd.Timestamp(item.accepted_at)
        path = self._path(clock, item, market_bars)
        horizon = clock.horizons(t0)
        if path is None or horizon is None:
            self.ledger.append("skipped", {**base, "reason": "no price path"})
            return
        if decision.mode == "ten_minutes":
            index = decision_index(path)
        else:
            index = clock.position(pd.Timestamp(decision.due)) - path.ref_index
        now = pd.Timestamp(datetime.now(UTC))
        daily = prices.bars(self.fetcher, item.yahoo, "1d", now - timedelta(days=60), now, chunk_days=400, live_ttl=3600)
        market_daily = prices.bars(self.fetcher, MARKET, "1d", now - timedelta(days=60), now, chunk_days=400, live_ttl=3600)
        sigma, dollar_volume = daily_context(daily, market_daily, clock.reaction_day(t0))
        view = known_at(path, index=index)
        if view is None or not np.isfinite(sigma):
            self.ledger.append("skipped", {**base, "reason": "not enough history"})
            return
        values = features(view, sigma, dollar_volume, session(t0), item.category, item.scheduled)
        decided_at = clock.grid[path.ref_index + len(view.tau) - 1]
        detail = {
            **base,
            "category": item.category,
            "accepted_at": item.accepted_at,
            "decided_at": decided_at.isoformat(),
            "move_so_far_bps": round(float(view.car[-1]) * 1e4, 1),
            "move_so_far_sd": round(float(values["z_d"]), 3),
            "settles_at": horizon[0].isoformat(),
        }
        if values["abs_z_d"] < MIN_REACTION_Z:
            self.ledger.append("skipped", {**detail, "reason": f"moved less than {MIN_REACTION_Z} daily s.d."})
            return
        entry = self.bundle[decision.mode]
        row = np.array([[values[name] for name in columns_for(entry["name"])]])
        p_model = float(entry["model"].predict_proba(row)[0, 1])
        cost = COST_REGULAR_BPS if session(decided_at) == "regular" else COST_EXTENDED_BPS
        policy = self.bundle["policy"]
        model_side = int(stance(np.array([p_model]))[0])
        extra = {}
        if decision.mode == "ten_minutes":
            side = model_side
            confidence = {"p_continue": round(p_model, 4), "source": f"{entry['name']}, no skill in the backtest"}
        else:
            # The rule, with its confidence from history; and the model, scored alongside it.
            segment = policy["at_open"]["segments"]["earnings" if item.category == "earnings" else "other"]
            side = 1
            confidence = {
                "p_continue": round(segment["continuation_rate"], 4),
                "p_low": round(segment["continuation_low"], 4),
                "p_high": round(segment["continuation_high"], 4),
                "historical_events": segment["events"],
                "historical_median_remaining_bps": round(segment["median_remaining_bps"], 1),
                "source": f"historical rate for this kind of filing (policy v{policy['version']})",
            }
            extra = {"model_stance": STANCE_NAMES[model_side], "model_p_continue": round(p_model, 4), "model_name": entry["name"]}
        written = self.ledger.append(
            "prediction",
            {
                **detail,
                "stance": STANCE_NAMES[side],
                "confidence": confidence,
                **extra,
                "cost_bps": cost,
                "model": entry["model_id"],
                "features": {key: (round(float(v), 6) if np.isfinite(v) else None) for key, v in values.items()},
            },
        )
        decision.prediction, decision.side = written["hash"], side
        decision.model_side = model_side if decision.mode == "at_open" else 0
        decision.car_d, decision.cost_bps = float(view.car[-1]), cost
        decision.settles = horizon[0].isoformat()
        log.info("%s %s: %s (move so far %.0f bps)", decision.mode, item.ticker, STANCE_NAMES[side], view.car[-1] * 1e4)

    # -- scoring -----------------------------------------------------------------

    def resolve(self, clock: Clock, market_bars: pd.DataFrame) -> None:
        now = pd.Timestamp(datetime.now(UTC))
        for item in self.state.tracked:
            pending = [d for d in item.decisions if d.prediction and not d.resolved and now >= pd.Timestamp(d.settles) + LATE]
            if not pending:
                continue
            path = self._path(clock, item, market_bars)
            if path is None:
                continue
            for decision in pending:
                remaining = float(np.sign(decision.car_d) * (path.car_h - decision.car_d))

                def net(side: int) -> float:
                    return round(side * remaining * 1e4 - (decision.cost_bps if side else 0.0), 1)

                scored = {"model_net_bps": net(decision.model_side)} if decision.mode == "at_open" else {}
                self.ledger.append(
                    "resolution",
                    {
                        "accession": item.accession,
                        "ticker": item.ticker,
                        "decision": decision.mode,
                        "prediction": decision.prediction,
                        "move_at_settle_bps": round(path.car_h * 1e4, 1),
                        "remaining_bps": round(remaining * 1e4, 1),
                        "continued": remaining > 0,
                        "net_bps": net(decision.side),
                        **scored,
                    },
                )
                decision.resolved = True
                log.info("resolved %s %s: remaining %.0f bps", decision.mode, item.ticker, remaining * 1e4)

    # -- the loop ----------------------------------------------------------------

    def step(self) -> None:
        market = self.market_bars()
        clock = self.clock(market)
        self.discover(clock)
        if any(not d.done or (d.prediction and not d.resolved) for t in self.state.tracked for d in t.decisions):
            self.decide(clock, market)
            self.resolve(clock, market)
        self.state.save()

    def run(self, minutes: float | None = None, poll_seconds: float = 20.0) -> None:
        stop = time.monotonic() + minutes * 60 if minutes else None
        while stop is None or time.monotonic() < stop:
            started = time.monotonic()
            try:
                self.step()
            except FetchError as error:
                log.warning("a source failed this round: %s", error)
            trading = session(pd.Timestamp(datetime.now(UTC))) != "closed"
            time.sleep(max(0.0, (poll_seconds if trading else 120.0) - (time.monotonic() - started)))


def load_bundle() -> dict:
    with open(MODEL, "rb") as handle:
        return pickle.load(handle)
