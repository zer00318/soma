#!/usr/bin/env python3
"""Cockpit ENGINE — computes the hard, decision-grade system state into one JSON.

This replaces the narrative chief.json fluff. Every field here is a number or a
machine-readable fact a founder needs at a glance to (a) decide pitch-readiness and
(b) debug. Fields we cannot HONESTLY measure yet are emitted with value=null and
status="UNINSTRUMENTED" plus the instrument plan — we never fake a metric.

  .venv/bin/python scripts/cockpit_engine.py            # write ops/cockpit/engine.json
  .venv/bin/python scripts/cockpit_engine.py --print    # also print a terminal view
"""
import argparse
import datetime
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "ops" / "cockpit"


def sh(*a):
    try:
        return subprocess.check_output(a, cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def read_json(p, default=None):
    try:
        return json.load(open(p))
    except Exception:
        return default


def git_state():
    return {
        "branch": sh("git", "rev-parse", "--abbrev-ref", "HEAD"),
        "head": sh("git", "log", "-1", "--pretty=%h %s"),
        "ahead_of_main": sh("git", "rev-list", "--count", "main..HEAD") or "?",
        "dirty_files": len([x for x in sh("git", "status", "--porcelain").splitlines() if x]),
    }


def north_star():
    """The ONE metric: text-recall correct% / hallucination%, vs the 60%/<10% gate.
    Read from the latest honest eval artifact; never invented."""
    r = read_json(ROOT / "evaluation/ras/ocr_recall_text_foundergold.json")
    if not r:
        return {"status": "NO_DATA", "correct_pc": None, "halluc_pc": None}
    s = r.get("summary", {})
    n = sum(s.values()) or 1
    cor, wr = s.get("CORRECT", 0), s.get("WRONG", 0)
    ans = cor + wr
    correct_pc = round(100 * cor / n, 1)
    halluc_pc = round(100 * wr / ans, 1) if ans else 0.0
    gate = correct_pc >= 60 and halluc_pc < 10
    return {
        "metric": "text-recall vs founder gold",
        "n": n, "correct": cor, "wrong": wr, "refused": s.get("REFUSED", 0),
        "correct_pc": correct_pc, "halluc_pc": halluc_pc,
        "gate": "PASS" if gate else "BOUNDARY" if correct_pc >= 60 else "FAIL",
        "gate_def": ">=60% correct AND <10% hallucination(wrong/answered)",
        "model": r.get("model", "gemma3:27b consensus"),
        "caveat": "n is small; standalone recall eval, not full brain",
        "baseline_correct_pc": 47.0, "baseline_halluc_pc": 42.0,
    }


def pipeline():
    """Each stage: role, status (LIVE/STUB/BROKEN), latency (UNINSTRUMENTED until hooked)."""
    stages = [
        ("capture", "Quartz window grab -> in-mem CGImage", "LIVE_FRAGILE",
         "CGWindowListCreateImage deprecated (macOS 14+); ScreenCaptureKit migration pending"),
        ("ocr", "Apple Vision VNRecognizeText (verbatim)", "LIVE", "self-calibrating: reads-or-silent"),
        ("scene_vlm", "gemma3:12b per-frame caption/objects", "LIVE_LOSSY", "always-emits -> descoped for text Qs"),
        ("consensus", "cross-frame OCR vote (frequency=confidence)", "LIVE", "reads-or-refuses; in ask_home"),
        ("recall", "ask_home assembler/answerer (12b/27b)", "LIVE", "refuse-hard on anchored reading"),
        ("store", "kf_memory.json per capture (NOT a DB)", "LIVE_DEBT", "flat JSON; no vector index at query time"),
    ]
    return [{"stage": s, "role": r, "status": st, "note": nt,
             "latency_ms": None, "latency_status": "UNINSTRUMENTED"} for s, r, st, nt in stages]


def channels():
    return [
        {"channel": "OCR (Apple Vision)", "honesty": "SELF_CALIBRATING", "emits": "verbatim-or-nothing",
         "confidence": "VNConfidence available per-observation — NOT yet surfaced", "trust": "HIGH"},
        {"channel": "Consensus vote", "honesty": "SELF_CALIBRATING", "emits": "answer-or-refuse",
         "confidence": "support count (frames agreeing) — surfaced in ask result", "trust": "HIGH"},
        {"channel": "Scene VLM (gemma 12b)", "honesty": "ALWAYS_EMITS", "emits": "a caption every frame",
         "confidence": "none — fabricates colour/scene", "trust": "LOW (descoped for text)"},
        {"channel": "Assembler fallback", "honesty": "ALWAYS_EMITS", "emits": "an answer for non-reading Qs",
         "confidence": "none — source of 'June 1901'/'Hi kaife' lies before refuse-hard", "trust": "MEDIUM"},
    ]


def blockers():
    """The roadblock audit, machine-readable. severity P0=demo-blocking."""
    return [
        {"id": "capture_api", "sev": "P1", "title": "Live capture on deprecated Quartz API",
         "root": "CGWindowListCreateImage deprecated macOS 14+; can stall/blank ('live-feed window failure')",
         "fix": "Port trace_live_feed to ScreenCaptureKit (SCStream); 1 window by SCContentFilter; keep 0-raw-media",
         "owner": "codebase"},
        {"id": "halluc_fallback", "sev": "P1", "title": "Assembler fabricates on non-reading Qs",
         "root": "When consensus refuses & question isn't classified 'reading', assembler still guesses",
         "fix": "Extend refuse-hard to all anchored Qs without grounded support; gate every channel on confidence",
         "owner": "ai+codebase"},
        {"id": "small_n", "sev": "P0", "title": "Number not trustworthy (n=15)",
         "root": "Gate measured on 15 questions; 1 Q = 6.7%; boundary pass is noise",
         "fix": "Munich ~50-Q eval in flight (build_walk_eval.py) -> founder gold -> real number",
         "owner": "founder+ai"},
        {"id": "monolith", "sev": "P2", "title": "Brain is a 2898-line monolith",
         "root": "ask_home.py couples routing/retrieval/answer/gates; fragile to change, hard to test",
         "fix": "Extract typed channel interfaces (Perceptor/Memory/Recaller); graph of nodes, not one file",
         "owner": "codebase"},
        {"id": "no_instrument", "sev": "P2", "title": "Zero latency/throughput instrumentation",
         "root": "No perf_counter spans; cannot show pipeline latency or token->text compression",
         "fix": "Decorator @span(stage) -> append to ops/cockpit/metrics.jsonl; engine aggregates p50/p95",
         "owner": "codebase"},
        {"id": "quant_limit", "sev": "P2", "title": "12b-QAT mis-binds multi-line signs",
         "root": "Quantized 12b picks wrong street/line (Q25); 27b better but slow for live",
         "fix": "27b for on-demand recall (recall isn't real-time); 12b only for live capture caption",
         "owner": "ai"},
    ]


def progress():
    """Weighted milestones to pitch-ready + % complete + a PROJECTED ETA date.
    Effort is in working-days (rough, honest estimate); ETA = today + remaining effort.
    completion in [0,1]. The ETA is a projection, not a promise — labeled as such."""
    ms = [
        ("Honesty moat: consensus reads-or-refuses", 25, 1.0, 0, "shipped + wired into ask_home"),
        ("Trustworthy number (n>=50 founder gold)", 20, 0.55, 1, "Munich 45-Q page built; awaiting founder gold + 1 eval run"),
        ("Kill residual hallucination (gate every channel)", 15, 0.30, 2, "refuse-hard on anchored reading done; non-reading channels still guess"),
        ("Live capture hardened (ScreenCaptureKit + budget)", 20, 0.10, 3, "still on deprecated Quartz; no frame-budget drop"),
        ("Instrumentation (latency / compression)", 10, 0.25, 1, "OCR latency sampled; @span spans + compression pending"),
        ("Retention signal on real use", 10, 0.0, 5, "not started; the founder's own validation bar"),
    ]
    total_w = sum(w for _, w, _, _, _ in ms)
    pct = round(sum(w * c for _, w, c, _, _ in ms) / total_w, 3)
    remaining_days = sum(e * (1 - c) for _, _, c, e, _ in ms)
    # round up remaining effort, add weekend slack (~1.4x calendar/working)
    eta = datetime.date.today() + datetime.timedelta(days=round(remaining_days * 1.4))
    return {
        "pct_to_pitch_ready": round(pct * 100, 1),
        "projected_eta": eta.isoformat(),
        "remaining_effort_days": round(remaining_days, 1),
        "note": "ETA = today + remaining effort x1.4 calendar slack; projection, recomputed each run",
        "milestones": [{"label": l, "weight": w, "completion": c,
                        "effort_days_left": round(e * (1 - c), 1),
                        "state": "done" if c >= 1 else "active" if c > 0 else "todo",
                        "note": n} for l, w, c, e, n in ms],
    }


def realtime():
    """Live-capture feasibility: can the helpers keep up at frame-rate? Read from a
    sampled metrics file; UNINSTRUMENTED until the eval writes it."""
    r = read_json(CK / "realtime.json")
    if not r:
        return {"status": "UNINSTRUMENTED", "note": "run the eval's latency sample to populate"}
    return r


def build_status():
    """The in-flight bigger-capture pipeline."""
    qf = ROOT / "data/walks/munich_text/work/questions.json"
    page = ROOT / "data/walks/munich_text/work/gold_review_walk.html"
    q = read_json(qf, [])
    return {"video": "youtube bpPdGx6Soa4 (Munich 1080p60)",
            "questions_built": len(q) if isinstance(q, list) else 0,
            "gold_page_ready": page.exists(),
            "gold_page": str(page) if page.exists() else "building"}


HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>TRACE — engine cockpit</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--fg:#e6edf3;--dim:#8b949e;
--red:#f85149;--amber:#d29922;--green:#3fb950;--blue:#58a6ff}
*{box-sizing:border-box} body{background:var(--bg);color:var(--fg);font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;margin:0;padding:18px;max-width:1100px;margin:0 auto}
h1{font-size:15px;letter-spacing:.5px;margin:0 0 2px} .ts{color:var(--dim);font-size:11px}
.verdict{background:#3d1d1d;border:1px solid var(--red);border-radius:8px;padding:12px 14px;margin:12px 0;font-size:14px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px} @media(max-width:780px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}
.card h2{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--dim);margin:0 0 8px}
.big{font-size:30px;font-weight:700} .row{display:flex;justify-content:space-between;gap:10px;padding:3px 0;border-bottom:1px solid #21262d}
.pill{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:700}
.PASS,.LIVE,.HIGH{background:#12361f;color:var(--green)} .BOUNDARY,.LIVE_LOSSY,.LIVE_FRAGILE,.LIVE_DEBT,.MEDIUM{background:#3a2e10;color:var(--amber)}
.FAIL,.BROKEN,.LOW,.P0{background:#3d1d1d;color:var(--red)} .P1{background:#3a2e10;color:var(--amber)} .P2{background:#1c2a3a;color:var(--blue)}
.ALWAYS_EMITS{background:#3a2e10;color:var(--amber)} .SELF_CALIBRATING{background:#12361f;color:var(--green)}
table{width:100%;border-collapse:collapse;font-size:12px} td{padding:4px 6px;border-bottom:1px solid #21262d;vertical-align:top}
.blk{border-left:3px solid var(--line);padding:8px 10px;margin:8px 0;background:#0f141a;border-radius:0 6px 6px 0}
.blk.P0{border-color:var(--red)} .blk.P1{border-color:var(--amber)} .blk.P2{border-color:var(--blue)}
.blk .t{font-weight:700} .blk .r{color:var(--dim);margin-top:3px} .blk .f{color:var(--green);margin-top:3px}
.dim{color:var(--dim)} .wait{background:#13262f;border:1px solid var(--blue);border-radius:8px;padding:10px;margin-top:12px}
</style></head><body>
<h1>TRACE — ENGINE COCKPIT</h1><div class="ts" id="ts"></div>
<div class="verdict" id="verdict"></div>
<div class="card" id="progwrap"><h2>Progress to pitch-ready — <span id="pct"></span> · ETA <span id="eta"></span></h2>
<div id="progbar" style="height:14px;background:#21262d;border-radius:7px;overflow:hidden;margin:4px 0 10px">
<div id="progfill" style="height:100%;background:linear-gradient(90deg,#3fb950,#58a6ff)"></div></div>
<div id="ms"></div><div class="dim" id="etanote" style="margin-top:6px"></div></div>
<div class="grid">
  <div class="card"><h2>North Star — text-recall vs gold</h2><div id="ns"></div></div>
  <div class="card"><h2>Build / Git</h2><div id="git"></div></div>
</div>
<div class="card" style="margin-top:12px"><h2>Pipeline (capture → recall)</h2><table id="pipe"></table></div>
<div class="card" style="margin-top:12px"><h2>Channels — honesty class</h2><table id="chan"></table></div>
<div class="card" style="margin-top:12px"><h2>Blockers to pitch (root cause → blueprint)</h2><div id="blk"></div></div>
<div class="wait" id="wait"></div>
<script>
let D = __DATA__;
fetch('engine.json',{cache:'no-store'}).then(r=>r.json()).then(j=>{D=j;render();}).catch(()=>render());
const P=(c,t)=>`<span class="pill ${c}">${t}</span>`;
function render(){
  document.getElementById('ts').textContent = 'server_ts '+new Date(D.server_ts*1000).toLocaleString();
  document.getElementById('verdict').textContent = '⚑ '+D.verdict;
  const pr=D.progress;
  document.getElementById('pct').textContent = pr.pct_to_pitch_ready+'%';
  document.getElementById('eta').textContent = pr.projected_eta;
  document.getElementById('progfill').style.width = pr.pct_to_pitch_ready+'%';
  document.getElementById('etanote').textContent = pr.note+' · '+pr.remaining_effort_days+' effort-days left';
  document.getElementById('ms').innerHTML = pr.milestones.map(m=>{
    const col = m.state==='done'?'var(--green)':m.state==='active'?'var(--amber)':'var(--dim)';
    const mark = m.state==='done'?'✓':m.state==='active'?'◐':'○';
    return `<div class="row"><span style="color:${col}">${mark} ${m.label}</span>`+
      `<span class="dim">${Math.round(m.completion*100)}%${m.effort_days_left?' · '+m.effort_days_left+'d left':''}</span></div>`+
      `<div class="dim" style="font-size:11px;margin:-2px 0 4px 16px">${m.note}</div>`;}).join('');
  const rt=D.realtime;
  const n=D.north_star;
  document.getElementById('ns').innerHTML =
    `<div class="big">${n.correct_pc}% <span class="dim" style="font-size:14px">correct</span> &nbsp; ${n.halluc_pc}% <span class="dim" style="font-size:14px">halluc</span></div>`+
    `<div class="row"><span>gate ${n.gate_def}</span>${P(n.gate,n.gate)}</div>`+
    `<div class="row"><span>n / correct / wrong / refused</span><b>${n.n} / ${n.correct} / ${n.wrong} / ${n.refused}</b></div>`+
    `<div class="row"><span>baseline (single-frame)</span><span class="dim">${n.baseline_correct_pc}% / ${n.baseline_halluc_pc}%</span></div>`+
    `<div class="row dim">${n.caveat}</div>`;
  const g=D.git;
  document.getElementById('git').innerHTML =
    `<div class="row"><span>branch</span><b>${g.branch}</b></div>`+
    `<div class="row"><span>ahead of main</span><b>+${g.ahead_of_main}</b></div>`+
    `<div class="row"><span>dirty files</span><b>${g.dirty_files}</b></div>`+
    `<div class="row dim">${g.head}</div>`;
  document.getElementById('pipe').innerHTML = D.pipeline.map(s=>
    `<tr><td><b>${s.stage}</b></td><td>${P(s.status,s.status)}</td><td>${s.role}<div class="dim">${s.note}</div></td>`+
    `<td class="dim">${s.latency_status==='UNINSTRUMENTED'?'⊘ lat':s.latency_ms+'ms'}</td></tr>`).join('');
  document.getElementById('chan').innerHTML = D.channels.map(c=>
    `<tr><td><b>${c.channel}</b></td><td>${P(c.honesty,c.honesty.replace('_',' '))}</td><td>${c.emits}</td><td>${P(c.trust.split(' ')[0],'trust '+c.trust)}</td></tr>`).join('');
  document.getElementById('blk').innerHTML = D.blockers.sort((a,b)=>a.sev.localeCompare(b.sev)).map(b=>
    `<div class="blk ${b.sev}">${P(b.sev,b.sev)} <span class="t">${b.title}</span> <span class="dim">[${b.owner}]</span>`+
    `<div class="r">root: ${b.root}</div><div class="f">→ ${b.fix}</div></div>`).join('');
  const w=D.bigger_capture;
  const rtline = rt.status==='UNINSTRUMENTED' ? 'realtime: ⊘ uninstrumented'
    : `realtime: OCR p50 ${rt.ocr_p50_ms}ms / p95 ${rt.ocr_p95_ms}ms · ${rt.pct_within_budget}% within ${rt.budget_ms}ms live budget @ ${rt.fps}fps`;
  document.getElementById('wait').innerHTML = `<b>Waiting on founder:</b> ${D.waiting_on_founder}`+
    `<div class="dim">bigger capture: ${w.questions_built} Qs built · gold page ${w.gold_page_ready?'READY ✓':'building…'} · ${rtline}</div>`;
}
render();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args()
    ns = north_star()
    engine = {
        "server_ts": int(time.time()),
        "verdict": "NOT PITCH-READY — honesty moat works; number untrusted (n small); capture API fragile",
        "git": git_state(),
        "north_star": ns,
        "progress": progress(),
        "realtime": realtime(),
        "pipeline": pipeline(),
        "channels": channels(),
        "blockers": blockers(),
        "bigger_capture": build_status(),
        "waiting_on_founder": "fill Munich gold page when ready -> unlocks trustworthy number",
    }
    CK.mkdir(parents=True, exist_ok=True)
    (CK / "engine.json").write_text(json.dumps(engine, indent=2, ensure_ascii=False))
    (CK / "cockpit_engine.html").write_text(
        HTML.replace("__DATA__", json.dumps(engine, ensure_ascii=False)), encoding="utf-8")
    if args.print:
        g = ns
        print(f"VERDICT: {engine['verdict']}")
        print(f"NORTH STAR: {g.get('correct_pc')}% correct / {g.get('halluc_pc')}% halluc "
              f"[{g.get('gate')}]  (baseline {g.get('baseline_correct_pc')}%/{g.get('baseline_halluc_pc')}%)")
        print(f"GIT: {engine['git']['branch']} +{engine['git']['ahead_of_main']}  {engine['git']['head']}")
        print("BLOCKERS:")
        for b in engine["blockers"]:
            print(f"  [{b['sev']}] {b['title']}")
    print(f"wrote {CK/'engine.json'}")


if __name__ == "__main__":
    main()
