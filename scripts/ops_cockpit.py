"""TRACE cockpit — the founder's window. HONEST, NEVER-DARK, SUPERVISED.

Serves ONE self-contained client (cockpit_client.html) plus a tiny JSON API:
  GET  /              -> the client (any non-/api path)
  GET  /api/state     -> merged snapshot of every ops/cockpit/* file + a SERVER CLOCK
                         (server_ts) and an HONEST liveness signal read from a single
                         dedicated heartbeat file (never nightly-file mtimes)
  GET  /api/access    -> {lan_url, localhost_url} so the founder always has a phone URL
  POST /api/steer     -> async interject / "you look stuck" -> ops/cockpit/inbox.jsonl
  POST /ask           -> live brain probe via ask_home (serialized; can't starve liveness)

Liveness is two ORTHOGONAL facts the window proves independently:
  1. SERVER reachable  -> proven by THIS response carrying a near-now server_ts.
  2. CHIEF working/idle/stopped -> read from ops/cockpit/heartbeat.json (cockpit_beat.py),
     classified against the Chief's OWN promised cadence (expected_next_s). A missing
     beat is "no data", never a fake 31-million-hour QUIET.

Stdlib only, dark, single screen. Process lifecycle is owned by a launchd LaunchAgent
(see ops/com.trace.cockpit.plist + scripts/install_cockpit_agent.sh), so the window
self-heals on any death and survives reboot/sleep. The product never keeps pixels, so
the cockpit shows none.
"""
import http.server
import json
import os
import random
import signal
import socket
import subprocess
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:
    import ask_home
except Exception:
    ask_home = None

REPO = os.path.dirname(_HERE)
CK = os.path.join(REPO, "ops", "cockpit")
WALKS = os.path.join(REPO, "data", "walks")
CLIENT_HTML = os.path.join(_HERE, "cockpit_client.html")
ACTIVE_CAPTURE = "day_in_life_20260618"  # the clip the live brain probe answers from
# Default 8788 (what the founder bookmarks); env override lets a preview/dev run on a
# scratch port without colliding with the supervised instance.
PORT = int(os.environ.get("COCKPIT_PORT") or os.environ.get("PORT") or 8788)
LOG = "/tmp/trace_cockpit.log"
PIDFILE = os.path.join(CK, "cockpit.pid")
ACCESS_TXT = os.path.join(CK, "access.txt")

# One heavy brain probe at a time — /ask must never starve the founder's only liveness
# signal by stacking gemma3:12b inferences on a 32GB box.
_ASK_LOCK = threading.Lock()


