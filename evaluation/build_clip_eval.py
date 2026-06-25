#!/usr/bin/env python3
"""Clip-level, grounded, live-faithful eval builder.

Fixes the two things the earlier build got wrong (frames that didn't match the
question, and the same sign asked 3x):

  1. BEST-FRAME ANCHORING. A sign is read across ~15-70 frames as the camera walks
     past; the EARLIEST sighting is far away/truncated, the close-up read is
     complete. We anchor each question (the shown frame + the YouTube seek + the
     candidate text) to the frame where the text was read MOST COMPLETELY, not the
     first glimpse. The candidate is a verbatim line from THAT frame, so what the
     founder sees on the page is always actually present in the shown frame.
  2. FUZZY DEDUP. OCR variants of the same sign ("B1O" vs "BIO",
     "Freilandhuhner" vs "Freilandhühner") are merged by string similarity, so one
     real sign = one question instead of three near-identical ones.

It stays CLIP-LEVEL and grounded: we only ask about text the camera DEMONSTRABLY
READ in >=2 frames (the live consensus signal), so the premise is always real, and
questions are phrased with the temporal NEIGHBOUR context (the shop name read a few
seconds away) so they're specific, not "what did that sign say?".

Reuses the cached ocr_memory.json (no re-OCR). Optional --latency re-samples OCR
timing to re-prove live feasibility. Run:
  .venv/bin/python evaluation/build_clip_eval.py --work data/walks/munich_text/work \
      --yt bpPdGx6Soa4 --n 40
"""
import argparse
import base64
import collections
import difflib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import consensus_recall as cr

MODEL = "gemma3:12b-it-qat"
HOST = "http://127.0.0.1:11434"

# string-similarity threshold for merging two OCR readings into one sign cluster.
# 0.72 merges the poultry-list OCR variants while keeping genuinely different signs
# at the same shop (e.g. the poultry list vs the price list) separate. Verified on
# the Munich walk.
MERGE_RATIO = 0.72
# a sign must be legible in at least one real frame to be askable.
MIN_COVERAGE = 0.6

