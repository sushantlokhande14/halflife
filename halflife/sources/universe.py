"""The S&P 500, with each company's SEC identifier.

Wikipedia's constituents table carries the CIK next to the ticker, which is what joins
a filing to a price series. Using today's constituents for the last six weeks is a mild
survivorship choice; over a window this short, membership barely changes.
"""

from __future__ import annotations

from collections.abc import Mapping
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


def one_line_per_company(members: pd.DataFrame, dollar_volume: Mapping[str, float]) -> pd.DataFrame:
    """Keep one share class per company.

    Alphabet, Fox and News Corp each have two classes in the index, so 503 tickers are 500
    companies. Their 8-Ks are one filing under one CIK, and measuring both classes would count
    the same news twice. The class with the larger dollar volume is kept, so the price used is
    the one most of the trading happens in; the others keep their order.
    """
    liquidity = members["ticker"].map(dollar_volume).fillna(0.0)
    ranked = members.assign(_liquidity=liquidity).sort_values(["cik", "_liquidity"], ascending=[True, False], kind="stable")
    keep = ranked.drop_duplicates("cik", keep="first").index
    return members.loc[members.index.isin(keep)].reset_index(drop=True)


def load(fetcher: Fetcher, ttl: float = 7 * 86400) -> pd.DataFrame:
    return parse(fetcher.get(URL, ttl=ttl).decode("utf-8"))
