"""The steps the command line runs: study, model, radar. Each writes to results/."""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from . import model as model_module
from . import report, study
from .clock import Clock, trading_days
from .config import DATA, ET, MARKET, RESULTS, UTC
from .diffusion import fit_two_speed
from .http import Fetcher
from .ingest import load_bars
from .sources import calendars

log = logging.getLogger("halflife.pipeline")


def md_table(frame: pd.DataFrame, formats: dict[str, str] | None = None) -> str:
    formats = formats or {}
    header = "| " + " | ".join(frame.columns) + " |"
    rule = "|" + "|".join("---:" if pd.api.types.is_numeric_dtype(frame[c]) else "---" for c in frame.columns) + "|"
    lines = [header, rule]
    for row in frame.itertuples(index=False):
        cells = []
        for column, value in zip(frame.columns, row):
            if isinstance(value, float):
                cells.append("" if not np.isfinite(value) else format(value, formats.get(column, ".2f")))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


CURVE_GROUPS = [
    ("Earnings, after the close", lambda e: (e["category"] == "earnings") & (e["session"] == "post")),
    ("Earnings, before the open", lambda e: (e["category"] == "earnings") & (e["session"] == "pre")),
    ("Other filings, during the session", lambda e: (e["category"] != "earnings") & (e["session"] == "regular")),
]


def run_study() -> dict:
    out = RESULTS / "study"
    out.mkdir(parents=True, exist_ok=True)
    events, placebo, paths = study.build()
    study.save(events, placebo, paths)
    rng = np.random.default_rng(11)

    everything = pd.concat([events, placebo], ignore_index=True)
    by_category = study.summarize(everything, ["category"], rng).sort_values("informative_share", ascending=False)
    earnings_by_session = study.summarize(events[events["category"] == "earnings"], ["session"], rng)
    by_session = study.summarize(events, ["session"], rng)
    for name, frame in (("by_category", by_category), ("earnings_by_session", earnings_by_session), ("by_session", by_session)):
        frame.to_csv(out / f"{name}.csv", index=False)

    curves, fits, curve_tables = [], [], []
    informative = events[events["informative"]]
    for label, select in CURVE_GROUPS:
        group = informative[select(informative)]
        if len(group) < 8:
            continue
        # Show each curve as far as three quarters of its events can still be followed.
        tau_max = float(min(960.0, np.quantile(group["minutes_to_h"], 0.25)))
        taus, mean, low, high, counts = study.mean_curve(group, paths, tau_max, rng)
        curves.append({"label": label, "taus": taus, "mean": mean, "low": low, "high": high, "n": len(group)})
        fit = fit_two_speed(taus, mean) or {}
        fits.append({"group": label, "events": len(group), "minutes_shown": tau_max, **{k: v for k, v in fit.items() if k != "params"}})
        curve_tables.append(pd.DataFrame({"group": label, "tau": taus, "mean": mean, "low": low, "high": high, "events": counts}))
    if curve_tables:
        pd.concat(curve_tables).to_csv(out / "curves.csv", index=False)
    fits_frame = pd.DataFrame(fits)
    fits_frame.to_csv(out / "two_speed_fits.csv", index=False)

    earnings = events[events["category"] == "earnings"]
    latency_earnings = study.latency_table(earnings, paths, rng)
    latency_all = study.latency_table(events, paths, rng)
    latency_earnings.to_csv(out / "latency_earnings.csv", index=False)
    latency_all.to_csv(out / "latency_all.csv", index=False)

    figures = RESULTS / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    if curves:
        report.curves_figure(curves, figures / "incorporation_curves.png")
    report.latency_figure(latency_earnings, figures / "latency_earnings.png")
    report.informative_figure(by_category, figures / "informative_share.png")
    report.half_life_figure(earnings[earnings["informative"]], figures / "earnings_half_life.png")

    fomc = fomc_illustration()
    write_findings(events, placebo, by_category, earnings_by_session, fits_frame, latency_earnings, latency_all, fomc)
    return {"events": len(events), "placebo": len(placebo), "informative": int(events["informative"].sum())}


