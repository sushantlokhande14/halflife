"""Commit and push the live ledger, so each prediction reaches GitHub before its outcome.

Run once a day at 15:45 Eastern, before the close. Every prediction the runner makes
settles at a 16:00 close or later: one made before 15:45 is in that day's commit, and one
made after it settles no earlier than the next day's close, after the next commit. So every
prediction is on GitHub before its outcome exists, and the git history is the outside
timestamp the hash chain cannot give itself.

Only the ledger is committed, and only once the exact content being committed verifies.
The run stops instead of touching anything else: other staged changes, or other commits
not yet pushed, are left for their owner.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import ROOT
from .ledger import verify_text

LEDGER = "results/ledger.jsonl"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # a scheduled run should not flash a console


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=check, creationflags=NO_WINDOW
    )


def publish(root: Path = ROOT, push: bool = True) -> str:
    """Commit the ledger's new entries and push them. Returns what happened, in one line."""
    staged = [name for name in git(root, "diff", "--cached", "--name-only").stdout.splitlines() if name != LEDGER]
    if staged:
        return f"not committed: other changes are staged ({', '.join(staged[:3])})"
    if git(root, "status", "--porcelain", "--", LEDGER).stdout.strip():
        git(root, "add", "--", LEDGER)
        text = git(root, "show", f":{LEDGER}").stdout  # exactly what the commit will hold
        problems = verify_text(text)
        if problems:
            git(root, "reset", "-q", "--", LEDGER)
            return "not committed: " + "; ".join(problems[:3])
        entries = [json.loads(line) for line in text.splitlines() if line.strip()]
        through = entries[-1]["recorded_at"][:16].replace("T", " ") if entries else "the start"
        git(root, "commit", "-q", "-m", f"Ledger: {len(entries)} entries, through {through} UTC")
        done = f"committed {len(entries)} entries"
    else:
        done = "no new entries"
    if not push:
        return done
    ahead = git(root, "log", "@{u}..HEAD", "--name-only", "--format=", check=False)
    if ahead.returncode != 0:
        return f"{done}; not pushed: the branch has no upstream"
    files = {name for name in ahead.stdout.splitlines() if name.strip()}
    if not files:
        return done
    if files != {LEDGER}:
        return f"{done}; not pushed: other commits are waiting to be pushed"
    result = git(root, "push", "-q", check=False)
    if result.returncode != 0:
        return f"{done}; push failed, the next run retries: {result.stderr.strip()[:200]}"
    return f"{done}; pushed"
