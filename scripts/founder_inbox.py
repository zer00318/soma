"""Founder -> Chief steer channel (the loop that makes the cockpit's steer box real).

The cockpit appends founder messages to ops/cockpit/inbox.jsonl (kind = steer | report_stuck).
The Chief DRAINS unacked messages at every step boundary and ACKs each one — the ack is the
green "Chief read this 14:32 -> switching to X" read-back the founder sees in the cockpit.
Without this loop the steer box is a write-only void.

CLI:
  python scripts/founder_inbox.py            # print unacked messages (for the Chief to read)
  python scripts/founder_inbox.py --count    # just the count (cheap poll)
  python scripts/founder_inbox.py ack <id> "note"   # acknowledge one message
"""
import json
import os
import sys
import time

CK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ops", "cockpit")
INBOX = os.path.join(CK, "inbox.jsonl")
ACK = os.path.join(CK, "inbox_ack.jsonl")


def _rows(path):
    out = []
    try:
        for line in open(path):
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return out


def drain():
    """Return inbox messages that have not been acked yet (newest last)."""
    acked = {a.get("id") for a in _rows(ACK) if a.get("ack")}
    return [m for m in _rows(INBOX) if m.get("id") and m["id"] not in acked]


def pending_count():
    return len(drain())


def ack(msg_id, note, acting=False):
    """Record that the Chief read (and is acting on) a message."""
    with open(ACK, "a") as f:
        f.write(json.dumps({"id": msg_id, "acting": acting,
                            "ack": {"ts": time.strftime("%H:%M"), "note": note[:300]}},
                           ensure_ascii=False) + "\n")


def main(argv):
    if argv and argv[0] == "--count":
        print(pending_count()); return 0
    if argv and argv[0] == "ack":
        if len(argv) < 3:
            print("usage: founder_inbox.py ack <id> \"note\""); return 2
        ack(argv[1], argv[2]); print("acked", argv[1]); return 0
    pend = drain()
    if not pend:
        print("(no unacked founder messages)"); return 0
    print("UNACKED FOUNDER MESSAGES (%d) — read + ack each:" % len(pend))
    for m in pend:
        print("  [%s] %s (%s): %s" % (m.get("id"), m.get("kind"), m.get("ts"), m.get("message")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
