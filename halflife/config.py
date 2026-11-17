"""Paths, clocks and client identities shared by every module."""

from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(os.environ.get("HALFLIFE_HOME", Path(__file__).resolve().parent.parent))
DATA = ROOT / "data"  # downloaded inputs and the HTTP cache; not committed
CACHE = DATA / "cache"
RESULTS = ROOT / "results"  # tables, figures and the prediction ledger; committed

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# SEC asks automated clients to identify themselves. Set HALFLIFE_SEC_USER_AGENT to
# "Your Name you@example.com" to do so; the default names the tool and nothing else.
# Without a contact, the SEC serves filing metadata (all this project needs) but not
# the documents themselves.
SEC_USER_AGENT = os.environ.get(
    "HALFLIFE_SEC_USER_AGENT", "halflife-research/0.1 (market microstructure research tool)"
)
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Resolution of the trading clock, in minutes. Yahoo serves 2-minute bars, with pre-
# and post-market trading, for roughly the last six weeks.
BAR_MINUTES = 2

# US equities trade from 04:00 to 20:00 Eastern on the extended clock.
EXTENDED_OPEN = (4, 0)
REGULAR_OPEN = (9, 30)
REGULAR_CLOSE = (16, 0)
EXTENDED_CLOSE = (20, 0)

MARKET = "SPY"  # the benchmark abnormal returns are measured against