PHRASE = (
    "You are writing ONE recall question about a sign a camera read on a city walk near "
    "the {mmss} mark. The answer to your question is the sign's text.\n"
    "Sign text (raw OCR, may have small errors): \"{span}\".\n"
    "Nearby signs (context only):\n{context}\n\n"
    "Rules:\n"
    "- If the text is a READABLE name or phrase, write a SPECIFIC question naming it. Examples:\n"
    "    'KAISERSCHMARRN-ALM' -> 'What restaurant did you pass at the market?'\n"
    "    'GUT, BESSER, PAULANER' -> \"What was Paulaner's slogan?\"\n"
    "    'NORDSEE' -> 'What seafood chain did you walk past?'\n"
    "    'Enten - Weidegänse - Waldhühner' with a 'Geflügelparadies' name nearby ->\n"
    "        'What poultry did Geflügelparadies list?'\n"
    "- ONLY if the text is unreadable GARBLE (not real words, e.g. 'lböhrnler', "
    "'OPERNFESTSPITC', 'wone Hlacker'), write EXACTLY: 'What did the sign around {mmss} say?'.\n"
    "- Prefer the specific form; use the time form only when the text truly isn't real words.\n"
    "- Never use the words weird, funny, quirky, camera, device, 'that sign', or 'that shop'.\n"
    "Output ONLY the question, one line."
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


def latency_sample(work, fps=2.0, k=40):
    """Time OCR on k frames -> is the helper real-time at frame-rate? Writes realtime.json."""
    from evaluation.vision_ocr import ocr_image
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


def words(s):
    """Content tokens, umlauts kept intact (unlike cr._norm which splits them)."""
    return [w for w in re.findall(r"[a-z0-9äöüß]{3,}", s.lower())]


def _key(s):
    return re.sub(r"[^a-z0-9äöüß]+", " ", s.lower()).strip()


def clip_spans(memory, n, min_frames=2, min_gap_s=8.0):
    """High-confidence text the camera read across the clip, fuzzy-deduped, each
    anchored to the frame where it reads most completely."""
    occ = collections.defaultdict(list)  # key(raw) -> [(t, raw, frame_name)]
    for fname, fr in memory.items():
        t = fr.get("t")
        for raw in fr.get("ocr", []):
            raw = raw.strip()
            if not _READABLE.search(raw) or cr.is_noise(raw) or len(raw) < 4:
                continue
            occ[_key(raw)].append((t, raw, fname))

    # fuzzy-cluster: fold a key into an existing cluster on substring OR high ratio.
    reps, clusters = [], {}
    for k in sorted(occ, key=len, reverse=True):
        host = next((c for c in reps if k in c or c in k
                     or difflib.SequenceMatcher(None, k, c).ratio() >= MERGE_RATIO), None)
        if host is None:
            reps.append(k)
            clusters[k] = list(occ[k])
        else:
            clusters[host].extend(occ[k])

    def coverage(rep_tokens, frame_name):
        if not rep_tokens:
            return 0.0
        ft = set()
        for ln in memory[frame_name].get("ocr", []):
            ft |= set(words(ln))
        return len(rep_tokens & ft) / len(rep_tokens)

    cand = []
    for hits in clusters.values():
        frames_seen = len(set(round(t, 1) for t, _, _ in hits if t is not None))
        if frames_seen < min_frames:
            continue
        rep = max((r for _, r, _ in hits), key=len)
        rep_tokens = set(words(rep))
        # best frame = the sighting whose full OCR most completely contains the sign.
        bt, _, bfn = max(hits, key=lambda h: (coverage(rep_tokens, h[2]), -abs((h[0] or 0))))
        cov = coverage(rep_tokens, bfn)
        if cov < MIN_COVERAGE:
            continue
        # candidate = the longest verbatim line IN that frame belonging to this sign,
        # so what we show is exactly what the shown frame contains.
        in_frame = [ln.strip() for ln in memory[bfn].get("ocr", [])
                    if set(words(ln)) & rep_tokens]
        candidate = max(in_frame, key=len) if in_frame else rep
        cand.append({"candidate": candidate, "frames": frames_seen, "t": round(bt, 2),
                     "frame": bfn, "cov": round(cov, 2),
                     "score": frames_seen * len(candidate)})

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


_NAME = re.compile(r"^[A-ZÄÖÜ][\wÄÖÜäöü&'.\- ]{2,}$")


def neighbours(picked, idx, window_s=12.0, k=5):
    """Other picked candidates read within window_s of picked[idx] — the context
    that lets gemma phrase a specific question (and the deterministic fallback name)."""
    t = picked[idx]["t"]
    ctx = [p["candidate"] for j, p in enumerate(picked)
           if j != idx and abs(p["t"] - t) <= window_s]
    return ctx[:k]


def name_anchor(span, ctx):
    """Best short proper-name in the neighbourhood, for the deterministic fallback."""
    pool = [span] + ctx
    names = [c for c in pool if _NAME.match(c.strip()) and len(c.split()) <= 4
             and any(len(w) >= 4 for w in c.split())]
    return min(names, key=len) if names else None


_VOWEL = set("aeiouäöüy")


def quotable(s):
    """Is this reading clean enough to put inside a question, or garbled OCR we
    should not echo? Catches stray OCR punctuation and low-vowel gibberish tokens."""
    if any(ch in s for ch in '"|*=~'):
        return False
    toks = [t for t in words(s) if len(t) >= 4]
    if not toks:
        return len(words(s)) > 0  # all-short (e.g. "NORDSEE C)" -> 'nordsee') is fine
    bad = 0
    for t in toks:
        v = sum(1 for c in t if c in _VOWEL) / len(t)
        if v < 0.18 or v > 0.7:           # consonant soup or vowel soup
            bad += 1
    return bad / len(toks) <= 0.34


def mmss(t):
    return f"{int(t//60)}:{int(t%60):02d}"


def fallback_q(span, ctx, t):
    anchor = name_anchor(span, ctx)
    if anchor and quotable(anchor) and _key(anchor) != _key(span):
        return f"What did the sign at {anchor.strip()} say?"
    return f"What did the sign around {mmss(t)} say?"


def good_question(q, span, ctx):
    """Reject bad gemma output: must end in '?', not be vague, and not echo a
    garbled candidate as if it were a real name."""
    if not q or "?" not in q:
        return False
    low = q.lower()
    if any(b in low for b in ("weird", "funny", "quirky", "camera", "device")):
        return False
    if "that sign" in low or "that shop" in low:
        return False
    # if the candidate is garbled, the question must not quote a chunk of it.
    if not quotable(span):
        garble = [t for t in words(span) if len(t) >= 5 and not quotable(t)]
        if any(t in low for t in garble):
            return False
    return True


def frame_src(work, frame_name):
    b64 = base64.b64encode((work / "frames" / frame_name).read_bytes()).decode()
    return "data:image/jpeg;base64," + b64


HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>TRACE — clip gold</title><style>
body{font:15px/1.55 -apple-system,sans-serif;max-width:820px;margin:18px auto;padding:0 16px;color:#111}
h1{font-size:20px}.sub{color:#666;margin-bottom:14px}
.card{border:1px solid #ddd;border-radius:10px;padding:14px;margin:14px 0}
.card img{max-width:100%;border-radius:6px;display:block;margin:8px 0}
.q{font-weight:600;margin-bottom:6px}.opt{margin:6px 0}.opt label{margin-right:16px;font-size:14px}
.meta{color:#888;font-size:12px}
.seek{background:#1971c2;color:#fff;border-radius:6px;padding:6px 11px;font-size:13px;text-decoration:none;display:inline-block;margin:6px 0}
input[type=text]{width:100%;padding:7px;font-size:14px;box-sizing:border-box;margin-top:6px}
#bar{position:sticky;bottom:0;background:#fff;border-top:1px solid #ddd;padding:12px 0}
button#export{background:#e8590c;color:#fff;border:0;border-radius:8px;padding:10px 18px;font-size:15px;cursor:pointer}
#out{width:100%;height:80px;margin-top:8px;font:12px monospace}.bad input[type=text]{opacity:.35}
#prog{font-size:13px;color:#666;margin-left:12px}
</style></head><body>
<h1>TRACE — confirm the gold (whole-clip recall)</h1>
<div class="sub">Each card is a sign the camera <b>read up close</b> during the walk. The image is the
frame where it read most clearly, and the text box is exactly what it read there. For each:
check the box matches the sign (click ▶ to watch that exact moment if unsure), then pick —
<b>correct</b> (box matches the real sign), <b>fix it</b> (edit the box to the true text),
<b>not in clip</b> (it isn't actually there), or <b>bad question</b> (the question is malformed).
Then <b>Export</b> and paste back.</div>
<div id="app"></div>
<div id="bar"><button id="export">Export gold &rarr; clipboard</button><span id="prog"></span>
<textarea id="out" placeholder="exported JSON appears here"></textarea></div>
<script>
const DATA=__DATA__; const VID="__YT__";
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const mmss=s=>Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');
const app=document.getElementById('app');
DATA.forEach(it=>{const c=document.createElement('div');c.className='card';c.id='c'+it.id;
 c.innerHTML='<div class="q">Q'+it.id+': '+esc(it.question)+'</div>'+
  '<img loading="lazy" src="'+it.src+'">'+
  '<div class="meta">read in '+it.frames_seen+' frames · clearest at '+mmss(it.t)+'</div>'+
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
 const fixed=res.filter(r=>r.verdict==='fix').length, bad=res.filter(r=>r.verdict==='not in clip'||r.verdict==='bad question').length;
 document.getElementById('prog').textContent=res.length+' answered · '+fixed+' fixed · '+bad+' dropped';
 if(navigator.clipboard)navigator.clipboard.writeText(s);};
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--yt", required=True)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--latency", action="store_true",
                    help="re-sample OCR latency (re-OCRs frames; slow). Off by default.")
    args = ap.parse_args()
    work = Path(args.work)
    memory = json.load(open(work / "ocr_memory.json"))

    if args.latency:
        print("sampling OCR latency (live-feasibility)...", flush=True)
        rt = latency_sample(work, args.fps)
        print(f"    OCR p50 {rt['ocr_p50_ms']}ms / p95 {rt['ocr_p95_ms']}ms; "
              f"{rt['pct_within_budget']}% within {rt['budget_ms']}ms -> feasible_live={rt['feasible_live']}", flush=True)

    print("1/2 extracting high-confidence clip spans (fuzzy-deduped, best-frame)...", flush=True)
    spans = clip_spans(memory, args.n)
    print(f"    {len(spans)} distinct signs (each read in >=2 frames, legible in >=1)", flush=True)

    print("2/2 phrasing specific, context-grounded questions...", flush=True)
    items = []
    for i, s in enumerate(spans):
        ctx = neighbours(spans, i)
        ctx_str = "\n".join(f"- {c}" for c in ctx) or "(none)"
        q = oll(PHRASE.format(context=ctx_str, span=s["candidate"], mmss=mmss(s["t"])))
        q = (q.splitlines() or [""])[0].strip().strip('"')
        if not good_question(q, s["candidate"], ctx):
            q = fallback_q(s["candidate"], ctx, s["t"])
        items.append({"id": len(items), "t": s["t"], "src": frame_src(work, s["frame"]),
                      "question": q, "candidate": s["candidate"],
                      "frames_seen": s["frames"], "frame": s["frame"], "cov": s["cov"]})
        print(f"    Q{i} (t={s['t']}s, seen {s['frames']}x, cov {s['cov']}): {q[:64]}", flush=True)

    qjson = [{k: v for k, v in it.items() if k != "src"} for it in items]
    json.dump(qjson, open(work / "clip_questions.json", "w"), ensure_ascii=False, indent=2)
    html = HTML.replace("__DATA__", json.dumps(items, ensure_ascii=False)).replace("__YT__", args.yt)
    (work / "gold_clip.html").write_text(html, encoding="utf-8")
    print(f"\nDONE: {len(items)} clip-level questions")
    print(f"  questions: {work/'clip_questions.json'}")
    print(f"  gold page: {work/'gold_clip.html'}")


if __name__ == "__main__":
    main()
