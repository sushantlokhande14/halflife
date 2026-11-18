"""An append-only, hash-chained record of live predictions.

A backtest can be rerun until it looks good; a live record cannot, if it is written
before outcomes are known and cannot be edited afterwards. Every entry here carries the
hash of the entry before it, so changing, removing or reordering any past entry breaks
every hash after it. Pushing the file to GitHub each day before the close (publish.py)
adds an outside timestamp: a prediction pushed before its outcome existed is provably a
prediction.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from .config import UTC

GENESIS = "0" * 64


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def digest(body: dict) -> str:
    return hashlib.sha256(canonical(body)).hexdigest()


class Ledger:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def append(self, kind: str, payload: dict, now: datetime | None = None) -> dict:
        existing = self.entries()
        body = {
            "seq": len(existing),
            "recorded_at": (now or datetime.now(UTC)).isoformat(),
            "kind": kind,
            "payload": payload,
            "prev": existing[-1]["hash"] if existing else GENESIS,
        }
        entry = {**body, "hash": digest(body)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry, sort_keys=True, ensure_ascii=False, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return entry


def verify(path: Path | str) -> list[str]:
    """Every problem found, or an empty list for an intact chain."""
    path = Path(path)
    return verify_text(path.read_text(encoding="utf-8")) if path.exists() else []


def verify_text(text: str) -> list[str]:
    """The same check on a ledger's text, such as the exact content about to be committed."""
    problems = []
    if text.strip() and not text.endswith("\n"):
        problems.append("the last entry is incomplete (no newline at the end)")
    previous = GENESIS
    for position, line in enumerate(line for line in text.splitlines() if line.strip()):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"entry {position}: not valid JSON")
            break
        body = {key: entry.get(key) for key in ("seq", "recorded_at", "kind", "payload", "prev")}
        if entry.get("seq") != position:
            problems.append(f"entry {position}: sequence number {entry.get('seq')} out of order")
        if entry.get("prev") != previous:
            problems.append(f"entry {position}: does not follow the entry before it")
        if digest(body) != entry.get("hash"):
            problems.append(f"entry {position}: contents do not match its hash")
        previous = entry.get("hash")
    return problems
