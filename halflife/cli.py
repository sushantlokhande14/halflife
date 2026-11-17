"""halflife <command>

    ingest          download filings and bars for the S&P 500 into data/
    study           measure every filing's path; write results/study and figures
    model           walk-forward evaluation, then train the model the live runner uses
    radar           upcoming Fed meetings, S&P 500 earnings and IPOs
    live            watch for new filings, predict, and score, into results/ledger.jsonl
    verify-ledger   check that the ledger's hash chain is intact
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import RESULTS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="halflife", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("--limit", type=int, help="only the first N companies, for a quick run")
    ingest.add_argument("--refresh", action="store_true", help="download bars again even if present")
    sub.add_parser("study")
    sub.add_parser("model")
    radar = sub.add_parser("radar")
    radar.add_argument("--days", type=int, default=7)
    live = sub.add_parser("live")
    live.add_argument("--minutes", type=float, help="stop after this long; default runs until interrupted")
    live.add_argument("--poll", type=float, default=20.0, help="seconds between checks for new filings")
    sub.add_parser("verify-ledger")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.command == "ingest":
        from .http import Fetcher
        from .ingest import ingest as run

        with Fetcher() as fetcher:
            summary = run(fetcher, limit=args.limit, refresh=args.refresh)
        print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in summary.items()}))
    elif args.command == "study":
        from .pipeline import run_study

        print(json.dumps(run_study()))
    elif args.command == "model":
        from .pipeline import run_model

        print(json.dumps(run_model()))
    elif args.command == "radar":
        from .pipeline import run_radar

        print(run_radar(args.days))
    elif args.command == "live":
        from .http import Fetcher
        from .ingest import companies
        from .live import Runner, load_bundle

        with Fetcher() as fetcher:
            runner = Runner(fetcher, companies(), load_bundle())
            try:
                runner.run(minutes=args.minutes, poll_seconds=args.poll)
            except KeyboardInterrupt:
                runner.state.save()
                print("stopped; state saved")
    elif args.command == "verify-ledger":
        from .ledger import verify

        problems = verify(RESULTS / "ledger.jsonl")
        print("ledger intact" if not problems else "\n".join(problems))
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
