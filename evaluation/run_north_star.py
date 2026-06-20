#!/usr/bin/env python3
"""North-star eval: fraction of stored graph facts that are true and correctly attributed.

Runs labeled WhatsApp fixtures through the real importer into a throwaway DB,
reads back what the graph actually stored, and scores it against ground truth.

    python3 evaluation/run_north_star.py [--fixture cases.json] [--threshold 0.8] [--json]

Check kinds per expected contact:
    <key>                exact attribute value (e.g. "message_count": "3")
    <key>_prefix         attribute value startswith
    <key>_any            JSON-list/string attribute must contain EVERY substring
    <key>_none           attribute must contain NO listed substring (precision canaries)
Case-level:
    forbidden_contacts   labels that must NOT exist as entities (e.g. the user)

Exit code is non-zero when the aggregate score falls below --threshold, so this
can gate local-model tuning loops (e.g. the gemma commitment gate).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from soma_hub.crypto import EncryptedTextCodec
from soma_hub.graph import RelationalMemoryGraph
from soma_hub.importer import import_whatsapp

DEFAULT_CASES = [
    {
        "name": "1to1-commitment-direction",
        "user": "Pranav",
        "chats": {
            "_chat_alice.txt": (
                "12.5.2026, 09:15 - Alice Tester: Good morning, did you see the grant slides?\n"
                "12.5.2026, 09:17 - Alice Tester: I will send you the budget spreadsheet after our call\n"
                "12.5.2026, 09:20 - Pranav: I will finish the market analysis section for the application\n"
                "12.5.2026, 09:22 - Pranav: I will sleep no worries\n"
                "12.5.2026, 09:23 - Pranav: I will fix the office printer today\n"
                "12.5.2026, 09:24 - Pranav: I cleaned the meeting room already but will bring the projector cable over\n"
                "12.5.2026, 09:25 - Pranav: I will send you the venue address for the demo day\n"
                "12.5.2026, 11:40 - Pranav: Just sent the venue address to your email, see you there\n"
                "12.5.2026, 11:45 - Alice Tester: Got it, thanks!\n"
                "13.5.2026, 18:40 - Alice Tester: The meeting room is booked for Thursday afternoon\n"
            ),
        },
        "expected": {
            "Alice Tester": {
                "relationship_source": "whatsapp",
                "message_count": "4",
                "last_contact_at_prefix": "2026-05-13",
                "recent_topics_any": ["grant", "budget"],
                # Direction: my promise is open_commitments, hers is commitments_to_me.
                # Elided-subject promise ("...but will bring...") must be caught.
                "open_commitments_any": ["market analysis", "projector cable"],
                "commitments_to_me_any": ["budget spreadsheet"],
                # Precision canaries — banter must not become a commitment,
                # promises must never land on the wrong side, a promise the
                # later chat shows was fulfilled is no longer open, and a
                # short-horizon promise ("today") lapses after a week.
                "open_commitments_none": ["sleep no worries", "venue address", "printer"],
                "commitments_to_me_none": ["market analysis"],
            },
        },
        "forbidden_contacts": ["Pranav"],
    },
]


def _slot_value(profile: dict, key: str) -> str:
    slot = (profile.get("canonical_slots") or {}).get(key) or {}
    return str(slot.get("value") or "")


def _slot_source(profile: dict, key: str) -> str:
    slot = (profile.get("canonical_slots") or {}).get(key) or {}
    return str(slot.get("source") or "")


def run_case(case: dict) -> list[tuple[str, bool, str]]:
    """Returns a list of (fact_label, passed, detail)."""
    results: list[tuple[str, bool, str]] = []
    os.environ["SOMA_USER_NAME"] = case.get("user", "user").lower()
    os.environ["SOMA_COMMITMENT_WINDOW_DAYS"] = "36500"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db = tmp_path / "soma_hub.sqlite3"
        codec = EncryptedTextCodec(b"soma-eval-key-not-for-real-data!")
        graph = RelationalMemoryGraph(db, codec)
        for fname, content in case["chats"].items():
            chat = tmp_path / fname
            chat.write_text(content, encoding="utf-8")
            import_whatsapp(str(chat), str(db))

        profiles = {
            p.get("label", ""): p
            for p in graph.profiles(limit=500).get("profiles", [])
        }

        for label in case.get("forbidden_contacts", []):
            ok = label not in profiles
            results.append((f"no-entity:{label}", ok, "user leaked into graph" if not ok else ""))

        for label, checks in case.get("expected", {}).items():
            if label not in profiles:
                results.append((f"entity:{label}", False, "contact missing from graph"))
                continue
            results.append((f"entity:{label}", True, ""))
            p = profiles[label]
            for check, want in checks.items():
                if check.endswith("_prefix"):
                    key = check[: -len("_prefix")]
                    got = _slot_value(p, key)
                    ok = got.startswith(want)
                elif check.endswith("_any"):
                    key = check[: -len("_any")]
                    got = _slot_value(p, key).lower()
                    ok = all(s.lower() in got for s in want)
                elif check.endswith("_none"):
                    key = check[: -len("_none")]
                    got = _slot_value(p, key).lower()
                    ok = all(s.lower() not in got for s in want)
                else:
                    key = check
                    got = _slot_value(p, key)
                    ok = got == want
                detail = "" if ok else f"want={want!r} got={got[:120]!r}"
                results.append((f"{label}.{check}", ok, detail))
                # Attribution: every checked fact must cite its true source.
                if ok and not check.endswith("_none"):
                    src_ok = _slot_source(p, key) == "whatsapp"
                    if not src_ok:
                        results.append(
                            (f"{label}.{key}:attribution", False,
                             f"source={_slot_source(p, key)!r}")
                        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", help="JSON file with a list of cases (default: bundled)")
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    cases = DEFAULT_CASES
    if args.fixture:
        cases = json.loads(Path(args.fixture).read_text(encoding="utf-8"))

    all_results: list[tuple[str, str, bool, str]] = []
    for case in cases:
        for fact, ok, detail in run_case(case):
            all_results.append((case["name"], fact, ok, detail))

    passed = sum(1 for _, _, ok, _ in all_results if ok)
    total = len(all_results)
    score = passed / total if total else 0.0

    if args.json:
        print(json.dumps({
            "score": score, "passed": passed, "total": total,
            "failures": [
                {"case": c, "fact": f, "detail": d}
                for c, f, ok, d in all_results if not ok
            ],
        }, indent=2))
    else:
        for c, f, ok, d in all_results:
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {c} :: {f}" + (f"  ({d})" if d else ""))
        print(f"\nnorth-star score: {passed}/{total} = {score:.2f} (threshold {args.threshold})")

    return 0 if score >= args.threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
