import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from halflife.sources import calendars, prices, sec, universe

FIXTURES = Path(__file__).parent / "fixtures"


def test_submissions_become_8k_filings_with_exact_utc_acceptance_times():
    filings = sec.parse_submissions((FIXTURES / "sec_submissions.json").read_text(encoding="utf-8"))
    assert filings, "the fixture holds 8-Ks"
    assert all(f.form == "8-K" for f in filings)  # 10-Qs in the same file are skipped
    first = filings[0]
    assert first.accepted_at.tzinfo is not None and first.accepted_at.utcoffset().total_seconds() == 0
    assert first.category == sec.categorize(list(first.items))


@pytest.mark.parametrize(
    "items, category",
    [
        (["2.02", "9.01"], "earnings"),
        (["5.02", "2.02"], "earnings"),  # results outrank everything else in the same filing
        (["1.01", "9.01"], "deal"),
        (["5.02"], "leadership"),
        (["7.01", "8.01"], "disclosure"),
        (["5.07"], "vote"),
        (["9.01"], "misc"),
    ],
)
def test_categories_follow_the_priority_order(items, category):
    assert sec.categorize(items) == category


def test_search_hits_parse():
    raw = {
        "hits": {
            "total": {"value": 1},
            "hits": [{"_id": "x", "_source": {"adsh": "0000320193-26-000001", "ciks": ["0000320193"], "items": ["2.02"], "display_names": ["Apple Inc.  (AAPL)"], "file_date": "2026-11-17"}}],
        }
    }
    hits, total = sec.parse_search(json.dumps(raw))
    assert total == 1 and hits[0].ciks == (320193,) and hits[0].items == ("2.02",)


def test_chart_bars_are_indexed_by_end_time_and_unfinished_bars_dropped():
    start = 1794900000 - 1794900000 % 120
    raw = {
        "chart": {
            "result": [
                {
                    "timestamp": [start, start + 120, start + 240, start + 251],
                    "indicators": {"quote": [{"open": [1, 2, 3, 4], "high": [1, 2, 3, 4], "low": [1, 2, 3, 4], "close": [1.0, None, 3.0, 4.0], "volume": [10, 0, 5, None]}]},
                }
            ]
        }
    }
    frame = prices.parse_chart(json.dumps(raw), "2m", now=start + 360)
    # The bar with no close is dropped; the off-grid snapshot is dropped; the bar ending
    # after `now` is dropped. What remains is labelled by end time.
    assert list(frame.index.asi8 // 10**9) == [start + 120, start + 360]
    assert list(frame["close"]) == [1.0, 3.0]


def test_fomc_meetings_parse_with_their_statement_time():
    meetings = calendars.parse_fomc((FIXTURES / "fomc.html").read_text(encoding="utf-8"))
    october = [m for m in meetings if m.end == date(2026, 10, 28)]
    assert october and october[0].start == date(2026, 10, 27)
    statement = october[0].statement_at.tz_convert("America/New_York")
    assert (statement.hour, statement.minute) == (14, 0)
    december = [m for m in meetings if m.end == date(2026, 12, 9)]
    assert december and december[0].projections


def test_earnings_and_ipo_calendars_parse():
    earnings = calendars.parse_earnings((FIXTURES / "nasdaq_earnings.json").read_text(encoding="utf-8"), date(2026, 11, 18))
    assert len(earnings) == 6
    assert set(earnings["timing"]) <= {"before the open", "after the close", "time not given"}
    ipos = calendars.parse_ipos((FIXTURES / "nasdaq_ipos.json").read_text(encoding="utf-8"))
    assert set(ipos["status"]) <= {"upcoming", "priced"} and len(ipos) > 0


def test_one_share_class_per_company_keeps_the_liquid_one():
    members = pd.DataFrame(
        {
            "ticker": ["AAPL", "GOOGL", "GOOG", "FOXA", "FOX"],
            "cik": [320193, 1652044, 1652044, 1754301, 1754301],
        }
    )
    volume = {"AAPL": 9e9, "GOOGL": 6e9, "GOOG": 4e9, "FOXA": 1e8, "FOX": 3e8}
    kept = universe.one_line_per_company(members, volume)
    # One line per CIK, the more liquid class, in the original order.
    assert list(kept["ticker"]) == ["AAPL", "GOOGL", "FOX"]
    assert kept["cik"].is_unique
