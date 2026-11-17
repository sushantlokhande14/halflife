from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd
import pytest

from halflife.clock import Clock, session
from halflife.config import ET, UTC
from halflife.diffusion import LN2, build_path, fit_exponential, fit_two_speed, measure, two_speed

# Monday 2026-11-09 to Friday 2026-11-13, then Monday 2026-11-16.
DAYS = [date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12), date(2026, 11, 13), date(2026, 11, 16)]


def et(day: date, hour: int, minute: int = 0, second: int = 0) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(day, time(hour, minute, second), ET)).tz_convert(UTC)


def flat_bars(clock: Clock, price: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame({"close": price, "volume": 1000.0}, index=clock.grid)


def jump_bars(clock: Clock, t0, size: float, kappa: float, price: float = 100.0) -> pd.DataFrame:
    """A stock that is flat until t0, then moves by `size` (log) along an exponential with
    time constant `kappa` in trading minutes."""
    close = np.full(len(clock), price)
    first = clock.index_before(t0) + 1
    tau = (np.arange(len(clock)) - (first - 1)) * clock.step
    after = np.arange(len(clock)) >= first
    close[after] = price * np.exp(size * (1 - np.exp(-tau[after] / kappa)))
    return pd.DataFrame({"close": close, "volume": 1000.0}, index=clock.grid)


@pytest.fixture
def clock() -> Clock:
    return Clock(DAYS)


def test_grid_covers_the_extended_session_and_skips_the_night(clock):
    assert clock.per_day == 480
    assert clock.grid[0] == et(DAYS[0], 4, 2)
    assert clock.grid[479] == et(DAYS[0], 20, 0)
    # The night takes no time: Monday 20:00 is followed directly by Tuesday 04:02.
    assert clock.grid[480] == et(DAYS[1], 4, 2)
    # Friday 20:00 is followed by Monday 04:02: the weekend takes no time either.
    friday_close = clock.position(et(DAYS[4], 20, 0))
    assert clock.grid[friday_close + 1] == et(DAYS[5], 4, 2)


def test_index_before_is_strict(clock):
    at = clock.position(et(DAYS[1], 10, 0))
    assert clock.index_before(et(DAYS[1], 10, 0)) == at - 1
    assert clock.index_before(et(DAYS[1], 10, 0, 30)) == at
    # During the night, the last point before is the previous evening's 20:00.
    assert clock.grid[clock.index_before(et(DAYS[1], 2, 0))] == et(DAYS[0], 20, 0)


@pytest.mark.parametrize(
    "when, expected",
    [
        ((1, 7, 0), DAYS[1]),  # pre-market: that day's close
        ((1, 11, 0), DAYS[1]),  # mid-session: that day's close
        ((1, 15, 30), DAYS[2]),  # too late in the session: the next close
        ((1, 16, 5), DAYS[2]),  # after hours: the next close
        ((4, 17, 0), DAYS[5]),  # Friday evening: Monday
    ],
)
def test_reaction_day(clock, when, expected):
    day_index, hour, minute = when
    assert clock.reaction_day(et(DAYS[day_index], hour, minute)) == expected


def test_weekend_events_react_on_monday(clock):
    saturday = date(2026, 11, 14)
    assert clock.reaction_day(et(saturday, 12, 0)) == DAYS[5]
    assert session(et(saturday, 12, 0)) == "closed"


def test_sessions():
    day = DAYS[1]
    assert session(et(day, 3, 59)) == "closed"
    assert session(et(day, 4, 0)) == "pre"
    assert session(et(day, 9, 29)) == "pre"
    assert session(et(day, 9, 30)) == "regular"
    assert session(et(day, 16, 0)) == "post"
    assert session(et(day, 20, 0)) == "closed"


def test_the_grid_never_sees_a_later_trade(clock):
    t = et(DAYS[1], 10, 0)
    bars = pd.DataFrame(
        {"close": [100.0, 999.0], "volume": [10.0, 10.0]},
        index=pd.DatetimeIndex([t, t + pd.Timedelta(minutes=2)]),
    )
    placed = clock.on_grid(bars)
    assert placed.loc[t, "close"] == 100.0
    assert placed.loc[t + pd.Timedelta(minutes=2), "close"] == 999.0
    # Between bars, the last price carries forward; a point with no bar did not trade.
    later = t + pd.Timedelta(minutes=10)
    assert placed.loc[later, "close"] == 999.0
    assert not placed.loc[later, "traded"]
    assert placed.loc[t, "traded"]


def test_market_moves_are_not_abnormal(clock):
    t0 = et(DAYS[1], 11, 0, 30)
    move = jump_bars(clock, t0, size=0.03, kappa=20)
    path = build_path(clock, clock.on_grid(move), clock.on_grid(move), t0)
    assert path is not None
    assert np.allclose(path.car, 0.0)
    assert path.raw[-1] == pytest.approx(0.03, rel=1e-3)


@pytest.mark.parametrize("kappa", [8.0, 30.0, 120.0])
def test_a_known_half_life_is_recovered(clock, kappa):
    t0 = et(DAYS[1], 10, 15, 20)
    stock = clock.on_grid(jump_bars(clock, t0, size=0.05, kappa=kappa))
    market = clock.on_grid(flat_bars(clock))
    path = build_path(clock, stock, market, t0)
    result = measure(path)

    # A slow adjustment is not finished by the close; the rest shows up as next-day drift.
    settled = 1 - np.exp(-path.tau[path.i_h] / kappa)
    assert result["car_h"] == pytest.approx(0.05 * settled, rel=1e-6)
    assert result["drift_next_day"] == pytest.approx(0.05 * (1 - settled), abs=1e-3)
    assert result["fit_half_life"] == pytest.approx(kappa * LN2, rel=0.05)
    # First passage measures half of the move seen by the close, and lands on the first
    # 2-minute step at or after the exact crossing.
    crossing = -kappa * np.log(1 - 0.5 * settled)
    assert crossing <= result["t50"] < crossing + 2.0
    assert result["pre_car"] == pytest.approx(0.0, abs=1e-12)


def test_noise_does_not_hide_the_half_life(clock):
    rng = np.random.default_rng(7)
    t0 = et(DAYS[2], 9, 45, 10)
    bars = jump_bars(clock, t0, size=-0.06, kappa=40.0)
    bars["close"] = bars["close"] * np.exp(rng.normal(0, 0.002, len(bars)))
    path = build_path(clock, clock.on_grid(bars), clock.on_grid(flat_bars(clock)), t0)
    result = measure(path)
    assert result["fit_half_life"] == pytest.approx(40.0 * LN2, rel=0.25)


def test_after_hours_events_settle_at_the_next_close_and_skip_the_night(clock):
    t0 = et(DAYS[1], 16, 5, 0)
    stock = clock.on_grid(jump_bars(clock, t0, size=0.04, kappa=60.0))
    path = build_path(clock, stock, clock.on_grid(flat_bars(clock)), t0)
    # 16:04 -> 20:00 is 236 minutes; 04:00 -> 16:00 the next day is 720: 956 trading minutes.
    assert path.tau[path.i_h] == 956.0
    assert clock.grid[path.ref_index + path.i_h] == et(DAYS[2], 16, 0)


def test_pre_event_movement_is_measured_separately(clock):
    t0 = et(DAYS[1], 12, 0, 1)
    close = np.full(len(clock), 100.0)
    ref = clock.index_before(t0)
    close[ref - 10 : ref + 1] = 102.0  # the price moved in the 20 minutes before the filing
    stock = clock.on_grid(pd.DataFrame({"close": close, "volume": 1.0}, index=clock.grid))
    path = build_path(clock, stock, clock.on_grid(flat_bars(clock)), t0)
    assert path.pre_car == pytest.approx(np.log(1.02))
    assert path.car_h == pytest.approx(np.log(100 / 102))


def test_events_without_enough_data_are_skipped(clock):
    # Too early for an hour of history before it.
    assert build_path(clock, clock.on_grid(flat_bars(clock)), clock.on_grid(flat_bars(clock)), et(DAYS[0], 4, 10)) is None
    # Its next-day close is past the end of the data.
    assert build_path(clock, clock.on_grid(flat_bars(clock)), clock.on_grid(flat_bars(clock)), et(DAYS[5], 11, 0)) is None


def test_exponential_fit_reports_failure_rather_than_guessing():
    amplitude, kappa, r2 = fit_exponential(np.arange(10.0), np.zeros(10))
    assert np.isnan(kappa)


def test_two_speed_fit_separates_a_jump_from_a_drift():
    tau = np.arange(0, 960, 2.0)
    ratio = two_speed(tau, 0.7, 2.0, 0.3, 300.0)
    fit = fit_two_speed(tau, ratio)
    assert fit["fast_share"] == pytest.approx(0.7, abs=0.02)
    assert fit["slow_half_life"] == pytest.approx(300 * LN2, rel=0.05)
