"""Price bars from Yahoo's chart endpoint, including pre- and post-market trading.

Yahoo labels a bar by its start time. Here every bar is indexed by its end time
instead, so that "the price at time t" is always the close of a bar that has finished
by t. That one convention is what keeps a reaction measured after an event from
borrowing trades from before it, and features computed at a decision time from
seeing trades after it.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from ..config import UTC
from ..http import Fetcher

CHART = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?interval={interval}&includePrePost=true&period1={start}&period2={end}"
)

INTERVAL_MINUTES = {"1m": 1, "2m": 2, "5m": 5, "15m": 15, "1d": 1440}


def parse_chart(raw: bytes | str, interval: str, now: float | None = None) -> pd.DataFrame:
    """Bars indexed by end time (UTC). Bars that have not finished by `now` are dropped."""
    data = json.loads(raw)
    result = (data.get("chart") or {}).get("result")
    columns = ["open", "high", "low", "close", "volume"]
    if not result or not result[0].get("timestamp"):
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], tz=UTC, name="end"))
    result = result[0]
    quote = result["indicators"]["quote"][0]
    start = np.asarray(result["timestamp"], dtype="int64")
    frame = pd.DataFrame({name: pd.to_numeric(pd.Series(quote.get(name)), errors="coerce") for name in columns})
    frame["start"] = start
    step = INTERVAL_MINUTES[interval] * 60
    if interval != "1d":
        # The response ends with a point stamped at the time of the request, not on the
        # bar grid. It is a snapshot of an unfinished bar, so it goes.
        frame = frame[frame["start"] % step == 0]
    frame = frame.dropna(subset=["close"])
    frame["volume"] = frame["volume"].fillna(0.0)
    if interval == "1d":
        # A daily bar is labelled by its session. Index it by the session's date, at
        # midnight UTC, and leave it to the caller to use only sessions that are over.
        days = pd.to_datetime(frame["start"].to_numpy(), unit="s", utc=True).tz_convert("America/New_York").normalize()
        frame.index = pd.DatetimeIndex(days.tz_localize(None).tz_localize(UTC), name="session")
        frame = frame[~frame.index.duplicated(keep="last")].sort_index()
        return frame[columns]
    end = frame["start"] + step
    cutoff = time.time() if now is None else now
    frame = frame[end <= cutoff]
    end = end[frame.index]
    frame.index = pd.DatetimeIndex(pd.to_datetime(end.to_numpy(), unit="s", utc=True), name="end")
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    return frame[columns]


def bars(
    fetcher: Fetcher,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    chunk_days: int = 20,
    live_ttl: float = 600,
    cache: bool = True,
) -> pd.DataFrame:
    """Bars for [start, end), fetched in chunks. A chunk that ends more than a day ago is
    cached for good; the most recent one is refetched after live_ttl seconds."""
    frames = []
    cursor = start
    now = datetime.now(UTC)
    while cursor < end:
        stop = min(cursor + timedelta(days=chunk_days), end)
        url = CHART.format(symbol=symbol, interval=interval, start=int(cursor.timestamp()), end=int(stop.timestamp()))
        settled = stop < now - timedelta(days=1)
        body = fetcher.get(url, ttl=None if settled else live_ttl, use_cache=cache or settled)
        frames.append(parse_chart(body, interval))
        cursor = stop
    if not frames:
        return parse_chart("{}", interval)
    out = pd.concat(frames)
    return out[~out.index.duplicated(keep="last")].sort_index()
