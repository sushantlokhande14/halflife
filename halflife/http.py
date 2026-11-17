"""A polite HTTP client: per-host pacing, retries with backoff, and a disk cache.

Every source this project reads is free and rate limited. The client keeps each host
under its limit across threads, retries what is worth retrying, and caches responses
on disk so that a study can be rerun without touching the network.
"""

from __future__ import annotations

import hashlib
import random
import threading
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import BROWSER_USER_AGENT, CACHE, SEC_USER_AGENT

# Requests per second, per host. The SEC publishes 10/s as its limit; the others are
# conservative guesses that have held up in use.
RATES = {
    "data.sec.gov": 8.0,
    "efts.sec.gov": 4.0,
    "query1.finance.yahoo.com": 3.0,
    "query2.finance.yahoo.com": 3.0,
    "api.nasdaq.com": 1.0,
    "news.google.com": 1.0,
    "en.wikipedia.org": 1.0,
    "www.federalreserve.gov": 1.0,
}
DEFAULT_RATE = 1.0

RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    def __init__(self, url: str, status: int | None, detail: str):
        super().__init__(f"{status or 'error'} for {url}: {detail}")
        self.url = url
        self.status = status


def user_agent_for(url: str) -> str:
    host = urlparse(url).hostname or ""
    return SEC_USER_AGENT if host.endswith("sec.gov") else BROWSER_USER_AGENT


class Fetcher:
    def __init__(self, cache_dir: Path = CACHE, rates: dict[str, float] | None = None, offline: bool = False):
        self.cache_dir = Path(cache_dir)
        self.rates = {**RATES, **(rates or {})}
        self.offline = offline
        self._client = httpx.Client(timeout=30.0, follow_redirects=True, headers={"Accept-Encoding": "gzip, deflate"})
        self._next_slot: dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _cache_path(self, url: str) -> Path:
        host = urlparse(url).hostname or "unknown"
        digest = hashlib.sha256(url.encode()).hexdigest()[:40]
        return self.cache_dir / host / f"{digest}.bin"

    def _wait_turn(self, host: str) -> None:
        interval = 1.0 / self.rates.get(host, DEFAULT_RATE)
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot[host])
            self._next_slot[host] = slot + interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def get(self, url: str, *, ttl: float | None = None, use_cache: bool = True, headers: dict | None = None) -> bytes:
        """Return the body of url.

        ttl is how long a cached copy stays good, in seconds; None keeps it forever,
        which suits historical data that cannot change. use_cache=False always fetches
        and does not store, which suits live polling.
        """
        path = self._cache_path(url)
        if use_cache and path.exists():
            fresh = ttl is None or (time.time() - path.stat().st_mtime) < ttl
            if fresh or self.offline:
                return path.read_bytes()
        if self.offline:
            raise FetchError(url, None, "offline and not cached")

        host = urlparse(url).hostname or ""
        request_headers = {"User-Agent": user_agent_for(url), "Accept": "*/*", **(headers or {})}
        last_error: Exception | None = None
        for attempt in range(6):
            self._wait_turn(host)
            try:
                response = self._client.get(url, headers=request_headers)
            except httpx.HTTPError as error:
                last_error = error
            else:
                if response.status_code == 200:
                    body = response.content
                    if use_cache:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        tmp = path.with_suffix(".tmp")
                        tmp.write_bytes(body)
                        tmp.replace(path)
                    return body
                if response.status_code not in RETRY_STATUS:
                    raise FetchError(url, response.status_code, response.text[:200])
                last_error = FetchError(url, response.status_code, response.text[:200])
            # Exponential backoff with jitter: 1, 2, 4, 8, 16 seconds.
            time.sleep(min(2**attempt, 16) * (0.75 + random.random() / 2))
        raise FetchError(url, getattr(last_error, "status", None), f"gave up after retries: {last_error}")
