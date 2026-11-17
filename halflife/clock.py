"""The trading clock: where on the timeline a price can move.

US equities trade from 04:00 to 20:00 Eastern. Between 20:00 and the next 04:00, and over
weekends and holidays, nothing trades, so nothing can be priced in. Measuring reaction
time on the wall clock would credit an after-hours filing with twelve "slow" overnight
hours. The clock here is a grid of 2-minute steps over trading time only: 04:02 to 20:00
on every trading day, with the overnight closure taking up no time at all.

Grid points are bar end times. The price "at" a grid point is the close of the last bar
that ended at or before it, so nothing on the grid can see a trade that happened later.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

from .config import BAR_MINUTES, ET, UTC

REGULAR_OPEN_MINUTE = 9 * 60 + 30
REGULAR_CLOSE_MINUTE = 16 * 60
EXTENDED_OPEN_MINUTE = 4 * 60
EXTENDED_CLOSE_MINUTE = 20 * 60
# An event this close to the regular close is judged on the next day's close: a quarter
# of an hour of trading is not enough to say where the price settled.
LATE_CUTOFF_MINUTE = 15 * 60


def to_et(ts) -> datetime:
    return pd.Timestamp(ts).tz_convert(ET).to_pydatetime()


def minute_of_day(ts) -> float:
    local = to_et(ts)
    return local.hour * 60 + local.minute + local.second / 60


def session(ts) -> str:
    """Which part of the trading day a moment falls in: pre, regular, post or closed."""
    local = to_et(ts)
    if local.weekday() >= 5:
        return "closed"
    minute = local.hour * 60 + local.minute + local.second / 60
    if EXTENDED_OPEN_MINUTE <= minute < REGULAR_OPEN_MINUTE:
        return "pre"
    if REGULAR_OPEN_MINUTE <= minute < REGULAR_CLOSE_MINUTE:
        return "regular"
    if REGULAR_CLOSE_MINUTE <= minute < EXTENDED_CLOSE_MINUTE:
        return "post"
    return "closed"


def trading_days(market_bars: pd.DataFrame) -> list[date]:
    """Days on which the benchmark traded in the regular session."""
    local = market_bars.index.tz_convert(ET)
    minute = local.hour * 60 + local.minute
    regular = (minute > REGULAR_OPEN_MINUTE) & (minute <= REGULAR_CLOSE_MINUTE)
    return sorted(set(local[regular].date))


class Clock:
    def __init__(self, days: list[date], step: int = BAR_MINUTES):
        if not days:
            raise ValueError("a clock needs at least one trading day")
        self.days = sorted(days)
        self._day_set = set(self.days)
        self.step = step
        self.per_day = (EXTENDED_CLOSE_MINUTE - EXTENDED_OPEN_MINUTE) // step
        stamps = []
        for day in self.days:
            first = datetime.combine(day, time(4, 0), ET) + timedelta(minutes=step)
            stamps.append(pd.date_range(first, periods=self.per_day, freq=f"{step}min"))
        nanos = np.concatenate([s.asi8 for s in stamps])  # nanoseconds since the epoch, UTC
        self.grid = pd.DatetimeIndex(pd.to_datetime(nanos, utc=True))
        self._ns = nanos.tolist()

    def __len__(self) -> int:
        return len(self.grid)

    @staticmethod
    def _ns_of(ts) -> int:
        return pd.Timestamp(ts).tz_convert(UTC).value

    def index_before(self, ts) -> int:
        """Position of the last grid point strictly before ts, or -1."""
        return bisect_left(self._ns, self._ns_of(ts)) - 1

    def index_at_or_before(self, ts) -> int:
        return bisect_right(self._ns, self._ns_of(ts)) - 1

    def position(self, ts) -> int:
        ns = self._ns_of(ts)
        index = bisect_left(self._ns, ns)
        if index >= len(self._ns) or self._ns[index] != ns:
            raise KeyError(f"{ts} is not on the trading clock")
        return index

    def regular_close(self, day: date) -> pd.Timestamp:
        return pd.Timestamp(datetime.combine(day, time(16, 0), ET)).tz_convert(UTC)

    def regular_open(self, day: date) -> pd.Timestamp:
        return pd.Timestamp(datetime.combine(day, time(9, 30), ET)).tz_convert(UTC)

    def next_day(self, day: date) -> date | None:
        index = bisect_right(self.days, day)
        return self.days[index] if index < len(self.days) else None

    def reaction_day(self, ts) -> date | None:
        """The trading day whose close is taken as the price after the news is in.

        Before 15:00 on a trading day (pre-market included), that day. Later, or on a
        day the market is closed, the next trading day.
        """
        local = to_et(ts)
        day = local.date()
        minute = local.hour * 60 + local.minute + local.second / 60
        if day in self._day_set and minute < LATE_CUTOFF_MINUTE:
            return day
        return self.next_day(day)

    def horizons(self, ts) -> tuple[pd.Timestamp, pd.Timestamp] | None:
        """(H, H2): the reaction day's regular close, and the next trading day's."""
        first = self.reaction_day(ts)
        if first is None:
            return None
        second = self.next_day(first)
        if second is None:
            return None
        return self.regular_close(first), self.regular_close(second)

    def minutes_between(self, earlier: int, later: int) -> float:
        return float((later - earlier) * self.step)

    def on_grid(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Bars placed on the grid: the last close at or before each point, whether a bar
        ended exactly there (the stock traded in that step), and that bar's volume."""
        bars = bars.sort_index()
        combined = bars["close"].reindex(bars.index.union(self.grid)).ffill()
        out = pd.DataFrame(index=self.grid)
        out["close"] = combined.reindex(self.grid).to_numpy()
        exact = bars.reindex(self.grid)
        out["traded"] = exact["close"].notna().to_numpy()
        out["volume"] = exact["volume"].fillna(0.0).to_numpy()
        return out
