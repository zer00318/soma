#!/usr/bin/env python3
"""SOMA felt-moment demo: import personal data, then ask it real questions.

Two modes:

  Fixture demo (no arguments) — builds a throwaway DB from a bundled
  WhatsApp + calendar fixture, then runs the investor query sequence:

      python3 scripts/demo_felt_moment.py

  Real data — point at an existing hub DB (uses the production key from
  SOMA_HUB_KEY or <db dir>/.soma_hub_key) and optionally name a person:

      python3 scripts/demo_felt_moment.py --db data/soma_hub.sqlite3 --person "Maria"

Every answer is printed with its provenance (source, timestamp, confidence)
to show recall is sealed: graph-grounded, cited, never a raw-log dump.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from soma_hub.crypto import EncryptedTextCodec
from soma_hub.graph import RelationalMemoryGraph
from soma_hub.importer import import_ics, import_whatsapp
from soma_hub.recall import RecallFirewall
from soma_hub.storage import MemoryStore

# Realistic shape: one export file per 1:1 chat (group chats drop the
# user's own commitments because the addressee is ambiguous).
_FIXTURE_CHATS = {
    "_chat_maria.txt": """\
12.5.2026, 09:15 - Maria Keller: Good morning! Did you get the EXIST grant slides finished?
12.5.2026, 09:17 - Maria Keller: I will send you the budget spreadsheet after our call
12.5.2026, 09:20 - Pranav: I will finish the market analysis section for the application
14.5.2026, 18:40 - Maria Keller: The TUM meeting room is booked for Thursday afternoon
14.5.2026, 18:42 - Maria Keller: Looking forward to the demo presentation session
2.6.2026, 13:11 - Maria Keller: Reviewer feedback is in, mostly positive on the privacy section
""",
    "_chat_jonas.txt": """\
20.5.2026, 11:02 - Jonas Brandt: Hey, are we still on for climbing this weekend?
20.5.2026, 11:05 - Pranav: I'll bring the rope and quickdraws on Saturday morning
27.5.2026, 16:30 - Jonas Brandt: I can pick you up at the Garching U-Bahn at nine
""",
}

_FIXTURE_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//SOMA demo//EN
BEGIN:VEVENT
UID:demo-grant-review@soma
DTSTART:20260612T140000Z
DTEND:20260612T150000Z
SUMMARY:EXIST grant review with Maria Keller
LOCATION:TUM Garching, room 5604
DESCRIPTION:Walk through budget spreadsheet and privacy section feedback
END:VEVENT
END:VCALENDAR
"""

_QUERY_SEQUENCE = [
    "what are my commitments?",
    "who is {person}?",
    "when did I last talk to {person}?",
    "when did I last contact someone?",
]


def _print_answer(query: str, result: dict) -> None:
    print(f"\n\033[1m> {query}\033[0m")
    print(f"  {result.get('answer', '(no answer)')}")
    confidence = result.get("confidence")
    if confidence is not None:
        print(f"  confidence: {confidence:.2f}")
    citations = result.get("citations") or []
    if not citations:
        print("  citations: none")
        return
    for c in citations:
        attrs = ", ".join(c.get("attributes") or [])
        when = (c.get("captured_at") or "")[:16] or "unknown time"
        print(
            f"  └ source={c.get('source', '?')}  at={when}  "
            f"conf={c.get('confidence', 0):.2f}  facts=[{attrs}]"
        )


def run_sequence(recall: RecallFirewall, person: str) -> None:
    for template in _QUERY_SEQUENCE:
        query = template.format(person=person)
        _print_answer(query, recall.answer(query))
    print()


def show_facts(graph: RelationalMemoryGraph, person: str) -> None:
    """Dump the raw stored facts for a person — the audit view.

    Everything recall is allowed to say comes from these slots; if a fact is
    wrong here, the importer is at fault, not the answer layer.
    """
    result = graph.profiles(label=person, limit=5)
    profiles = result.get("profiles", [])
    if not profiles:
        print(f"No entity matching {person!r}.")
        return
    for p in profiles:
        print(f"\n\033[1m{p.get('label')}\033[0m  status={p.get('status')}  id={p.get('id', '')[:8]}")
        cs = p.get("canonical_slots") or {}
        for key in sorted(cs):
            slot = cs[key]
            print(f"  {key:22} {str(slot.get('value'))[:110]!r}")
            print(
                f"  {'':22} source={slot.get('source')}  "
                f"observed={str(slot.get('last_seen_at'))[:16]}  conf={slot.get('confidence')}"
            )
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="existing hub DB (default: throwaway fixture demo)")
    parser.add_argument("--person", help="person to ask about (fixture default: Maria Keller)")
    parser.add_argument(
        "--facts", action="store_true",
        help="dump the raw stored facts for --person instead of recall answers",
    )
    args = parser.parse_args()

    if args.db:
        db = Path(args.db)
        if not db.exists():
            print(f"DB not found: {db}", file=sys.stderr)
            return 1
        codec = EncryptedTextCodec.from_env_or_file(db.parent)
        graph = RelationalMemoryGraph(db, codec)
        if args.facts:
            show_facts(graph, args.person or "")
            return 0
        recall = RecallFirewall(MemoryStore(db, codec), graph)
        person = args.person or "someone"
        print(f"SOMA recall on {db} — asking about: {person}")
        run_sequence(recall, person)
        return 0

    # Fixture dates are fixed; pin the commitment window so the demo
    # keeps working as the fixture ages.
    os.environ.setdefault("SOMA_COMMITMENT_WINDOW_DAYS", "36500")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db = tmp_path / "soma_hub.sqlite3"
        ics = tmp_path / "calendar.ics"
        ics.write_text(_FIXTURE_ICS, encoding="utf-8")

        codec = EncryptedTextCodec(b"soma-demo-key-not-for-real-data!")
        graph = RelationalMemoryGraph(db, codec)  # creates schema
        for name, content in _FIXTURE_CHATS.items():
            chat = tmp_path / name
            chat.write_text(content, encoding="utf-8")
            wa = import_whatsapp(str(chat), str(db))
            print(f"Imported {name}: {wa}")
        cal = import_ics(str(ics), str(db))
        print(f"Imported calendar: {cal}")

        recall = RecallFirewall(MemoryStore(db, codec), graph)
        run_sequence(recall, args.person or "Maria Keller")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