def _log(msg):
    """Timestamped lifecycle breadcrumb. launchd also captures stdout to LOG; we append
    directly too so manual runs leave the same trail. Never raises."""
    line = "%s  %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _lan_ip():
    """The LAN IPv4 a phone on the same Wi-Fi reaches this Mac by. No packet is sent
    (UDP connect just picks the route). Falls back to loopback if offline."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


LAN_IP = _lan_ip()
LAN_URL = "http://%s:%d" % (LAN_IP, PORT)
LOCAL_URL = "http://localhost:%d" % PORT


def _capture_dir():
    for slug in (ACTIVE_CAPTURE, "walk_outside_20260614", "home_capture_20260613"):
        p = os.path.join(WALKS, slug)
        if os.path.isdir(os.path.join(p, "memory")):
            return p
    return os.path.join(WALKS, ACTIVE_CAPTURE)


def _best_memory():
    mdir = os.path.join(_capture_dir(), "memory")
    for name in ("world_memory.json", "kf_memory.json", "memory_full.json", "memory.json"):
        p = os.path.join(mdir, name)
        if os.path.exists(p) and os.path.getsize(p) > 2:
            return p
    return os.path.join(mdir, "memory.json")


# --- defensive loaders ----------------------------------------------------- #
def read_json(name, default=None):
    # Retry once: a writer (run_live) updates these files non-atomically, so a read can
    # catch a 0-byte/partial file mid-write. A 60ms retry catches the completed write and
    # stops the cockpit flickering to empty panels.
    for attempt in (0, 1):
        try:
            with open(os.path.join(CK, name)) as f:
                return json.load(f)
        except Exception:
            if attempt == 0:
                time.sleep(0.06)
                continue
            return {} if default is None else default


def read_jsonl(name):
    rows = []
    try:
        for line in open(os.path.join(CK, name)):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return rows


def _age(name):
    """Seconds since CK/name was last modified; None if absent (never a 1e9 sentinel
    that the UI would render as a multi-thousand-hour lie)."""
    try:
        return round(time.time() - os.path.getmtime(os.path.join(CK, name)), 1)
    except Exception:
        return None


# cold = the new 'day in life' cross-clip test; walk = the original Garching walk.
CLIP_REGISTRY = [
    ("cold", "eval_live_cold.json", "critic_dil.json"),
    ("walk", "eval_live_walk.json", "critic.json"),
]


def _clip_stats(eval_file):
    d = read_json(eval_file, {})
    if not d:
        return None
    return {
        "correct": d.get("correct", 0), "wrong": d.get("wrong", 0),
        "miss": d.get("miss", 0), "total": d.get("total", 0),
        "hard_ras": d.get("hard_ras", 0.0), "halluc_pct": d.get("halluc_pct", 0.0),
        "state": d.get("state", "unknown"), "done": d.get("done", 0),
        "current_q": d.get("current_q"), "current_question": d.get("current_question"),
        "eta_human": d.get("eta_human"), "updated_epoch": d.get("updated_epoch"),
        "age_s": _age(eval_file),
    }


def _beat(server_ts):
    """The HONEST Chief-liveness signal, from the single-purpose heartbeat file only.
    Returns (beat_dict_or_None, beat_age_s_or_None). Never reads incidental data files."""
    hb = read_json("heartbeat.json", {})
    if not hb or "ts" not in hb:
        return None, None
    try:
        age = round(server_ts - float(hb["ts"]), 1)
    except Exception:
        return None, None
    return {
        "step": hb.get("step", ""),
        "by": hb.get("by", ""),
        "idle": bool(hb.get("idle", False)),
        "expected_next_s": int(hb.get("expected_next_s", 300) or 300),
        "pid": hb.get("pid"),
    }, age


def build_state():
    state = {}
    server_ts = time.time()
    state["server_ts"] = round(server_ts, 1)  # lets the client prove this reply is LIVE

    # HONEST liveness: a dedicated heartbeat file, not the mtime of nightly artifacts.
    beat, beat_age = _beat(server_ts)
    state["beat"] = beat
    state["beat_age_s"] = beat_age
    # Artifact freshness is NEUTRAL context ("newest update Nm ago"), never an alarm.
    data_ages = [a for a in (_age("status.json"), _age("eval_live_cold.json"),
                             _age("eval_live_walk.json"),
                             _age("critic_dil.json")) if a is not None]
    state["data_age_s"] = min(data_ages) if data_ages else None

    state["pitch"] = read_json("pitch_progress.json", {})  # founder's always-on prototype tracker
    state["plan"] = read_json("plan.json", {})
    state["status"] = read_json("status.json", {})
    state["asks"] = read_json("asks.json", {})

    clips, critic = {}, {}
    for key, eval_file, critic_file in CLIP_REGISTRY:
        s = _clip_stats(eval_file)
        if s:
            clips[key] = s
        c = read_json(critic_file, {})
        if c:
            critic[key] = {"state": c.get("state", "legacy"),
                           "verdict": c.get("verdict"), "model": c.get("model"),
                           "generated": c.get("generated"), "error": c.get("error"),
                           "age_s": _age(critic_file)}
    state["clips"] = clips
    state["critic"] = critic
    state["critic_any"] = next(iter(critic.values()), None)

    state["eval_live"] = {}

    state["diagnosis"] = {"summary": read_json("diagnosis_dil.json", {}).get("summary", {})}
    state["scoreboard"] = read_jsonl("scoreboard.jsonl")
    state["history"] = read_jsonl("progress_history.jsonl")

    # Founder thread + ack read-back (the loop that makes steering real).
    acks = {a.get("id"): a.get("ack") for a in read_jsonl("inbox_ack.jsonl") if a.get("id")}
    acting = {a.get("id") for a in read_jsonl("inbox_ack.jsonl") if a.get("acting")}
    inbox = []
    for m in read_jsonl("inbox.jsonl"):
        mid = m.get("id")
        inbox.append({**m, "ack": acks.get(mid), "acting": mid in acting})
    state["inbox"] = inbox[-12:]
    return state


def _append(name, obj):
    with open(os.path.join(CK, name), "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _stuck_snapshot(ts):
    """Capture the facts behind a 'you look stuck' report so the Chief reads the
    state, not just the feeling. Best-effort; never raises."""
    info = {"ts": ts, "logs": {}, "ages": {}}
    try:
        import glob
        for lg in sorted(glob.glob("/tmp/*.log"))[-8:]:
            try:
                info["logs"][os.path.basename(lg)] = "".join(
                    open(lg, errors="replace").readlines()[-40:])
            except Exception:
                pass
        for f in ("status.json", "eval_live.json", "heartbeat.json"):
            info["ages"][f] = _age(f)
        ps = subprocess.run(["pgrep", "-fl", "run_live|build_keyframe|ask_home|ollama"],
                            capture_output=True, text=True, timeout=5)
        info["procs"] = ps.stdout.strip()
    except Exception:
        pass
    try:
        json.dump(info, open(os.path.join(CK, "stuck_report_%s.json" % ts), "w"),
                  ensure_ascii=False, indent=2)
    except Exception:
        pass


class Cockpit(http.server.BaseHTTPRequestHandler):
    timeout = 15  # a half-open phone connection on flaky Wi-Fi can't pin a worker forever

    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        # no-store: a shipped client fix must reach the phone, never a cached broken copy;
        # and a stale body is always distinguishable from a fresh one via server_ts.
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        try:
            if self.path.startswith("/api/state"):
                return self._send(build_state())
            if self.path.startswith("/api/access"):
                return self._send({"lan_url": LAN_URL, "localhost_url": LOCAL_URL,
                                   "lan_ip": LAN_IP})
            # any other path -> the single-page client
            try:
                html_doc = open(CLIENT_HTML, encoding="utf-8").read()
            except Exception:
                html_doc = "<!DOCTYPE html><h1>cockpit client missing</h1><p>scripts/cockpit_client.html not found.</p>"
            return self._send(html_doc, "text/html; charset=utf-8")
        except Exception as exc:
            return self._send({"error": type(exc).__name__})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            n = max(0, min(n, 65536))  # clip absurd bodies before read
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            payload = {}
        try:
            if self.path.startswith("/api/steer"):
                msg = (payload.get("message") or "").strip()[:4000]
                kind = payload.get("kind") or "steer"
                if not msg:
                    return self._send({"ok": False, "error": "empty"})
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                mid = "f_%d_%04d" % (int(time.time()), random.randint(0, 9999))
                _append("inbox.jsonl", {"id": mid, "ts": ts, "kind": kind,
                                        "message": msg, "ack": None})
                _append("founder_notes.ndjson", {"ts": ts, "kind": kind, "message": msg})
                if kind == "report_stuck":
                    _stuck_snapshot(time.strftime("%Y%m%d_%H%M%S"))
                return self._send({"ok": True, "id": mid})
            if self.path.startswith("/ask"):
                q = (payload.get("question") or "").strip()
                if not q or ask_home is None:
                    return self._send({"answer": "Ask me anything about the captured day.", "scenes": []})
                # Serialize: one heavy probe at a time so /api/state stays fast and the
                # liveness signal is never held hostage by the founder's own click.
                if not _ASK_LOCK.acquire(blocking=False):
                    return self._send({"answer": "Brain busy with another question — try again in a moment.",
                                       "busy": True})
                try:
                    res = ask_home.ask(q, _best_memory())
                finally:
                    _ASK_LOCK.release()
                return self._send({"answer": res.get("answer", ""),
                                   "cited": "scenes" in res and bool(res.get("scenes"))})
            return self._send({"ok": False, "error": "unknown endpoint"})
        except Exception as exc:
            return self._send({"ok": False, "error": type(exc).__name__})


def _write_access():
    try:
        with open(ACCESS_TXT, "w") as f:
            f.write("TRACE cockpit — reachable URLs (regenerated every launch)\n")
            f.write("On this Mac : %s\n" % LOCAL_URL)
            f.write("On phone/LAN: %s   (phone must be on the same Wi-Fi as this Mac)\n" % LAN_URL)
            f.write("generated   : %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


def _on_signal(signum, _frame):
    _log("shutting down (signal %d)" % signum)
    try:
        os.remove(PIDFILE)
    except Exception:
        pass
    sys.exit(0)


def main():
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    try:
        srv = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Cockpit)
    except OSError as exc:
        # EADDRINUSE: a live owner already holds the port. Exit with a distinct code so
        # launchd's ThrottleInterval backs off instead of flapping on a traceback.
        _log("bind failed on :%d (%s) — another cockpit already owns the port" % (PORT, exc))
        sys.exit(3)
    try:
        with open(PIDFILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    _write_access()
    _log("TRACE cockpit UP  pid=%d  %s  |  %s (phone/LAN)" % (os.getpid(), LOCAL_URL, LAN_URL))
    try:
        srv.serve_forever()
    except Exception as exc:
        _log("serve_forever crashed: %s: %s" % (type(exc).__name__, exc))
        raise


if __name__ == "__main__":
    main()
