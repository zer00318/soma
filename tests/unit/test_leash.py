"""Unit tests for THE LEASH v1 (evaluation/leash.py, packet P03).

Synthetic mini-stores only (tmp_path) — these test the pure anti-tunnel machinery (domain
grouping, verdicts, THE YANK, history I/O, MERGED-line parsing). The reasoner answerability
sample is exercised live in the smoke run, not here (no GPU in CI)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from trace_memory.store import TraceMemoryStore  # noqa: E402
from evaluation import leash  # noqa: E402


def _store(tmp_path, rows):
    """rows: list of (helper_id, text, t_ms) -> mini store shaped like the hub writes them
    (helper identity in metadata['helper'], source is a pillar source)."""
    store = TraceMemoryStore(str(tmp_path / "leash.sqlite3"))
    for i, (helper, text, t_ms) in enumerate(rows):
        store.write_observation(
            text=text, t_ms=t_ms, source="phone_camera",
            provenance={"source": helper},
            metadata={"helper": helper, "helper_prompt": helper},
        )
    return store


# --- domain grouping / volumes ---------------------------------------------------------------

def test_helpers_map_to_correct_domains(tmp_path):
    store = _store(tmp_path, [
        ("detector", "OBJECT | mug", 1000),
        ("vlm_object", "a mug on a desk", 1100),
        ("ocr", "DEWALT 20V", 1200),
        ("asr", "call Marcus on Thursday", 1300),
    ])
    vols = leash.domain_volumes(store, day=None)
    assert vols["physical-objects"] == 2  # detector + vlm_object
    assert vols["text-in-world"] == 1     # ocr
    assert vols["speech/people"] == 1     # asr
    assert vols["digital/screen"] == 0
    assert vols["motion/place"] == 0
    assert vols["sound-events"] == 0
    store.close()


def test_unknown_helper_falls_to_other_never_crashes(tmp_path):
    store = _store(tmp_path, [
        ("kettle_watcher", "the kettle is boiling", 1000),  # unregistered helper
        ("detector", "OBJECT | mug", 1100),
    ])
    vols = leash.domain_volumes(store, day=None)
    assert vols["other"] == 1
    assert vols["physical-objects"] == 1
    store.close()


def test_day_fence(tmp_path):
    import datetime as _dt
    d1 = int(_dt.datetime(2026, 7, 1, 12, tzinfo=_dt.timezone.utc).timestamp() * 1000)
    d2 = int(_dt.datetime(2026, 7, 2, 12, tzinfo=_dt.timezone.utc).timestamp() * 1000)
    store = _store(tmp_path, [
        ("detector", "day one object", d1),
        ("detector", "day two object", d2),
        ("detector", "day two object 2", d2 + 5000),
    ])
    assert leash.domain_volumes(store, day="2026-07-01")["physical-objects"] == 1
    assert leash.domain_volumes(store, day="2026-07-02")["physical-objects"] == 2
    assert leash.domain_volumes(store, day=None)["physical-objects"] == 3
    store.close()


# --- verdicts (STARVED | THIN | FED) ---------------------------------------------------------

def test_starved_domain_is_flagged(tmp_path):
    # a store with only physical-objects: the other six domains must read STARVED
    store = _store(tmp_path, [("detector", "OBJECT | mug", 1000) for _ in range(50)])
    scored = leash.score_store(store, day=None, model="unused", do_answerability=False)
    ds = scored["domain_scores"]
    assert ds["physical-objects"]["verdict"] == "FED"       # volume-only, > THIN threshold
    for starved in ("text-in-world", "speech/people", "digital/screen",
                    "motion/place", "sound-events", "temporal"):
        assert ds[starved]["verdict"] == "STARVED", starved
    store.close()


def test_verdict_thresholds():
    # zero volume => STARVED regardless of answer_rate
    assert leash.verdict_for(0, 1.0) == "STARVED"
    # volume but no answers at all => STARVED (rows that surface nothing)
    assert leash.verdict_for(100, 0.0) == "STARVED"
    # sparse volume => THIN even with good answers
    assert leash.verdict_for(5, 1.0) == "THIN"
    # good volume but weak answers => THIN
    assert leash.verdict_for(100, 0.3) == "THIN"
    # good volume + good answers => FED
    assert leash.verdict_for(100, 0.9) == "FED"
    # degraded (answerability skipped): volume-only fallback
    assert leash.verdict_for(0, None) == "STARVED"
    assert leash.verdict_for(5, None) == "THIN"
    assert leash.verdict_for(100, None) == "FED"


# --- MERGED-line parsing ---------------------------------------------------------------------

def test_merged_packet_parsing(tmp_path):
    idx = tmp_path / "INDEX.md"
    idx.write_text(
        "| id | packet | status |\n"
        "| P01 | [x](P01.md) | MERGED (abc): done |\n"
        "| P02 | [y](P02.md) | MERGED 2026-07-04: done |\n"
        "| P03 | [z](P03.md) | READY — unblocked |\n"
        "| P04 | [w](P04.md) | merged: lowercase counts too |\n"
        "not a table row\n"
    )
    merged = leash._merged_packet_ids(idx)
    assert merged == ["P01", "P02", "P04"]


def test_merged_parsing_missing_index(tmp_path):
    assert leash._merged_packet_ids(tmp_path / "nope.md") == []


# --- history I/O -----------------------------------------------------------------------------

def test_history_roundtrip(tmp_path, monkeypatch):
    hist = tmp_path / "history.jsonl"
    monkeypatch.setattr(leash, "HISTORY_PATH", hist)
    rec = {"ts": "t", "domain_scores": {"physical-objects": {"volume": 5}}}
    leash.append_history(rec)
    leash.append_history({**rec, "ts": "t2"})
    back = leash.read_history()
    assert len(back) == 2
    assert back[0]["ts"] == "t"
    assert back[1]["ts"] == "t2"


def test_history_read_skips_corrupt_lines(tmp_path, monkeypatch):
    hist = tmp_path / "history.jsonl"
    hist.write_text('{"ts": "ok"}\nNOT JSON\n{"ts": "ok2"}\n')
    monkeypatch.setattr(leash, "HISTORY_PATH", hist)
    back = leash.read_history()
    assert [r["ts"] for r in back] == ["ok", "ok2"]


# --- THE YANK --------------------------------------------------------------------------------

def _sig(volume):
    return {"domain_scores": {"physical-objects": {"volume": volume, "answer_rate": None,
                                                   "refusal_rate": None}},
            "merged_packets": []}


def _index_with_merged(tmp_path, n):
    lines = ["| id | packet | status |"]
    for i in range(1, n + 1):
        lines.append(f"| P{i:02d} | [x](P{i:02d}.md) | MERGED (c{i}): done |")
    idx = tmp_path / "INDEX.md"
    idx.write_text("\n".join(lines) + "\n")
    return idx


def test_yank_not_armed_below_window(tmp_path):
    idx = _index_with_merged(tmp_path, 3)  # < LEASH_YANK_WINDOW
    history = [_sig(10), _sig(10)]
    stop, msg = leash.yank_check(history, idx)
    assert stop is False
    assert "not armed" in msg


def test_yank_fires_when_no_domain_moves(tmp_path):
    idx = _index_with_merged(tmp_path, leash.LEASH_YANK_WINDOW + 1)
    # window+1 identical history points => no movement across the window
    history = [_sig(10) for _ in range(leash.LEASH_YANK_WINDOW + 1)]
    stop, msg = leash.yank_check(history, idx)
    assert stop is True
    assert "NO domain number" in msg


def test_yank_slack_when_a_number_moved(tmp_path):
    idx = _index_with_merged(tmp_path, leash.LEASH_YANK_WINDOW + 1)
    history = [_sig(10) for _ in range(leash.LEASH_YANK_WINDOW)] + [_sig(42)]  # newest moved
    stop, msg = leash.yank_check(history, idx)
    assert stop is False
    assert "moved" in msg


def test_report_exit_code_yank(tmp_path, monkeypatch):
    # wire the module globals so --report reads our synthetic history + index, then assert exit 2
    hist = tmp_path / "history.jsonl"
    with hist.open("w") as fh:
        for _ in range(leash.LEASH_YANK_WINDOW + 1):
            fh.write(json.dumps(_sig(10)) + "\n")
    monkeypatch.setattr(leash, "HISTORY_PATH", hist)
    monkeypatch.setattr(leash, "INDEX_PATH", _index_with_merged(tmp_path, leash.LEASH_YANK_WINDOW + 1))
    assert leash.main(["--report"]) == 2


def test_report_exit_code_slack(tmp_path, monkeypatch):
    hist = tmp_path / "history.jsonl"
    monkeypatch.setattr(leash, "HISTORY_PATH", hist)
    monkeypatch.setattr(leash, "INDEX_PATH", _index_with_merged(tmp_path, 2))  # below window
    hist.write_text(json.dumps(_sig(10)) + "\n")
    assert leash.main(["--report"]) == 0


# --- score_store degraded mode (no reasoner) -------------------------------------------------

def test_score_store_degraded_marks_skipped(tmp_path):
    store = _store(tmp_path, [("detector", "OBJECT | mug", 1000)])
    scored = leash.score_store(store, day=None, model="unused", do_answerability=False)
    assert scored["answerability_skipped"] is True
    assert scored["domain_scores"]["physical-objects"]["answer_rate"] is None
    store.close()
