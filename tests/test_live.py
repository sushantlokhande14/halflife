"""Finding filings live: what counts as new, and what is history."""

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from halflife import live
from halflife.clock import Clock
from halflife.config import UTC
from halflife.ledger import Ledger
from halflife.sources.sec import Filing, SearchHit

BUNDLE = {"ten_minutes": {"model_id": "a"}, "at_open": {"model_id": "b"}, "policy": {"version": 2}}


def filing(accession: str, accepted_at: datetime) -> Filing:
    return Filing(cik=1, accession=accession, form="8-K", accepted_at=accepted_at, items=("2.02",), category="earnings", document="x.htm")


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "STATE", tmp_path / "state.json")
    universe = pd.DataFrame({"ticker": ["AAA"], "cik": [1], "yahoo": ["AAA"]})
    return live.Runner(None, universe, BUNDLE, ledger=Ledger(tmp_path / "ledger.jsonl"))


def test_the_search_looks_ahead_for_filings_dated_the_next_business_day(runner, monkeypatch):
    windows = []
    monkeypatch.setattr(live.sec, "filed_between", lambda fetcher, start, end: windows.append((start, end)) or [])
    runner.discover(Clock([date(2026, 11, 17), date(2026, 11, 18)]))
    (start, end), = windows
    assert end - start >= timedelta(days=4)  # covers an evening filing dated across a weekend or holiday
    assert runner.state.started_at is not None
    assert [e["kind"] for e in runner.ledger.entries()] == ["started"]


def test_a_filing_accepted_before_the_first_start_is_history_even_if_listed_later(runner, monkeypatch):
    started = datetime(2026, 11, 17, 23, 24, tzinfo=UTC)  # 18:24 Eastern
    runner.baselined, runner.state.started_at = True, started.isoformat()
    accepted = {
        "before": started - timedelta(minutes=30),  # 17:54 Eastern: dated the next day, listed late
        "after": started + timedelta(minutes=30),
    }
    hits = [SearchHit(name, (1,), ("2.02",), "AAA", "2026-11-18") for name in accepted]
    monkeypatch.setattr(live.sec, "filed_between", lambda fetcher, start, end: hits)
    monkeypatch.setattr(live.sec, "filings", lambda fetcher, cik, use_cache=False: [filing(n, t) for n, t in accepted.items()])
    runner.discover(Clock([date(2026, 11, 17), date(2026, 11, 18), date(2026, 11, 19)]))
    detected = [e["payload"]["accession"] for e in runner.ledger.entries() if e["kind"] == "detected"]
    assert detected == ["after"]
    assert set(runner.state.seen) == {"before", "after"}  # both handled, neither looked at again
    assert [t.accession for t in runner.state.tracked] == ["after"]