def fomc_illustration() -> dict | None:
    """The benchmark's own path after the one FOMC statement inside the data window. One
    meeting is an illustration, not a result."""
    market_bars = load_bars("2m", MARKET)
    clock = Clock(trading_days(market_bars))
    grid = clock.on_grid(market_bars)
    with Fetcher() as fetcher:
        meetings = calendars.fomc(fetcher)
    inside = [m for m in meetings if clock.grid[0] < m.statement_at < clock.grid[-1] - pd.Timedelta(days=1)]
    if not inside:
        return None
    meeting = inside[-1]
    ref = clock.index_before(meeting.statement_at + pd.Timedelta(seconds=1))
    close = np.log(grid["close"].to_numpy())
    path = close[ref : ref + 120] - close[ref]  # four hours of trading time
    settle = clock.position(clock.regular_close(meeting.end)) - ref
    total = float(close[ref + settle] - close[ref])
    ratio = path[1 : settle + 1] / total if total else np.full(settle, np.nan)
    first_half = next((2 * (i + 1) for i, r in enumerate(ratio) if r >= 0.5), float("nan"))
    peak = int(np.argmax(np.abs(path[1:settle + 1]))) + 1
    return {
        "date": str(meeting.end),
        "move_to_close_bps": total * 1e4,
        "first_half_minutes": first_half,
        "largest_excursion_bps": float(path[peak]) * 1e4,
        "largest_excursion_minutes": 2 * peak,
    }


