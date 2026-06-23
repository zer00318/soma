#!/usr/bin/env python3
"""Clip-level, grounded, live-faithful eval builder.

Fixes three things the frame-pinned approach got wrong:
  1. CLIP-LEVEL, not frame-pinned. We don't ask "at frame 1639, what's the museum?"
     (and get a hallucinated premise). We find text the camera DEMONSTRABLY READ across
     the walk (a span seen in >=2 frames = high-confidence), and ask a natural recall
     question grounded in THAT span — so the premise is always real.
  2. LIVE-FAITHFUL capture. We don't "study frames to reverse-engineer answers". The
     OCR memory was produced per-frame (as the live helpers would). We additionally
     SAMPLE OCR latency to prove the helper keeps up at frame-rate (the live budget),
     and write it to ops/cockpit/realtime.json.
  3. A "bad question / not in clip" escape, so a malformed question is never forced.

Reuses the cached ocr_memory.json (no re-OCR). Run:
  .venv/bin/python evaluation/build_clip_eval.py --work data/walks/munich_text/work \
      --yt bpPdGx6Soa4 --n 40
"""
import argparse
import base64
import collections
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from evaluation.vision_ocr import ocr_image
import consensus_recall as cr

MODEL = "gemma3:12b-it-qat"
HOST = "http://127.0.0.1:11434"

PHRASE = (
    "On a city walk, a sign/shopfront read this exact text: \"{span}\".\n"
    "Write ONE short, natural question a person would later ask to recall it, whose answer is this text. "
    "Examples: 'What was the name of the fish shop at the market?' / 'What poultry types did the butcher "
    "list?' / 'What was the bakery's slogan?'. Plain and specific. Do NOT use the words 'weird', 'funny', "
    "'quirky', or 'camera'. Output ONLY the question, one line."
)


