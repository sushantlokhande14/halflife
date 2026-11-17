"""The S&P 500, with each company's SEC identifier.

Wikipedia's constituents table carries the CIK next to the ticker, which is what joins
a filing to a price series. Using today's constituents for the last six weeks is a mild
survivorship choice; over a window this short, membership barely changes.
"""

from __future__ import annotations

from io import StringIO

import pandas as pd

from ..http import Fetcher

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def parse(html: str) -> pd.DataFrame:
    table = pd.read_html(StringIO(html), attrs={"id": "constituents"}, flavor="lxml")[0]
    out = pd.DataFrame(
        {
            "ticker": table["Symbol"].astype(str).str.strip(),
            "name": table["Security"].astype(str).str.strip(),
            "sector": table["GICS Sector"].astype(str).str.strip(),
            "cik": table["CIK"].astype(int),
        }
    )
    # Yahoo writes share classes with a dash: BRK.B is BRK-B.
    out["yahoo"] = out["ticker"].str.replace(".", "-", regex=False)
    return out.drop_duplicates("ticker").reset_index(drop=True)


def load(fetcher: Fetcher, ttl: float = 7 * 86400) -> pd.DataFrame:
    return parse(fetcher.get(URL, ttl=ttl).decode("utf-8"))
