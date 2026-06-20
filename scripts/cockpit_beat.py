"""TRACE cockpit heartbeat — the ONE file whose only job is to prove the Chief is alive.

The cockpit reads liveness ONLY from ops/cockpit/heartbeat.json (never from the mtime
of nightly data files — that was the old lie that showed "QUIET" all afternoon). Write
this at the top of every work step so the founder's window can tell, honestly:

    from cockpit_beat import beat
    beat("scoring Q3/12", expected_next_s=120)        # WORKING (green)
    beat("waiting for next step", 1800, idle=True)    # IDLE (blue, NOT an alarm)

If the beat goes older than expected_next_s with no new write, the cockpit shows
"Chief STOPPED" — an honest, self-declared deadline, not a guessed threshold. A missing
file shows "no check-in yet", never a 31-million-hour reading. Atomic write so a reader
never sees a half-written file. Importable, and a CLI: `python3 cockpit_beat.py "<step>" [secs]`.
"""
import json
import os
import time

CK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ops", "cockpit")
BEAT = os.path.join(CK, "heartbeat.json")


def beat(step, expected_next_s=300, by="chief", idle=False):
    """Atomically stamp the heartbeat. Best-effort; never raises into the caller."""
    obj = {
        "ts": round(time.time(), 1),
        "by": str(by)[:40],
        "step": str(step)[:200],
        "idle": bool(idle),
        "expected_next_s": int(expected_next_s),
        "pid": os.getpid(),
    }
    try:
        os.makedirs(CK, exist_ok=True)
        tmp = BEAT + ".tmp"
        with open(tmp, "w") as f:
            json.dump(obj, f)
        os.replace(tmp, BEAT)
    except Exception:
        pass
    return obj


if __name__ == "__main__":
    import sys
    step = sys.argv[1] if len(sys.argv) > 1 else "manual check-in"
    exp = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    idle = "--idle" in sys.argv
    print(beat(step, exp, idle=idle))