def oll(prompt):
    p = {"model": MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
    data = json.dumps(p).encode()
    for _ in range(3):
        try:
            req = urllib.request.Request(HOST + "/api/generate", data=data,
                                         headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read()).get("response", "").strip()
        except Exception:
            pass
    return ""


def latency_sample(memory, work, fps=2.0, k=40):
    """Time OCR on k frames -> is the helper real-time at frame-rate? Writes realtime.json."""
    frames = sorted((work / "frames").glob("f_*.jpg"))
    step = max(1, len(frames) // k)
    sample = frames[::step][:k]
    lat = []
    for p in sample:
        t0 = time.perf_counter()
        ocr_image(str(p))
        lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()
    budget = 1000.0 / fps
    p50 = lat[len(lat) // 2]
    p95 = lat[int(len(lat) * 0.95)]
    within = round(100 * sum(1 for x in lat if x <= budget) / len(lat), 1)
    rt = {"channel": "Apple Vision OCR", "fps": fps, "budget_ms": round(budget),
          "ocr_p50_ms": round(p50), "ocr_p95_ms": round(p95),
          "pct_within_budget": within, "n_sampled": len(lat),
          "feasible_live": p95 <= budget,
          "note": "OCR per frame vs the live per-frame budget; full VLM caption (~1-3s) does NOT fit -> OCR-first"}
    (ROOT / "ops/cockpit/realtime.json").write_text(json.dumps(rt, indent=2))
    return rt


_READABLE = re.compile(r"[A-Za-zÄÖÜäöü]{4,}")


def clip_spans(memory, n, min_frames=2, min_gap_s=8.0):
    """High-confidence text the camera read across the clip: lines that recur in
    >=min_frames frames (the live consensus signal), deduped by substring, ranked by
    (frames-seen x length), spread in time so we cover distinct things, not one sign."""
    occ = collections.defaultdict(list)  # normalized line -> [(t, raw)]
    for fr in memory.values():
        t = fr.get("t")
        for raw in fr.get("ocr", []):
            raw = raw.strip()
            if not _READABLE.search(raw) or cr.is_noise(raw) or len(raw) < 4:
                continue
            occ[cr._norm(raw)].append((t, raw))
    # cluster by substring: fold a short normalized key into a longer one
    keys = sorted(occ, key=len, reverse=True)
    clusters = {}
    for k in keys:
        host = next((c for c in clusters if k in c), None)
        if host is None:
            clusters[k] = list(occ[k])
        else:
            clusters[host].extend(occ[k])
    cand = []
    for k, hits in clusters.items():
        frames_seen = len(set(round(t, 1) for t, _ in hits if t is not None))
        if frames_seen < min_frames:
            continue
        rep = max((r for _, r in hits), key=len)            # most complete reading
        t0 = min(t for t, _ in hits if t is not None)
        cand.append({"span": rep, "frames": frames_seen, "t": round(t0, 2),
                     "score": frames_seen * len(rep)})
    cand.sort(key=lambda x: -x["score"])
    picked, used = [], []
    for c in cand:
        if all(abs(c["t"] - u) >= min_gap_s for u in used):
            picked.append(c)
            used.append(c["t"])
        if len(picked) >= n:
            break
    picked.sort(key=lambda x: x["t"])
    return picked


def frame_at(work, t):
    """Nearest extracted frame file to time t (ms-named f_00000000ms.jpg)."""
    target = int(round(t * 1000))
    best, bd = None, 1e18
    for p in (work / "frames").glob("f_*.jpg"):
        ms = int(re.search(r"f_(\d+)ms", p.name).group(1))
        if abs(ms - target) < bd:
            best, bd = p, abs(ms - target)
    return best


HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>TRACE — clip gold</title><style>
body{font:15px/1.55 -apple-system,sans-serif;max-width:820px;margin:18px auto;padding:0 16px;color:#111}
h1{font-size:20px}.sub{color:#666;margin-bottom:14px}
.card{border:1px solid #ddd;border-radius:10px;padding:14px;margin:14px 0}
.card img{max-width:100%;border-radius:6px;display:block;margin:8px 0}
.q{font-weight:600;margin-bottom:6px}.opt{margin:6px 0}.opt label{margin-right:16px;font-size:14px}
.seek{background:#1971c2;color:#fff;border-radius:6px;padding:6px 11px;font-size:13px;text-decoration:none;display:inline-block;margin:6px 0}
input[type=text]{width:100%;padding:7px;font-size:14px;box-sizing:border-box;margin-top:6px}
#bar{position:sticky;bottom:0;background:#fff;border-top:1px solid #ddd;padding:12px 0}
button#export{background:#e8590c;color:#fff;border:0;border-radius:8px;padding:10px 18px;font-size:15px;cursor:pointer}
#out{width:100%;height:80px;margin-top:8px;font:12px monospace}.bad input[type=text]{opacity:.35}
</style></head><body>
<h1>TRACE — confirm the gold (whole-clip recall)</h1>
<div class="sub">These are things the camera <b>read across the walk</b>. For each: read the frame (or click ▶ to
watch that moment on YouTube), then pick one — <b>correct</b> (the box matches what the sign really says),
<b>fix it</b> (edit the box to the true text), <b>not in clip</b> (it isn't actually there), or
<b>bad question</b> (the question itself is malformed). Then <b>Export</b> and paste back.</div>
<div id="app"></div>
<div id="bar"><button id="export">Export gold &rarr; clipboard</button>
<textarea id="out" placeholder="exported JSON appears here"></textarea></div>
<script>
const DATA=__DATA__; const VID="__YT__";
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const mmss=s=>Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');
const app=document.getElementById('app');
DATA.forEach(it=>{const c=document.createElement('div');c.className='card';c.id='c'+it.id;
 c.innerHTML='<div class="q">Q'+it.id+': '+esc(it.question)+'</div>'+
  '<img loading="lazy" src="'+it.src+'">'+
  '<a class="seek" target="_blank" rel="noopener" href="https://www.youtube.com/watch?v='+VID+'&t='+Math.floor(it.t)+'s">▶ watch on YouTube at '+mmss(it.t)+'</a>'+
  '<div class="opt">'+['correct','fix','not in clip','bad question'].map((v,i)=>
    '<label><input type="radio" name="a'+it.id+'" value="'+v+'"'+(i==0?' checked':'')+'> '+v+'</label>').join('')+'</div>'+
  '<input type="text" id="g'+it.id+'" value="'+esc(it.candidate)+'">';
 app.appendChild(c);
 c.querySelectorAll('input[name=a'+it.id+']').forEach(r=>r.onchange=()=>{
   const v=c.querySelector('input[name=a'+it.id+']:checked').value;
   c.classList.toggle('bad', v==='not in clip'||v==='bad question');});
});
document.getElementById('export').onclick=()=>{
 const res=DATA.map(it=>{const v=document.querySelector('input[name=a'+it.id+']:checked').value;
  return {id:it.id,t:it.t,question:it.question,verdict:v,
    gold:(v==='not in clip'||v==='bad question')?null:document.getElementById('g'+it.id).value.trim()};});
 const s=JSON.stringify(res);document.getElementById('out').value=s;
 if(navigator.clipboard)navigator.clipboard.writeText(s);};
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--yt", required=True)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--fps", type=float, default=2.0)
    args = ap.parse_args()
    work = Path(args.work)
    memory = json.load(open(work / "ocr_memory.json"))

    print("1/3 sampling OCR latency (live-feasibility)...", flush=True)
    rt = latency_sample(memory, work, args.fps)
    print(f"    OCR p50 {rt['ocr_p50_ms']}ms / p95 {rt['ocr_p95_ms']}ms; "
          f"{rt['pct_within_budget']}% within {rt['budget_ms']}ms budget -> feasible_live={rt['feasible_live']}", flush=True)

    print("2/3 extracting high-confidence clip spans...", flush=True)
    spans = clip_spans(memory, args.n)
    print(f"    {len(spans)} spans (seen in >=2 frames each)", flush=True)

    print("3/3 phrasing clip-level questions (gemma, grounded in the span)...", flush=True)
    items = []
    for s in spans:
        q = oll(PHRASE.format(span=s["span"])).splitlines()[0].strip().strip('"') if True else ""
        if not q:
            q = f"What did the sign you passed around {int(s['t']//60)}:{int(s['t']%60):02d} say?"
        fp = frame_at(work, s["t"])
        b64 = base64.b64encode(fp.read_bytes()).decode()
        items.append({"id": len(items), "t": s["t"], "src": "data:image/jpeg;base64," + b64,
                      "question": q, "candidate": s["span"], "frames_seen": s["frames"]})
        print(f"    Q{len(items)-1} (t={s['t']}s, seen {s['frames']}x): {q[:60]}", flush=True)

    qjson = [{k: v for k, v in it.items() if k != "src"} for it in items]
    json.dump(qjson, open(work / "clip_questions.json", "w"), ensure_ascii=False, indent=2)
    html = HTML.replace("__DATA__", json.dumps(items, ensure_ascii=False)).replace("__YT__", args.yt)
    (work / "gold_clip.html").write_text(html, encoding="utf-8")
    print(f"\nDONE: {len(items)} clip-level questions")
    print(f"  gold page: {work/'gold_clip.html'}")


if __name__ == "__main__":
    main()
