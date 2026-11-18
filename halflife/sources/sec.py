"""8-K filings from the SEC.

An 8-K is a company's official notice that something material happened: results, a
deal, a departure. Its acceptance time is recorded to the second, which makes it the
most precisely timed piece of corporate news there is, and the clock this project
measures price reactions against.

Two endpoints are used. The per-company submissions file gives each filing's exact
acceptance time and item codes. The full-text search index lists every 8-K filed on a
day in one request, which is how the live runner finds new filings quickly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime

from ..config import UTC
from ..http import Fetcher

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEARCH = "https://efts.sec.gov/LATEST/search-index?forms=8-K&dateRange=custom&startdt={start}&enddt={end}&from={offset}"

# 8-K item codes, mapped to the kind of news they carry. A filing usually lists several
# items; the first match in this order decides its category. 9.01 (exhibits) is on
# almost every filing and decides nothing.
CATEGORY_ORDER: list[tuple[str, tuple[str, ...]]] = [
    ("earnings", ("2.02",)),
    ("deal", ("1.01", "1.02", "2.01")),
    ("leadership", ("5.02",)),
    ("financing", ("2.03", "2.04", "3.02", "3.03")),
    ("disclosure", ("7.01",)),
    ("vote", ("5.07",)),
    ("governance", ("5.03", "5.05", "5.08")),
    ("other", ("8.01",)),
]

# Earnings dates and shareholder meetings are announced in advance; the rest is not.
SCHEDULED = {"earnings", "vote"}


def categorize(items: list[str]) -> str:
    present = set(items)
    for category, codes in CATEGORY_ORDER:
        if present.intersection(codes):
            return category
    return "misc"


@dataclass(frozen=True)
class Filing:
    cik: int
    accession: str
    form: str
    accepted_at: datetime  # UTC; when the filing became public
    items: tuple[str, ...]
    category: str
    document: str

    @property
    def scheduled(self) -> bool:
        return self.category in SCHEDULED


def parse_accepted(value: str) -> datetime:
    """'2026-11-09T21:30:40.000Z' -> an aware UTC datetime. The suffix is honest: these are UTC."""
    return datetime.strptime(value.replace("Z", ""), "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=UTC)


def parse_submissions(raw: bytes | str, forms: tuple[str, ...] = ("8-K",)) -> list[Filing]:
    data = json.loads(raw)
    cik = int(data["cik"])
    recent = data["filings"]["recent"]
    out = []
    for index, form in enumerate(recent["form"]):
        if form not in forms:
            continue
        items = tuple(item.strip() for item in (recent["items"][index] or "").split(",") if item.strip())
        out.append(
            Filing(
                cik=cik,
                accession=recent["accessionNumber"][index],
                form=form,
                accepted_at=parse_accepted(recent["acceptanceDateTime"][index]),
                items=items,
                category=categorize(list(items)),
                document=recent["primaryDocument"][index],
            )
        )
    return out


def filings(fetcher: Fetcher, cik: int, ttl: float | None = 6 * 3600, use_cache: bool = True) -> list[Filing]:
    return parse_submissions(fetcher.get(SUBMISSIONS.format(cik=cik), ttl=ttl, use_cache=use_cache))


@dataclass(frozen=True)
class SearchHit:
    accession: str
    ciks: tuple[int, ...]
    items: tuple[str, ...]
    name: str
    file_date: str


def parse_search(raw: bytes | str) -> tuple[list[SearchHit], int]:
    data = json.loads(raw)
    hits = []
    for hit in data.get("hits", {}).get("hits", []):
        source = hit["_source"]
        hits.append(
            SearchHit(
                accession=source["adsh"],
                ciks=tuple(int(c) for c in source.get("ciks", [])),
                items=tuple(source.get("items") or ()),
                name=(source.get("display_names") or [""])[0],
                file_date=source.get("file_date", ""),
            )
        )
    total = data.get("hits", {}).get("total", {}).get("value", len(hits))
    return hits, int(total)


def filed_on(fetcher: Fetcher, day: date) -> list[SearchHit]:
    """Every 8-K the search index lists for a filing date, all pages."""
    return filed_between(fetcher, day, day)


def filed_between(fetcher: Fetcher, start: date, end: date) -> list[SearchHit]:
    """Every 8-K the search index lists with a filing date from start to end, all pages.

    The filing date is not always the day of acceptance: EDGAR dates an 8-K accepted after
    17:30 Eastern to the next business day, and the index lists it under that date.
    """
    hits: list[SearchHit] = []
    offset = 0
    while True:
        page, total = parse_search(
            fetcher.get(SEARCH.format(start=start.isoformat(), end=end.isoformat(), offset=offset), use_cache=False)
        )
        hits.extend(page)
        offset += len(page)
        if not page or offset >= total:
            return hits
