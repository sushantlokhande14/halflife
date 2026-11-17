from datetime import date, datetime, time

import numpy as np
import pandas as pd
import pytest

from halflife.clock import Clock
from halflife.config import ET, UTC
from halflife.diffusion import build_path
from halflife.features import DECISION_MINUTES, features, known_at, outcome
from halflife.model import stance, trade_returns, walk_forward

DAYS = [date(2026, 11, d) for d in (9, 10, 11, 12, 13)] + [date(2026, 11, 16)]


def et(day, hour, minute=0, second=0):
    return pd.Timestamp(datetime.combine(day, time(hour, minute, second), ET)).tz_convert(UTC)


def path_with_future(clock: Clock, t0, future: float):
    """A stock that rises 1% in the first ten minutes after t0, then moves by `future`."""
    close = np.full(len(clock), 100.0)
    ref = clock.index_before(t0)
    decision = ref + DECISION_MINUTES // clock.step
    close[ref + 1 : decision + 1] = np.linspace(100.2, 101.0, decision - ref)
    close[decision + 1 :] = 101.0 * np.exp(future)
    grid = pd.DataFrame({"close": close, "volume": 1.0}, index=clock.grid)
    flat = pd.DataFrame({"close": 50.0, "volume": 1.0}, index=clock.grid)
    return build_path(clock, clock.on_grid(grid), clock.on_grid(flat), t0)


def test_features_cannot_see_past_the_decision_time():
    clock = Clock(DAYS)
    t0 = et(DAYS[1], 10, 0, 5)
    up = path_with_future(clock, t0, future=+0.05)
    down = path_with_future(clock, t0, future=-0.05)

    view_up, view_down = known_at(up), known_at(down)
    assert view_up.tau[-1] == DECISION_MINUTES
    # Two futures that could not be more different give identical features...
    a = features(view_up, 0.01, 1e9, "regular", "earnings", True)
    b = features(view_down, 0.01, 1e9, "regular", "earnings", True)
    assert a == b
    # ...and opposite outcomes.
    assert outcome(up)["continues"] == 1
    assert outcome(down)["continues"] == 0
    assert outcome(up)["remaining"] == pytest.approx(0.05, rel=1e-6)


def test_no_decision_when_the_close_comes_first():
    clock = Clock(DAYS)
    # 15:00 events settle at the next day's close, so a decision is possible...
    assert known_at(path_with_future(clock, et(DAYS[1], 15, 0, 5), 0.0)) is not None


def test_stance_thresholds():
    assert list(stance(np.array([0.9, 0.55, 0.5, 0.45, 0.1]))) == [1, 1, 0, -1, -1]


def test_trade_returns_charge_costs_only_when_trading():
    predictions = pd.DataFrame({"remaining": [0.01, 0.01, -0.02], "cost_bps": [10.0, 30.0, 10.0]})
    trades = trade_returns(predictions, np.array([0.8, 0.5, 0.2]))
    assert list(trades["side"]) == [1, 0, -1]
    assert list(trades["gross_bps"]) == pytest.approx([100.0, 0.0, 200.0])
    assert list(trades["net_bps"]) == pytest.approx([90.0, 0.0, 190.0])


def test_walk_forward_never_trains_on_an_outcome_from_the_future():
    rng = np.random.default_rng(0)
    rows = []
    start = pd.Timestamp("2026-10-05 14:00", tz=UTC)
    for i in range(400):
        accepted = start + pd.Timedelta(hours=6 * i)
        row = {name: rng.normal() for name in ("z_d", "abs_z_d")}
        rows.append(
            {
                "event_id": f"e{i}",
                "accepted_at": accepted,
                # The outcome is known one day later.
                "known_at": accepted + pd.Timedelta(days=1),
                "decision_session": "regular",
                "category": "other",
                "session": "regular",
                "continues": int(rng.random() < 0.5),
                "remaining": rng.normal(0, 0.01),
                "cost_bps": 10.0,
                **row,
            }
        )
    from halflife import model as model_module

    names = model_module.FEATURE_NAMES
    frame = pd.DataFrame(rows)
    for name in names:
        if name not in frame:
            frame[name] = rng.normal(size=len(frame))
    result = walk_forward(frame, min_train=40)
    assert result.folds
    for fold in result.folds:
        begin = fold["start"]
        trained_on = frame[frame["known_at"] < begin]
        assert len(trained_on) == fold["train"]
        assert trained_on["known_at"].max() < begin
        # Every test event of the fold happened after training data was closed off.
        tested = result.predictions[result.predictions["accepted_at"] >= begin]
        assert len(tested) >= fold["test"]
    assert (result.predictions["accepted_at"] >= result.folds[0]["start"]).all()
