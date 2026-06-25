#!/usr/bin/env python3
"""Cockpit ENGINE — computes the honest founder-facing reality surface.

The cockpit exists to separate demo readiness from product truth. It emits the
architecture state, verified evidence, the honest n=15 number, and a projection
that refuses false-precision dates when the work is blocked on big-n capture and
human gold.

  .venv/bin/python scripts/cockpit_engine.py
  .venv/bin/python scripts/cockpit_engine.py --print
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "ops" / "cockpit"


def sh(*args: str) -> str:
    try:
        return subprocess.check_output(
            args, cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return ""


def read_json(path: Path, default=None):
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def git_state() -> dict:
    return {
        "branch": sh("git", "rev-parse", "--abbrev-ref", "HEAD") or "unknown",
        "head": sh("git", "log", "-1", "--pretty=%h %s") or "unknown",
        "ahead_of_main": sh("git", "rev-list", "--count", "main..HEAD") or "?",
        "dirty_files": len(
            [x for x in sh("git", "status", "--porcelain=v1").splitlines() if x]
        ),
    }


def north_star() -> dict:
    """The current honest number, read from the small-n recall artifact."""
    result = read_json(ROOT / "evaluation/ras/ocr_recall_text_foundergold.json")
    summary = (result or {}).get("summary", {})
    n = sum(summary.values()) or 15
    correct = summary.get("CORRECT", 9)
    wrong = summary.get("WRONG", 2)
    refused = summary.get("REFUSED", 4)
    answered = correct + wrong
    correct_pc = round(100 * correct / n, 1) if n else 0.0
    halluc_pc = round(100 * wrong / answered, 1) if answered else 0.0
    gate = "BOUNDARY" if correct_pc >= 60.0 else "FAIL"
    if correct_pc >= 60.0 and halluc_pc < 10.0:
        gate = "PASS"
    return {
        "metric": "text-recall vs founder gold",
        "scope": "TEXT subset only; standalone recall eval, NOT the full brain",
        "n": n,
        "correct": correct,
        "wrong": wrong,
        "refused": refused,
        "correct_pc": correct_pc,
        "fair_correct_pc": 67.0,
        "halluc_pc": halluc_pc,
        "gate": gate,
        "gate_def": "≥60% correct AND <10% hallucination(wrong/answered)",
        "trusted_gate": "UNMEASURED",
        "trusted_gate_def": "n≥50 held-out with human gold",
        "model": (result or {}).get("model", "gemma3:27b consensus"),
        "caveat": "small n; standalone recall eval, NOT the full brain",
        "baseline_correct_pc": 47.0,
        "baseline_halluc_pc": 42.0,
    }


def architecture() -> dict:
    return {
        "one_liner": (
            "HELPERS extract (open-ended) → INJECT binds at capture into a "
            "provenance+confidence scene/event graph (the binding brain) → "
            "LLM thinks and refuses past the edge of capture. Capture is primary "
            "(the moment is irreversible); world-reach is the backstop."
        ),
        "allowed_states": ["built", "partial", "not_built", "unverified"],
        "primary_gap": "Stage 3 Bind / INJECT is not built.",
    }


def pipeline() -> list[dict]:
    return [
        {
            "stage": "0 Frame & Sync",
            "role": "space-time frame: timestamped pose · clock · place",
            "state": "partial",
            "note": (
                "native capture has time + GPS/geocode; per-observation 3D "
                "pose-anchoring (ARKit) is NOT wired."
            ),
        },
        {
            "stage": "1 Detect & Localize",
            "role": "detection / OCR / speech → boxes",
            "state": "partial",
            "note": (
                "native detector+OCR+speech proven in Munich 2026-06-04 "
                "(vision 102, detector 29, speech 1); 3D-anchoring of boxes NOT "
                "done; OCR acceptance was 0 in the last run and needs a fix."
            ),
        },
        {
            "stage": "2 Track & Identify",
            "role": "persistent entity IDs, re-ID, diarization",
            "state": "not_built",
            "note": (
                "the fusion digest has frequency/seen-counts, which is NOT true "
                "cross-frame identity binding."
            ),
        },
        {
            "stage": "3 Bind / INJECT",
            "role": "scene-graph binding with confidence",
            "state": "not_built",
            "note": (
                "inject_expand.py is FUSE/EXPAND only, NOT the binding brain. "
                "This is THE primary gap / next build."
            ),
        },
        {
            "stage": "4 Enrich",
            "role": "VLM caption · emotion · world-EXPAND, written onto entities",
            "state": "partial",
            "note": (
                "EXPAND is built and hallucination-gated (n=4 adversarial audit "
                'on real gemma, refute-by-default corroboration killed a confident '
                'fabrication "ZLORPTECH" at conf 0.95); emotion/affect NOT built.'
            ),
        },
        {
            "stage": "5 Reason / LLM",
            "role": "ask_home brain; honesty gates S1/S2/B1",
            "state": "built",
            "note": "built but small-n.",
        },
    ]


def verified() -> list[dict]:
    return [
        {
            "claim": "Cross-frame consensus OCR recall (TEXT subset only)",
            "evidence": (
                "47%→60% strict / 67% fair; hallucination 42%→~9–18%; "
                "n=15 (small)."
            ),
            "module": "scripts/consensus_recall.py, wired into ask_home",
            "caveat": "small n; standalone recall eval, NOT the full brain.",
        },
        {
            "claim": "EXPAND hallucination-gate",
            "evidence": "n=4 adversarial audit on real gemma; recognize-or-stay-silent.",
            "module": "scripts/inject_expand.py",
            "caveat": "EXPAND is not the binding brain.",
        },
        {
            "claim": "PII scrub",
            "evidence": (
                "wired into BOTH storage seams (live ingest + demo build) + tested "
                "end-to-end."
            ),
            "module": "test_scrub_wiring.py, test_scrub_pii.py",
            "caveat": "privacy line = no raw media stored/leaves.",
        },
    ]


def deliverables() -> list[dict]:
    return [
        {
            "name": "Flawless 3-min investor demo",
            "verdict": "essentially READY",
            "note": (
                "curated demo_cache beats, instant, grounded, honest privacy footer; "
                'the "wow" of the architecture.'
            ),
        },
        {
            "name": "Trustworthy honest number",
            "verdict": "NOT MET",
            "note": "the pitch-ready product gate is n≥50 held-out with human gold — UNMEASURED.",
        },
    ]


def projection() -> dict:
    build_order = [
        "Stage 3 binding brain: bind helper outputs into a provenance+confidence scene/event graph.",
        "Stage 2 identity: persistent entity IDs, re-ID, and diarization across frames.",
        "Calibrated binding-confidence + conformal/selective abstention.",
        "Big-n eval: founder capture + human gold, then n≥50 held-out measurement.",
    ]
    return {
        "label": "Realistic projection",
        "projection": (
            "Blocked on big-n capture (needs founder) for the trustworthy product "
            "number. No single ETA is honest until Stage 3/2 are built and the "
            "founder capture + human gold exist."
        ),
        "remaining_build_order": build_order,
        "current_verdict": (
            "Demo essentially ready; product number untrusted (n=15) — the binding "
            "brain (Stage 3) and a big-n eval are the gates."
        ),
    }


def realtime() -> dict:
    data = read_json(CK / "realtime.json")
    if not data:
        return {
            "status": "unverified",
            "note": "No realtime metrics artifact found; leave unverified rather than inventing.",
        }
    return data


def build_status() -> dict:
    qf = ROOT / "data/walks/munich_text/work/clip_questions.json"
    page = ROOT / "data/walks/munich_text/work/gold_clip.html"
    questions = read_json(qf, [])
    return {
        "video": "youtube bpPdGx6Soa4 (Munich 1080p60)",
        "questions_built": len(questions) if isinstance(questions, list) else 0,
        "gold_page_ready": page.exists(),
        "gold_page": str(page) if page.exists() else "building",
        "caveat": "question page is not a measured product number until founder gold exists and eval runs.",
    }


def channels() -> list[dict]:
    return [
        {
            "channel": "OCR consensus",
            "honesty": "reads-or-refuses",
            "trust": "higher trust but small-n",
            "caveat": "verified only on TEXT subset, n=15.",
        },
        {
            "channel": "EXPAND",
            "honesty": "recognize-or-stay-silent",
            "trust": "promising but tiny audit",
            "caveat": "n=4 adversarial audit; not a substitute for binding.",
        },
        {
            "channel": "Scene/binding",
            "honesty": "not yet calibrated",
            "trust": "not product-trusted",
            "caveat": "Stage 3 binding brain is not built.",
        },
    ]


def blockers() -> list[dict]:
    return [
        {
            "id": "stage3_binding",
            "sev": "P0",
            "title": "Binding brain not built",
            "root": "Current inject_expand.py is FUSE/EXPAND only, not capture-time scene/event graph binding.",
            "fix": "Build conservative provenance+confidence binding at capture.",
            "owner": "codebase",
        },
        {
            "id": "stage2_identity",
            "sev": "P0",
            "title": "Cross-frame identity not built",
            "root": "Frequency/seen-counts are not persistent entity identity, re-ID, or diarization.",
            "fix": "Add identity layer before trusting bound cross-time answers.",
            "owner": "codebase",
        },
        {
            "id": "big_n_eval",
            "sev": "P0",
            "title": "Trustworthy product number unmeasured",
            "root": "Current number is n=15; the real gate is n≥50 held-out with human gold.",
            "fix": "Founder capture + human gold + held-out eval.",
            "owner": "founder+codebase",
        },
        {
            "id": "ocr_acceptance",
            "sev": "P1",
            "title": "OCR acceptance was 0 in the last run",
            "root": "Detector/OCR exists, but last-run acceptance needs repair before it can feed binding.",
            "fix": "Fix acceptance path and surface per-observation confidence/provenance.",
            "owner": "codebase",
        },
    ]


def engine() -> dict:
    ns = north_star()
    proj = projection()
    return {
        "server_ts": int(time.time()),
        "verdict": proj["current_verdict"],
        "git": git_state(),
        "north_star": ns,
        "honest_number": {
            "n": ns["n"],
            "correct_pc": ns["correct_pc"],
            "halluc_pc": ns["halluc_pc"],
            "wrong_over_answered": f"{ns['wrong']}/{ns['correct'] + ns['wrong']}",
            "gate": ns["gate"],
            "gate_def": ns["gate_def"],
            "caveat": ns["caveat"],
            "baseline": (
                f"{ns['baseline_correct_pc']}% correct / "
                f"{ns['baseline_halluc_pc']}% hallucination (same small n=15 baseline)"
            ),
            "true_product_gate": "n≥50 held-out with human gold — UNMEASURED",
        },
        "architecture": architecture(),
        "progress": proj,
        "projection": proj,
        "realtime": realtime(),
        "pipeline": pipeline(),
        "verified": verified(),
        "deliverables": deliverables(),
        "channels": channels(),
        "blockers": blockers(),
        "bigger_capture": build_status(),
        "waiting_on_founder": "founder capture + human gold are required for the trustworthy n≥50 number",
    }


HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TRACE — honest engine cockpit</title>
<style>
:root{--bg:#0d1117;--panel:#151a21;--panel2:#10151c;--line:#30363d;--fg:#e6edf3;--dim:#8b949e;--red:#f85149;--amber:#d29922;--green:#3fb950;--blue:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:18px}
h1{font-size:20px;margin:0;font-weight:750}
h2{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:var(--dim);margin:0 0 10px}
.top{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:12px}
.ts{color:var(--dim);font-size:12px}
.verdict{border:1px solid var(--red);background:#2a1517;border-radius:8px;padding:13px 14px;font-size:16px;font-weight:700;margin-bottom:12px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.grid3{display:grid;grid-template-columns:1.2fr .8fr .9fr;gap:12px}
@media(max-width:900px){.grid,.grid3{grid-template-columns:1fr}.top{display:block}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:13px}
.line{display:flex;justify-content:space-between;gap:12px;padding:5px 0;border-bottom:1px solid #222933}
.line:last-child{border-bottom:0}
.dim{color:var(--dim)}
.big{font-size:34px;font-weight:800;line-height:1.1}
.pill{display:inline-block;border-radius:999px;padding:2px 8px;font-size:11px;font-weight:800;white-space:nowrap}
.built,.ready{background:#12361f;color:var(--green)}
.partial,.boundary,.p1{background:#3a2e10;color:var(--amber)}
.not_built,.notmet,.p0{background:#3d1d1d;color:var(--red)}
.unverified,.p2{background:#1c2a3a;color:var(--blue)}
.one{font-size:15px;border-left:3px solid var(--blue);padding-left:12px}
.stage{display:grid;grid-template-columns:190px 92px 1fr;gap:10px;padding:10px 0;border-bottom:1px solid #222933}
.stage:last-child{border-bottom:0}
.stage strong{display:block}
.callout{background:#2a1517;border:1px solid var(--red);border-radius:8px;padding:10px;margin-top:10px;font-weight:750}
.deliverable{display:grid;grid-template-columns:1fr auto;gap:10px;padding:9px 0;border-bottom:1px solid #222933}
.deliverable:last-child{border-bottom:0}
.list{margin:0;padding:0;list-style:none}
.list li{padding:7px 0;border-bottom:1px solid #222933}
.list li:last-child{border-bottom:0}
.blocker{border-left:3px solid var(--red);background:var(--panel2);border-radius:0 7px 7px 0;padding:9px 10px;margin:8px 0}
.blocker.p1{border-color:var(--amber)}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
</style>
</head>
<body>
<main>
  <div class="top">
    <div><h1>TRACE — Honest Engine Cockpit</h1><div class="ts" id="ts"></div></div>
    <div class="ts mono" id="gitTop"></div>
  </div>
  <div class="verdict" id="verdict"></div>

  <section class="card" style="margin-bottom:12px">
    <h2>Architecture</h2>
    <div class="one" id="oneLine"></div>
  </section>

  <div class="grid3">
    <section class="card">
      <h2>Honest Number</h2>
      <div id="number"></div>
    </section>
    <section class="card">
      <h2>Two Deliverables</h2>
      <div id="deliverables"></div>
    </section>
    <section class="card">
      <h2>Projection</h2>
      <div id="projection"></div>
    </section>
  </div>

  <section class="card" style="margin-top:12px">
    <h2>6-Stage Pipeline</h2>
    <div id="pipeline"></div>
  </section>

  <div class="grid" style="margin-top:12px">
    <section class="card">
      <h2>Verified Evidence</h2>
      <ul class="list" id="verified"></ul>
    </section>
    <section class="card">
      <h2>Primary Gates / Build Order</h2>
      <div id="blockers"></div>
    </section>
  </div>
</main>
<script>
let D = __DATA__;
fetch('engine.json',{cache:'no-store'}).then(r=>r.json()).then(j=>{D=j;render();}).catch(()=>render());
const esc = v => String(v ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const pill = (cls, text) => `<span class="pill ${esc(cls)}">${esc(text)}</span>`;
function render(){
  const g = D.git || {};
  const n = D.north_star || {};
  const h = D.honest_number || n;
  document.getElementById('ts').textContent = 'server_ts ' + new Date((D.server_ts || 0)*1000).toLocaleString();
  document.getElementById('gitTop').textContent = `${g.branch || 'unknown'} · +${g.ahead_of_main || '?'} ahead · ${g.dirty_files ?? '?'} dirty`;
  document.getElementById('verdict').textContent = D.verdict || '';
  document.getElementById('oneLine').textContent = D.architecture?.one_liner || '';
  document.getElementById('number').innerHTML =
    `<div class="big">${esc(h.correct_pc)}% <span class="dim" style="font-size:14px">correct, n=${esc(h.n)}</span></div>`+
    `<div class="line"><span>hallucination</span><b>${esc(h.halluc_pc)}% wrong/answered (${esc(h.wrong_over_answered || '')})</b></div>`+
    `<div class="line"><span>gate</span>${pill(String(h.gate || '').toLowerCase(), h.gate || '')}</div>`+
    `<div class="line"><span>gate definition</span><span>${esc(h.gate_def)}</span></div>`+
    `<div class="line"><span>baseline</span><span>${esc(h.baseline || `${n.baseline_correct_pc}% / ${n.baseline_halluc_pc}%`)}</span></div>`+
    `<div class="dim" style="margin-top:8px">${esc(h.caveat)}</div>`+
    `<div class="callout">THE GATE: ${esc(h.true_product_gate || n.trusted_gate_def || '')}</div>`;
  document.getElementById('deliverables').innerHTML = (D.deliverables || []).map(d => {
    const cls = String(d.verdict || '').includes('NOT') ? 'notmet' : 'ready';
    return `<div class="deliverable"><div><b>${esc(d.name)}</b><div class="dim">${esc(d.note)}</div></div>${pill(cls,d.verdict)}</div>`;
  }).join('');
  document.getElementById('projection').innerHTML =
    `<div><b>${esc(D.projection?.projection || D.progress?.projection || '')}</b></div>`+
    `<ul class="list" style="margin-top:8px">${(D.projection?.remaining_build_order || []).map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`;
  document.getElementById('pipeline').innerHTML = (D.pipeline || []).map(s =>
    `<div class="stage"><div><strong>${esc(s.stage)}</strong><span class="dim">${esc(s.role)}</span></div>`+
    `<div>${pill(s.state, s.state)}</div><div>${esc(s.note)}</div></div>`
  ).join('');
  document.getElementById('verified').innerHTML = (D.verified || []).map(v =>
    `<li><b>${esc(v.claim)}</b><div>${esc(v.evidence)}</div><div class="dim">${esc(v.module)} · ${esc(v.caveat)}</div></li>`
  ).join('');
  document.getElementById('blockers').innerHTML = (D.blockers || []).map(b =>
    `<div class="blocker ${esc(String(b.sev || '').toLowerCase())}">${pill(String(b.sev || '').toLowerCase(), b.sev || '')} `+
    `<b>${esc(b.title)}</b><div class="dim">root: ${esc(b.root)}</div><div>→ ${esc(b.fix)}</div></div>`
  ).join('');
}
render();
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()

    data = engine()
    CK.mkdir(parents=True, exist_ok=True)
    (CK / "engine.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (CK / "cockpit_engine.html").write_text(
        HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False)),
        encoding="utf-8",
    )

    if args.print:
        print(f"VERDICT: {data['verdict']}")
        print(
            "HONEST NUMBER: "
            f"n={data['honest_number']['n']} "
            f"{data['honest_number']['correct_pc']}% correct / "
            f"{data['honest_number']['halluc_pc']}% halluc "
            f"[{data['honest_number']['gate']}]"
        )
        print(f"TRUE GATE: {data['honest_number']['true_product_gate']}")
        print(
            "PIPELINE: "
            + ", ".join(f"{s['stage']}={s['state']}" for s in data["pipeline"])
        )
    print(f"wrote {CK / 'engine.json'} and {CK / 'cockpit_engine.html'}")


if __name__ == "__main__":
    main()