def write_findings(events, placebo, by_category, earnings_by_session, fits, latency_earnings, latency_all, fomc) -> None:
    window = f"{events['accepted_at'].min():%Y-%m-%d} to {events['accepted_at'].max():%Y-%m-%d}"
    shown = by_category[
        ["category", "events", "informative", "informative_share", "median_abs_move_informative_bps", "t50_median", "t50_low", "t50_high", "t90_median", "done_by_10min", "pre_event_share", "next_day_continues"]
    ]
    session_cols = ["session", "events", "informative", "informative_share", "median_abs_move_informative_bps", "t50_median", "t50_low", "t50_high", "t90_median", "fit_half_life_median", "done_by_10min", "done_by_60min", "pre_event_share", "overshoot_share", "next_day_continues"]
    lines = [
        "# Study results (generated)",
        "",
        f"Window: {window}. S&P 500 8-K filings measured: {len(events)}; placebo moments: {len(placebo)}.",
        "Minutes are trading minutes after the last price before the filing. t50/t90: first time the",
        "path reaches 50%/90% of the move at the settling close (informative events only, median, 90% bootstrap interval).",
        "",
        "## By category",
        "",
        md_table(shown, {"informative_share": ".1%", "done_by_10min": ".0%", "pre_event_share": ".0%", "next_day_continues": ".0%", "median_abs_move_informative_bps": ".0f", "t50_median": ".0f", "t50_low": ".0f", "t50_high": ".0f", "t90_median": ".0f"}),
        "",
        "## Earnings, by when the filing landed",
        "",
        md_table(earnings_by_session[session_cols], {"informative_share": ".1%", "done_by_10min": ".0%", "done_by_60min": ".0%", "pre_event_share": ".0%", "overshoot_share": ".0%", "next_day_continues": ".0%", "median_abs_move_informative_bps": ".0f", "t50_median": ".0f", "t50_low": ".0f", "t50_high": ".0f", "t90_median": ".0f", "fit_half_life_median": ".0f"}),
        "",
        "## Two-speed fits to the average curves",
        "",
        md_table(fits, {"fast_share": ".0%", "fast_half_life": ".1f", "slow_half_life": ".0f", "r2": ".3f", "minutes_shown": ".0f"}) if len(fits) else "(not enough events)",
        "",
        "## Latency: what is left at each reaction time",
        "",
        "remaining: median share of an informative earnings move still ahead. follow: mean return to the settling close",
        "from trading in the direction of the move so far (all events, before costs).",
        "",
        "### Earnings",
        "",
        md_table(latency_earnings, {"remaining_median": ".0%", "remaining_low": ".0%", "remaining_high": ".0%", "follow_mean_bps": ".1f", "follow_low_bps": ".1f", "follow_high_bps": ".1f"}),
        "",
        "### All filings",
        "",
        md_table(latency_all, {"remaining_median": ".0%", "remaining_low": ".0%", "remaining_high": ".0%", "follow_mean_bps": ".1f", "follow_low_bps": ".1f", "follow_high_bps": ".1f"}),
        "",
    ]
    if fomc:
        lines += [
            "## The one FOMC statement in the window (illustration, n = 1)",
            "",
            md_table(pd.DataFrame([fomc]), {"move_to_close_bps": ".0f", "largest_excursion_bps": ".0f", "first_half_minutes": ".0f"}),
            "",
        ]
    (RESULTS / "study" / "findings.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def run_model() -> dict:
    out = RESULTS / "model"
    out.mkdir(parents=True, exist_ok=True)
    events, placebo, paths = study.load()
    market_bars = load_bars("2m", MARKET)
    clock = Clock(trading_days(market_bars))
    data = model_module.dataset(events, paths, clock.grid)
    data.drop(columns=[c for c in data.columns if c.startswith("category_") or c.startswith("session_")]).to_csv(out / "dataset_summary.csv", index=False)
    result = model_module.walk_forward(data)
    metrics = model_module.evaluate(result.predictions)
    metrics.to_csv(out / "metrics.csv", index=False)
    pd.DataFrame(result.folds).to_csv(out / "folds.csv", index=False)
    result.predictions.to_csv(out / "out_of_sample_predictions.csv", index=False)
    main = "logistic, all features"
    reliability = model_module.reliability(result.predictions, main)
    reliability.to_csv(out / "reliability.csv", index=False)
    report_reliability(reliability, RESULTS / "figures" / "reliability.png")

    final = model_module.fit_final(data, main)
    blob = pickle.dumps(final)
    model_id = hashlib.sha256(blob).hexdigest()[:12]
    bundle = {"model": final, "name": main, "model_id": model_id, "trained_events": len(data), "features": model_module.columns_for(main)}
    with open(DATA / "model.pkl", "wb") as handle:
        pickle.dump(bundle, handle)
    card = {
        "model": main,
        "model_id": model_id,
        "trained_events": len(data),
        "window": f"{data['accepted_at'].min():%Y-%m-%d} to {data['accepted_at'].max():%Y-%m-%d}",
        "continuation_base_rate": float(data["continues"].mean()),
        "thresholds": {"with": model_module.WITH, "against": model_module.AGAINST},
        "costs_bps": {"regular": model_module.COST_REGULAR_BPS, "extended": model_module.COST_EXTENDED_BPS},
        "coefficients": dict(zip(model_module.columns_for(main), np.round(final[-1].coef_[0], 4).tolist())),
    }
    (out / "model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8", newline="\n")
    lines = [
        "# Model results (generated)",
        "",
        f"Eligible events (moved at least {model_module.MIN_REACTION_Z} daily s.d. by the decision): {len(data)}; "
        f"out of sample: {len(result.predictions)} across {len(result.folds)} weekly folds. "
        f"Base rate of continuation: {data['continues'].mean():.1%}.",
        "",
        md_table(metrics, {"auc": ".3f", "brier": ".4f", "brier_skill": ".3f", "log_loss": ".4f", "coverage": ".0%", "hit_rate": ".1%", "mean_gross_bps": ".1f", "mean_net_bps": ".1f", "t_net": ".2f"}),
        "",
        "## Reliability of the main model's probabilities (out of sample)",
        "",
        md_table(reliability, {"predicted": ".3f", "observed": ".3f"}),
        "",
    ]
    (out / "findings.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return {"eligible": len(data), "out_of_sample": len(result.predictions), "folds": len(result.folds), "model_id": model_id}


def report_reliability(table: pd.DataFrame, path) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5.4, 5.0), dpi=150)
    ax.plot([0, 1], [0, 1], color=report.MUTED, linewidth=1, linestyle=(0, (3, 3)))
    ax.plot(table["predicted"], table["observed"], color=report.SERIES[0], linewidth=2, marker="o", markersize=6)
    for row in table.itertuples():
        ax.annotate(f"n={row.events}", (row.predicted, row.observed), xytext=(6, -10), textcoords="offset points", fontsize=8, color=report.INK_SECONDARY)
    low = float(min(table["predicted"].min(), table["observed"].min())) - 0.05
    high = float(max(table["predicted"].max(), table["observed"].max())) + 0.05
    ax.set_xlim(low, high)
    ax.set_ylim(low, high)
    report.style(ax, "Predicted vs observed continuation", "Predicted probability (bin mean)", "Observed frequency")
    fig.tight_layout()
    fig.savefig(path, facecolor=report.SURFACE)
    plt.close(fig)


