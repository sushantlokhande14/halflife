import json

from halflife.ledger import Ledger, verify


def write(path, entries):
    path.write_text("".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries), encoding="utf-8")


def test_an_intact_chain_verifies(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    for i in range(5):
        ledger.append("prediction", {"ticker": f"T{i}", "p": 0.5 + i / 100})
    assert verify(ledger.path) == []
    entries = ledger.entries()
    assert [e["seq"] for e in entries] == [0, 1, 2, 3, 4]
    assert all(entries[i]["prev"] == entries[i - 1]["hash"] for i in range(1, 5))


def test_editing_an_old_prediction_is_detected(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    for i in range(4):
        ledger.append("prediction", {"ticker": f"T{i}", "p": 0.4})
    entries = ledger.entries()
    entries[1]["payload"]["p"] = 0.9  # quietly improve a past call
    write(ledger.path, entries)
    assert any("entry 1" in problem and "hash" in problem for problem in verify(ledger.path))


def test_editing_and_rehashing_one_entry_still_breaks_the_chain(tmp_path):
    from halflife.ledger import digest

    ledger = Ledger(tmp_path / "ledger.jsonl")
    for i in range(4):
        ledger.append("prediction", {"ticker": f"T{i}", "p": 0.4})
    entries = ledger.entries()
    entries[1]["payload"]["p"] = 0.9
    body = {key: entries[1][key] for key in ("seq", "recorded_at", "kind", "payload", "prev")}
    entries[1]["hash"] = digest(body)  # a careful forger recomputes this entry's hash...
    write(ledger.path, entries)
    # ...but the next entry still points at the old one.
    assert any("entry 2" in problem and "follow" in problem for problem in verify(ledger.path))


def test_deleting_or_reordering_entries_is_detected(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    for i in range(4):
        ledger.append("prediction", {"ticker": f"T{i}"})
    entries = ledger.entries()
    write(ledger.path, entries[:1] + entries[2:])  # a losing call removed
    assert verify(ledger.path)
    write(ledger.path, [entries[0], entries[2], entries[1], entries[3]])
    assert verify(ledger.path)


def test_a_restart_with_new_models_is_recorded_once(tmp_path):
    from halflife.live import model_change

    ledger = Ledger(tmp_path / "ledger.jsonl")
    v1 = {"models": {"ten_minutes": "aaa", "at_open": "bbb"}, "policy_version": 1}
    v2 = {"models": {"ten_minutes": "ccc", "at_open": "ddd"}, "policy_version": 2}
    assert model_change(ledger.entries(), v1) is None  # nothing started yet: the start entry says it
    ledger.append("started", {"ignored_earlier_filings": 3, **v1})
    assert model_change(ledger.entries(), v1) is None  # same models: nothing to record
    change = model_change(ledger.entries(), v2)
    assert change == {**v2, "replaces": v1}
    ledger.append("models changed", change)
    assert model_change(ledger.entries(), v2) is None  # recorded once, not on every restart
