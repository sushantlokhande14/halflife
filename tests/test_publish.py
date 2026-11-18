"""The daily publish: only a verified ledger is committed, and nothing else is touched."""

import json
import subprocess

import pytest

from halflife.ledger import Ledger
from halflife.publish import LEDGER, publish


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    """A working copy with one commit, pushed to a bare repository standing in for GitHub."""
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    git(work, "config", "user.email", "test@example.com")
    git(work, "config", "user.name", "Test")
    (work / "README.md").write_text("x\n", encoding="utf-8")
    git(work, "add", "README.md")
    git(work, "commit", "-q", "-m", "start")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "-u", "origin", "main")
    return work, remote, Ledger(work / LEDGER)


def test_new_entries_are_committed_alone_and_pushed(repo):
    work, remote, ledger = repo
    assert publish(work) == "no new entries"
    ledger.append("started", {"n": 1})
    ledger.append("prediction", {"p": 0.6})
    assert publish(work) == "committed 2 entries; pushed"
    assert git(work, "log", "-1", "--format=%s").startswith("Ledger: 2 entries, through ")
    assert git(work, "show", "--name-only", "--format=", "HEAD").split() == [LEDGER]
    assert git(remote, "rev-parse", "main") == git(work, "rev-parse", "HEAD")
    assert publish(work) == "no new entries"


def test_a_broken_chain_is_not_committed(repo):
    work, remote, ledger = repo
    ledger.append("started", {"n": 1})
    publish(work)
    entry = json.loads(ledger.path.read_text(encoding="utf-8").splitlines()[0])
    entry["payload"]["n"] = 2  # quietly change history
    ledger.path.write_text(json.dumps(entry, sort_keys=True) + "\n", encoding="utf-8")
    outcome = publish(work)
    assert outcome.startswith("not committed: entry 0: contents do not match its hash")
    assert git(work, "diff", "--cached", "--name-only") == ""  # nothing left staged
    assert git(work, "log", "-1", "--format=%s").startswith("Ledger: 1 entries")


def test_an_unfinished_last_line_is_not_committed(repo):
    work, remote, ledger = repo
    ledger.append("started", {"n": 1})
    with open(ledger.path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write('{"seq": 1, "kind": "pred')  # the runner caught mid-write
    assert publish(work).startswith("not committed: the last entry is incomplete")


def test_other_work_is_left_alone(repo):
    work, remote, ledger = repo
    (work / "notes.txt").write_text("draft\n", encoding="utf-8")
    git(work, "add", "notes.txt")
    ledger.append("started", {"n": 1})
    assert publish(work) == "not committed: other changes are staged (notes.txt)"
    assert git(work, "diff", "--cached", "--name-only").split() == ["notes.txt"]

    # An unpushed commit of someone else's work is not pushed along with the ledger.
    git(work, "commit", "-q", "-m", "notes")
    assert publish(work) == "committed 1 entries; not pushed: other commits are waiting to be pushed"
    assert git(remote, "log", "-1", "--format=%s", "main").strip() == "start"
