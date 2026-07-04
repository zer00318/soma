#!/usr/bin/env python3
"""THE LEASH v1 (ops/CANONICAL_SPEC.md §6, packet P03) — the objective anti-tunnel evaluator.

The canonical battery (evaluation/run_canonical_battery.py) is THE merge gate. The Leash is a
SEPARATE PROGRESS instrument: it scores real captured days per LIFE DOMAIN and makes channel
starvation visible, so the team can never again spend weeks inside one perception channel while
the others starve.

For a store (default the real data/trace_store.sqlite3) and a day (or --all) it computes, per
life domain:
  * observation VOLUME — rows tagged to that domain's helper_id class,
  * an ANSWERABILITY sample — N fixed STRUCTURAL template questions asked against the real store
    through the REAL agent + local reasoner (a domain with rows but no answers is not fed),
  * REFUSAL honesty — a structural absent-probe that MUST be refused,
  * a coverage VERDICT — STARVED | THIN | FED (thresholds in ONE constants block below).

Every run appends one JSON line to evaluation/leash_history.jsonl so the trend is data, not vibes.

    .venv/bin/python evaluation/leash.py [--store data/trace_store.sqlite3] [--day YYYY-MM-DD | --all]
    .venv/bin/python evaluation/leash.py --report      # trend table + THE YANK

THE YANK (--report): if the last LEASH_YANK_WINDOW merged packets (ops/packets/INDEX.md MERGED
lines) moved NO domain number, print "LEASH: STOP — reassess with founder" and exit 2.

LAWS: L2 (report honestly — ollama down => answerability SKIPPED, never faked), L6. The Leash
reads the store; it NEVER mutates it. It is NOT a merge gate (§7's gate stays the battery).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from trace_memory.store import TraceMemoryStore  # noqa: E402
from trace_memory.brain import TraceMemoryAgent  # noqa: E402

# --- constants block (documented thresholds — one place to tune the instrument) --------------

DEFAULT_STORE = ROOT / "data" / "trace_store.sqlite3"
HISTORY_PATH = ROOT / "evaluation" / "leash_history.jsonl"
INDEX_PATH = ROOT / "ops" / "packets" / "INDEX.md"

# The pillar `source` values the Leash reads (spec §5 / contract.PILLAR_SOURCES). Observations
# live under these; everything else in the store (dev noise) is ignored.
LEASH_SOURCES = ("phone_camera", "mac_screen", "owner")

# helper_id -> life domain. This is the ONLY place the seven domains are defined. Grouping keys
# off helper_id (metadata['helper'] / helper_type column), NOT off row content (law L5: no
# room-specific nouns anywhere in this instrument). Unknown/unregistered helper_ids fall to
# 'other' and are counted, never crashed on.
DOMAIN_OF_HELPER: Dict[str, str] = {
    "detector": "physical-objects",
    "vlm_object": "physical-objects",
    "ocr": "text-in-world",
    "asr": "speech/people",
    "mac_screen_ocr": "digital/screen",
    "mac_app_focus": "digital/screen",
    "motion_activity": "motion/place",
    "sound_event": "sound-events",
    # activity_context / barcode / owner etc. are fused/meta helpers, not a raw life domain;
    # they land in 'other' by omission and still surface in the volume report.
}

# temporal is a DERIVED domain — it has no raw helper, only an answerability probe over whatever
# else is captured (before/after ordering across the day). Listed here so it always appears.
DERIVED_DOMAINS = ("temporal",)

DOMAINS: Tuple[str, ...] = (
    "physical-objects",
    "text-in-world",
    "speech/people",
    "digital/screen",
    "motion/place",
    "sound-events",
    "temporal",
)

# Coverage verdict thresholds (documented):
#   STARVED — the domain is not being captured (or answers nothing): raise the alarm.
#   THIN    — some capture, but recall is weak; keep feeding it.
#   FED     — enough volume AND the sample answers: this domain is healthy.
STARVED_MAX_VOLUME = 0            # volume <= this  -> STARVED (no rows at all)
THIN_MAX_VOLUME = 10             # volume <= this  -> at best THIN (sparse capture)
FED_MIN_ANSWER_RATE = 0.5        # answerability sample correct-fraction to reach FED
THIN_MIN_ANSWER_RATE = 0.01      # any correct answer lifts a volumed domain off STARVED

# THE YANK window: N most-recent merged packets that must have moved a number.
LEASH_YANK_WINDOW = 5

OLLAMA_HOST = "http://127.0.0.1:11434"
OLLAMA_MODEL = "gemma3:12b-it-qat"

# --- structural template questions (law L5: helper-class phrasing, no room-specific nouns) ----
# Each domain gets fixed template questions asked against the WHOLE store. `present` questions
# probe whether that domain's captured signal is answerable; `absent` probes an impossible thing
# the domain would have surfaced if fed — it MUST be refused (refusal honesty).

DOMAIN_TEMPLATES: Dict[str, Dict[str, List[str]]] = {
    "physical-objects": {
        "present": ["what objects did you see", "what things were around me"],
        "absent": ["how many unicorns did you see"],
    },
    "text-in-world": {
        "present": ["what text did you read", "what words were written on things"],
        "absent": ["what did the sign about the emerald dragon say"],
    },
    "speech/people": {
        "present": ["what did anyone say", "what was said out loud"],
        "absent": ["what did the astronaut say to me"],
    },
    "digital/screen": {
        "present": ["what was on my screen", "what app was I using"],
        "absent": ["what did the screen say about the moon landing contract"],
    },
    "motion/place": {
        "present": ["was I moving or still", "what was I doing"],
        "absent": ["when did I go scuba diving"],
    },
    "sound-events": {
        "present": ["what sounds did you hear", "were there any ambient sounds"],
        "absent": ["when did the fire alarm go off"],
    },
    "temporal": {
        "present": ["what happened first", "what happened earlier"],
        "absent": ["what happened in the year 3000"],
    },
}

# Cues that mark an honest refusal / absence acknowledgement (mirrors the battery judge, kept
# structural — no domain nouns).
_ABSENT_CUES = ("no ", "not ", "n't", "none", "never", "does not", "didn't", "no mention",
                "nothing", "wasn't", "weren't", "cannot", "can't", "no record", "no prior",
                "unable", "don't have", "do not have", "no evidence", "unknown")


# --- store reading (read-only; never mutates) -----------------------------------------------

def _helper_of(node) -> str:
    md = node.metadata or {}
    return str(md.get("helper") or node.helper_type or "untagged")


def _day_of(t_ms: int) -> str:
    return _dt.datetime.utcfromtimestamp(t_ms / 1000).date().isoformat()


def domain_volumes(store: TraceMemoryStore, day: Optional[str]) -> Dict[str, int]:
    """Rows per life domain (optionally fenced to one UTC day). Unknown helpers -> 'other'."""
    vols: Dict[str, int] = {d: 0 for d in DOMAINS}
    vols["other"] = 0
    for node in store.nodes(node_types=("observation",), sources=LEASH_SOURCES):
        if day is not None and _day_of(node.t_ms) != day:
            continue
        helper = _helper_of(node)
        domain = DOMAIN_OF_HELPER.get(helper, "other")
        vols[domain] = vols.get(domain, 0) + 1
    return vols


def captured_days(store: TraceMemoryStore) -> List[str]:
    days = sorted({_day_of(n.t_ms) for n in
                   store.nodes(node_types=("observation",), sources=LEASH_SOURCES)})
    return days


# --- answerability sample (REAL agent + local reasoner) -------------------------------------

def _is_absent_honest(answer: str, refused: bool) -> bool:
    if refused:
        return True
    low = f" {(answer or '').lower()} "
    return any(cue in low for cue in _ABSENT_CUES)


def _is_present_answered(answer: str, refused: bool) -> bool:
    # A present-probe "counts" when the agent gave a grounded, non-refusing answer that isn't
    # itself an absence statement. Structural only — we do not check content correctness (that
    # is the battery's job); the Leash measures whether the domain SURFACES anything at all.
    if refused:
        return False
    return not _is_absent_honest(answer, refused)


def answerability(store: TraceMemoryStore, model: str) -> Tuple[Optional[Dict[str, Dict[str, Any]]], Optional[str]]:
    """Ask the fixed templates through the PRODUCTION reasoner path. Returns (per-domain scores,
    None) or (None, skip_reason) if the reasoner is unreachable — never fakes numbers (L2)."""
    reachable, why = _ollama_reachable(model)
    if not reachable:
        return None, why
    agent = TraceMemoryAgent(store, reasoner="local-ollama", ollama_model=model,
                             ollama_host=OLLAMA_HOST, restrict_sources=LEASH_SOURCES)
    scores: Dict[str, Dict[str, Any]] = {}
    for domain in DOMAINS:
        tpl = DOMAIN_TEMPLATES[domain]
        present_hits = 0
        for q in tpl["present"]:
            a = agent.answer(q)
            if _is_present_answered(a.answer, a.refused):
                present_hits += 1
        n_present = max(1, len(tpl["present"]))
        refusal_hits = 0
        for q in tpl["absent"]:
            a = agent.answer(q)
            if _is_absent_honest(a.answer, a.refused):
                refusal_hits += 1
        n_absent = max(1, len(tpl["absent"]))
        scores[domain] = {
            "answer_rate": round(present_hits / n_present, 3),
            "refusal_rate": round(refusal_hits / n_absent, 3),
            "n_present": len(tpl["present"]),
            "n_absent": len(tpl["absent"]),
        }
    return scores, None


def _ollama_reachable(model: str) -> Tuple[bool, Optional[str]]:
    import urllib.error
    import urllib.request
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, f"ollama unreachable ({exc})"
    names = {m.get("name", "") for m in data.get("models", [])}
    stems = {n.split(":")[0] for n in names}
    if model in names or model.split(":")[0] in stems:
        return True, None
    return False, f"model {model!r} not pulled (have: {sorted(names)})"


# --- verdicts --------------------------------------------------------------------------------

def verdict_for(volume: int, answer_rate: Optional[float]) -> str:
    """STARVED | THIN | FED from volume + (optional) answerability. When answerability is
    SKIPPED (ollama down), fall back to volume-only so the report still means something."""
    if volume <= STARVED_MAX_VOLUME:
        return "STARVED"
    if answer_rate is None:  # volume-only degraded mode
        return "FED" if volume > THIN_MAX_VOLUME else "THIN"
    if answer_rate < THIN_MIN_ANSWER_RATE:
        return "STARVED"
    if volume <= THIN_MAX_VOLUME or answer_rate < FED_MIN_ANSWER_RATE:
        return "THIN"
    return "FED"


def score_store(store: TraceMemoryStore, day: Optional[str], model: str,
                do_answerability: bool = True) -> Dict[str, Any]:
    vols = domain_volumes(store, day)
    ans: Optional[Dict[str, Dict[str, Any]]] = None
    skip_reason: Optional[str] = None
    if do_answerability:
        ans, skip_reason = answerability(store, model)
    else:
        skip_reason = "answerability disabled (--no-answerability)"

    domain_scores: Dict[str, Any] = {}
    for domain in DOMAINS:
        vol = int(vols.get(domain, 0))
        a = ans.get(domain) if ans else None
        rate = a["answer_rate"] if a else None
        domain_scores[domain] = {
            "volume": vol,
            "answer_rate": rate,
            "refusal_rate": (a["refusal_rate"] if a else None),
            "verdict": verdict_for(vol, rate),
        }
    return {
        "domain_scores": domain_scores,
        "other_volume": int(vols.get("other", 0)),
        "answerability_skipped": ans is None,
        "answerability_skip_reason": skip_reason,
    }


# --- history + THE YANK ----------------------------------------------------------------------

def _merged_packet_ids(index_path: Path) -> List[str]:
    """Packet ids whose INDEX row status starts with MERGED, in file (roughly chronological)
    order. Robust to spacing — a MERGED line is `| Pxx | ... | MERGED... |`."""
    if not index_path.exists():
        return []
    ids: List[str] = []
    for line in index_path.read_text().splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        pid, status = cells[0], cells[-1]
        if pid.startswith("P") and pid[1:].isdigit() and status.upper().startswith("MERGED"):
            ids.append(pid)
    return ids


def _domain_number_signature(record: Dict[str, Any]) -> Dict[str, Any]:
    """The comparable per-domain numbers (volume + answer_rate) that a packet must move."""
    sig: Dict[str, Any] = {}
    for domain, s in record.get("domain_scores", {}).items():
        sig[domain] = (s.get("volume"), s.get("answer_rate"), s.get("refusal_rate"))
    return sig


def read_history() -> List[Dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in HISTORY_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def append_history(record: Dict[str, Any]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def yank_check(history: List[Dict[str, Any]], index_path: Path) -> Tuple[bool, str]:
    """THE YANK: if the last LEASH_YANK_WINDOW merged packets moved NO domain number, the plan
    must be reassessed with the founder. Returns (should_stop, human_message).

    Mechanics: compare the newest history signature against the signature from
    LEASH_YANK_WINDOW+1 runs ago. If we don't yet have that many merged packets OR that many
    history points, we cannot have "5 merges with no movement" — do not yank."""
    merged = _merged_packet_ids(index_path)
    if len(merged) < LEASH_YANK_WINDOW:
        return False, (f"only {len(merged)} merged packet(s) < window {LEASH_YANK_WINDOW}; "
                       "yank not armed")
    if len(history) < 2:
        return False, "not enough leash history to judge movement; yank not armed"

    latest = _domain_number_signature(history[-1])
    # baseline = the run recorded before the last window of movement opportunity
    baseline_idx = max(0, len(history) - 1 - LEASH_YANK_WINDOW)
    baseline = _domain_number_signature(history[baseline_idx])
    moved = latest != baseline
    if moved:
        return False, "a domain number moved within the window; leash slack"
    return True, (f"last {LEASH_YANK_WINDOW} merged packets moved NO domain number "
                  f"(baseline run @ index {baseline_idx})")


# --- reporting -------------------------------------------------------------------------------

def _fmt_rate(r: Optional[float]) -> str:
    return "  n/a" if r is None else f"{r:5.2f}"


def print_scores(store_label: str, day_label: str, scored: Dict[str, Any]) -> None:
    print(f"\n=== THE LEASH (§6) · store={store_label} · day={day_label} ===")
    if scored["answerability_skipped"]:
        print(f"  answerability: SKIPPED — {scored['answerability_skip_reason']} "
              "(volume + verdict below; no faked numbers, L2)")
    print(f"  {'domain':<17} {'volume':>7} {'answer':>7} {'refuse':>7}  verdict")
    for domain in DOMAINS:
        s = scored["domain_scores"][domain]
        print(f"  {domain:<17} {s['volume']:>7} {_fmt_rate(s['answer_rate']):>7} "
              f"{_fmt_rate(s['refusal_rate']):>7}  {s['verdict']}")
    if scored["other_volume"]:
        print(f"  ({scored['other_volume']} row(s) under unregistered/meta helpers -> 'other')")


def print_trend(history: List[Dict[str, Any]]) -> None:
    print("\n=== LEASH TREND (volume per domain, oldest -> newest) ===")
    if not history:
        print("  (no history yet — run the leash once to seed it)")
        return
    tail = history[-10:]
    header = "  " + "ts".ljust(20) + "".join(d[:6].rjust(8) for d in DOMAINS)
    print(header)
    for rec in tail:
        ts = str(rec.get("ts", ""))[:19]
        cells = "".join(
            str(rec.get("domain_scores", {}).get(d, {}).get("volume", "-")).rjust(8)
            for d in DOMAINS
        )
        print("  " + ts.ljust(20) + cells)


# --- CLI -------------------------------------------------------------------------------------

def run_once(store_path: Path, day: Optional[str], model: str,
             do_answerability: bool) -> Dict[str, Any]:
    store = TraceMemoryStore(store_path)
    try:
        merged = _merged_packet_ids(INDEX_PATH)
        prev = read_history()
        packets_since_last_move = _packets_since_last_move(prev, merged)
        scored = score_store(store, day, model, do_answerability=do_answerability)
        record = {
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "store": str(store_path),
            "day": day or "ALL",
            "domain_scores": scored["domain_scores"],
            "other_volume": scored["other_volume"],
            "answerability_skipped": scored["answerability_skipped"],
            "answerability_skip_reason": scored["answerability_skip_reason"],
            "merged_packets": merged,
            "packets_since_last_move": packets_since_last_move,
        }
        append_history(record)
        print_scores(str(store_path), day or "ALL", scored)
        return record
    finally:
        store.close()


def _packets_since_last_move(history: List[Dict[str, Any]], merged: List[str]) -> int:
    """How many merged packets have landed since the last leash run whose domain numbers
    differed from its predecessor. Informational field for the history line."""
    if not history:
        return len(merged)
    # find most recent history record that moved vs its predecessor
    last_move_merged: Optional[List[str]] = None
    for i in range(len(history) - 1, 0, -1):
        if _domain_number_signature(history[i]) != _domain_number_signature(history[i - 1]):
            last_move_merged = history[i].get("merged_packets", [])
            break
    if last_move_merged is None:
        # never moved in recorded history
        last_move_merged = history[0].get("merged_packets", [])
    return max(0, len(merged) - len(last_move_merged))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="The Leash v1 — objective anti-tunnel evaluator (§6)")
    ap.add_argument("--store", default=str(DEFAULT_STORE), help="store sqlite path (read-only)")
    ap.add_argument("--day", default=None, help="UTC day YYYY-MM-DD to fence to")
    ap.add_argument("--all", action="store_true", help="score all captured days together")
    ap.add_argument("--report", action="store_true",
                    help="print trend table + THE YANK (exit 2 if the leash yanks)")
    ap.add_argument("--model", default=OLLAMA_MODEL)
    ap.add_argument("--no-answerability", action="store_true",
                    help="skip the reasoner sample (volume + verdict only)")
    args = ap.parse_args(argv)

    store_path = Path(args.store)

    if args.report:
        history = read_history()
        print_trend(history)
        should_stop, msg = yank_check(history, INDEX_PATH)
        print(f"\n  yank: {msg}")
        if should_stop:
            print("\nLEASH: STOP — reassess with founder")
            return 2
        print("\nLEASH: slack — keep going")
        return 0

    if not store_path.exists():
        print(f"[leash] store not found: {store_path}", file=sys.stderr)
        return 1

    day: Optional[str] = None
    if not args.all:
        day = args.day  # None => whole store when neither --day nor --all given

    run_once(store_path, day, args.model, do_answerability=not args.no_answerability)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
