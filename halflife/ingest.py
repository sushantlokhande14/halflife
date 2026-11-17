"""Download everything the study needs, into data/.

    universe.parquet          S&P 500 constituents with CIKs
    filings.parquet           every 8-K those companies filed in the window
    bars/2m/<TICKER>.parquet  2-minute bars with pre- and post-market trading
    bars/1d/<TICKER>.parquet  daily bars, for trailing volatility and liquidity

Each source is cached by the HTTP client, so a second run costs nothing.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pandas as pd

from .config import DATA, MARKET, UTC
from .http import FetchError, Fetcher
from .sources import prices, sec, universe

log = logging.getLogger("halflife.ingest")

INTRADAY_DAYS = 59  # Yahoo serves 2-minute bars for the last 60 days, at most
DAILY_DAYS = 200


def bars_path(interval: str, symbol: str):
    return DATA / "bars" / interval / f"{symbol}.parquet"


def load_bars(interval: str, symbol: str) -> pd.DataFrame | None:
    path = bars_path(interval, symbol)
    return pd.read_parquet(path) if path.exists() else None


def ingest(fetcher: Fetcher, limit: int | None = None, workers: int = 4, refresh: bool = False) -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)

    members = universe.load(fetcher)
    if limit:
        members = members.head(limit)
    members.to_parquet(DATA / "universe.parquet")
    log.info("universe: %d companies", len(members))

    # Filings: one request per company, paced for the SEC's limit.
    rows = []
    failures = []

    def company_filings(row):
        return row, sec.filings(fetcher, int(row.cik))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(company_filings, row) for row in members.itertuples()]
        for future in as_completed(futures):
            try:
                row, found = future.result()
            except FetchError as error:
                failures.append(str(error))
                continue
            for filing in found:
                rows.append(
                    {
                        "ticker": row.ticker,
                        "yahoo": row.yahoo,
                        "sector": row.sector,
                        "cik": filing.cik,
                        "accession": filing.accession,
                        "accepted_at": filing.accepted_at,
                        "items": ",".join(filing.items),
                        "category": filing.category,
                        "scheduled": filing.scheduled,
                    }
                )
    filings = pd.DataFrame(rows).sort_values("accepted_at").reset_index(drop=True)
    window_start = now - timedelta(days=INTRADAY_DAYS + 1)
    filings = filings[filings["accepted_at"] >= window_start]
    filings.to_parquet(DATA / "filings.parquet")
    log.info("filings: %d 8-Ks since %s (%d companies failed)", len(filings), window_start.date(), len(failures))

    # Bars: the market benchmark first, then every company.
    symbols = [MARKET] + members["yahoo"].tolist()
    intraday_start = now - timedelta(days=INTRADAY_DAYS)
    daily_start = now - timedelta(days=DAILY_DAYS)
    missing = []

    def company_bars(symbol):
        for interval, begin, chunk in (("2m", intraday_start, 20), ("1d", daily_start, 400)):
            path = bars_path(interval, symbol)
            if path.exists() and not refresh:
                continue  # resumable: an interrupted run picks up where it stopped
            frame = prices.bars(fetcher, symbol, interval, begin, now, chunk_days=chunk)
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(path)
        return symbol

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(company_bars, symbol): symbol for symbol in symbols}
        for done, future in enumerate(as_completed(futures), 1):
            try:
                future.result()
            except FetchError as error:
                missing.append(futures[future])
                log.warning("bars failed for %s: %s", futures[future], error)
            if done % 50 == 0:
                log.info("bars: %d/%d", done, len(symbols))

    return {"companies": len(members), "filings": len(filings), "filing_failures": failures, "bar_failures": missing}
