"""Scheduled events: Fed meetings, earnings dates and IPOs.

The FOMC publishes its meeting dates a year ahead; the statement comes out at 14:00
Eastern on the last day. Nasdaq's public calendars list upcoming earnings with their
timing (before the open or after the close) and the IPO pipeline.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time

import pandas as pd
from bs4 import BeautifulSoup

from ..config import ET, UTC
from ..http import Fetcher

FOMC = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
EARNINGS = "https://api.nasdaq.com/api/calendar/earnings?date={day}"
IPOS = "https://api.nasdaq.com/api/ipo/calendar?date={month}"

MONTHS = {name: number for number, name in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1
)}
MONTHS.update({name[:3]: number for name, number in list(MONTHS.items())})


@dataclass(frozen=True)
class FomcMeeting:
    start: date
    end: date
    projections: bool  # meetings marked * come with the Summary of Economic Projections

    @property
    def statement_at(self) -> pd.Timestamp:
        return pd.Timestamp(datetime.combine(self.end, time(14, 0), ET)).tz_convert(UTC)


def parse_fomc(html: str) -> list[FomcMeeting]:
    soup = BeautifulSoup(html, "lxml")
    meetings = []
    for panel in soup.select("div.panel"):
        heading = panel.select_one(".panel-heading")
        found = re.search(r"(\d{4}) FOMC Meetings", heading.get_text(" ", strip=True) if heading else "")
        if not found:
            continue
        year = int(found.group(1))
        for row in panel.select(".fomc-meeting"):
            month_text = row.select_one(".fomc-meeting__month").get_text(" ", strip=True)
            day_text = row.select_one(".fomc-meeting__date").get_text(" ", strip=True)
            months = [MONTHS[m] for m in re.findall(r"[A-Z][a-z]+", month_text) if m in MONTHS]
            days = [int(d) for d in re.findall(r"\d+", day_text)]
            if not months or not days:
                continue
            first_month, last_month = months[0], months[-1]
            start = date(year, first_month, days[0])
            end = date(year, last_month, days[-1])
            meetings.append(FomcMeeting(start=start, end=end, projections="*" in day_text))
    return sorted(meetings, key=lambda m: m.end)


def fomc(fetcher: Fetcher) -> list[FomcMeeting]:
    return parse_fomc(fetcher.get(FOMC, ttl=86400).decode("utf-8", "replace"))


TIMING = {"time-pre-market": "before the open", "time-after-hours": "after the close", "time-not-supplied": "time not given"}


def parse_earnings(raw: bytes | str, day: date) -> pd.DataFrame:
    data = json.loads(raw).get("data") or {}
    rows = data.get("rows") or []
    return pd.DataFrame(
        [
            {
                "date": day,
                "ticker": row.get("symbol", "").strip(),
                "name": row.get("name", "").strip(),
                "timing": TIMING.get(row.get("time", ""), row.get("time", "")),
                "eps_forecast": row.get("epsForecast", ""),
                "estimates": row.get("noOfEsts", ""),
                "market_cap": row.get("marketCap", ""),
            }
            for row in rows
        ]
    )


def earnings(fetcher: Fetcher, day: date) -> pd.DataFrame:
    return parse_earnings(fetcher.get(EARNINGS.format(day=day.isoformat()), ttl=6 * 3600), day)


def parse_ipos(raw: bytes | str) -> pd.DataFrame:
    data = json.loads(raw).get("data") or {}
    rows = []
    for status in ("upcoming", "priced"):
        section = data.get(status) or {}
        table = section.get("rows") or (section.get("upcomingTable") or {}).get("rows") or []
        for row in table:
            rows.append(
                {
                    "status": status,
                    "ticker": row.get("proposedTickerSymbol", ""),
                    "name": row.get("companyName", ""),
                    "exchange": row.get("proposedExchange", ""),
                    "price": row.get("proposedSharePrice", ""),
                    "date": row.get("expectedPriceDate") or row.get("pricedDate") or "",
                    "deal_size": row.get("dollarValueOfSharesOffered", ""),
                }
            )
    return pd.DataFrame(rows)


def ipos(fetcher: Fetcher, month: str) -> pd.DataFrame:
    return parse_ipos(fetcher.get(IPOS.format(month=month), ttl=6 * 3600))