def run_radar(days: int = 7) -> str:
    from .live import upcoming_days

    universe = pd.read_parquet(DATA / "universe.parquet")
    tickers = set(universe["ticker"]) | set(universe["yahoo"])
    profile_path = RESULTS / "study" / "earnings_by_session.csv"
    profile = pd.read_csv(profile_path).set_index("session") if profile_path.exists() else None
    today = datetime.now(ET).date()
    lines = [f"# Radar: scheduled events from {today}", ""]
    with Fetcher() as fetcher:
        meetings = [m for m in calendars.fomc(fetcher) if m.end >= today][:2]
        lines += ["## Federal Reserve", ""]
        for m in meetings:
            note = ", with economic projections and the dot plot" if m.projections else ""
            lines.append(f"- FOMC statement {m.statement_at.tz_convert(ET):%a %d %b %Y, %H:%M} ET (meeting {m.start:%d}-{m.end:%d %b}){note}")
        lines += ["", "## S&P 500 earnings", ""]
        rows = []
        for day in upcoming_days(today, days):
            frame = calendars.earnings(fetcher, day)
            if not frame.empty:
                rows.append(frame[frame["ticker"].isin(tickers)])
        earnings = pd.concat(rows) if rows else pd.DataFrame()
        if not earnings.empty:
            lines.append(md_table(earnings[["date", "ticker", "name", "timing", "eps_forecast", "estimates"]].astype(str)))
            if profile is not None:
                lines += ["", "What filings like these did in the study window (informative events, medians):", ""]
                for session_name, label in (("post", "after the close"), ("pre", "before the open")):
                    if session_name in profile.index:
                        row = profile.loc[session_name]
                        lines.append(
                            f"- Released {label}: {row['informative_share']:.0%} moved the stock 2+ daily s.d.; "
                            f"median move {row['median_abs_move_informative_bps']:.0f} bps; half priced in after {row['t50_median']:.0f} trading minutes."
                        )
        else:
            lines.append("None in the window.")
        lines += ["", "## IPOs", ""]
        month = today.strftime("%Y-%m")
        next_month = (today.replace(day=1) + timedelta(days=32)).strftime("%Y-%m")
        ipos = pd.concat([calendars.ipos(fetcher, month), calendars.ipos(fetcher, next_month)])
        upcoming = ipos[ipos["status"] == "upcoming"].drop_duplicates("ticker") if not ipos.empty else ipos
        lines.append(md_table(upcoming[["date", "ticker", "name", "exchange", "price", "deal_size"]].astype(str)) if len(upcoming) else "None listed.")
    text = "\n".join(lines) + "\n"
    (RESULTS / "radar.md").write_text(text, encoding="utf-8", newline="\n")
    return text
