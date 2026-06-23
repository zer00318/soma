#!/usr/bin/env python3
"""Turn a downloaded walking-tour video into a text-recall eval + a founder gold page.

Pipeline (all local):
  1. extract frames at --fps (cv2; 60fps source -> sharp, low-blur samples),
  2. Apple-Vision OCR every frame -> the consensus memory (ocr_memory.json),
  3. select the --n most text-RICH frames, temporally spread (one key frame per sign,
     not ten of the same one), as the question anchors,
  4. gemma writes 1-2 READING questions per key frame (+ a candidate gold, to be fixed),
  5. emit gold_review_walk.html: embeds the YouTube player with a "watch at MM:SS"
     seek per question + the extracted frame, so the founder confirms gold against the
     actual video, then Exports the adjudications JSON.

Run (after downloading source.mp4):
  .venv/bin/python evaluation/build_walk_eval.py \
      --video data/walks/munich_text/source.mp4 \
      --outdir data/walks/munich_text/work --yt bpPdGx6Soa4 \
      --fps 2 --n 45 --qper 1
"""
import argparse
import base64
import json
import sys
import urllib.request
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evaluation.vision_ocr import ocr_image

MODEL = "gemma3:12b-it-qat"
HOST = "http://127.0.0.1:11434"

GENQ = (
    "You are looking at ONE frame from a first-person city walk. Below is the exact text "
    "Apple-Vision OCR read in this frame:\n---\n{ocr}\n---\n"
    "Write {qper} natural question(s) a person might ask their memory about TEXT they READ here "
    "(a shop/street/station name, a price, a menu item, what a sign or screen says). Each answer "
    "MUST be text actually present above. Output STRICT JSON: a list of objects "
    '{{"question": "...", "answer": "..."}}. No prose, just the JSON list.'
)


def oll(prompt, images=None):
    p = {"model": MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
    if images:
        p["images"] = images
    data = json.dumps(p).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(HOST + "/api/generate", data=data,
                                         headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read()).get("response", "").strip()
        except Exception:
            if attempt == 2:
                return ""
    return ""


def extract(video, outdir, fps, start, dur):
    """Extract frames at `fps` from [start, start+dur] seconds. Timestamps are the
    REAL video seconds (so the gold page's 'watch at MM:SS' matches the YouTube clock)."""
    frames_dir = Path(outdir) / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise SystemExit(f"cv2 could not open {video} (need ffmpeg backend / valid mp4)")
    vfps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(vfps / fps))
    start_f = int(start * vfps)
    end_f = int((start + dur) * vfps) if dur else int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
    out = []
    i = start_f
    while i < end_f:
        ok = cap.grab()
        if not ok:
            break
        if (i - start_f) % step == 0:
            t = i / vfps
            ok, frame = cap.retrieve()
            if ok:
                p = frames_dir / f"f_{int(round(t*1000)):08d}ms.jpg"
                cv2.imwrite(str(p), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
                out.append((round(t, 2), str(p)))
        i += 1
    cap.release()
    return out


def richness(lines):
    """Readable-text weight: total chars of lines that look like words (>=3 chars,
    has a vowel), so keyboard/garbage glyphs don't inflate the score."""
    score = 0
    for l in lines:
        w = l.strip()
        if len(w) >= 3 and any(c in "aeiouAEIOUäöü" for c in w):
            score += len(w)
    return score


def select_rich(scored, n, min_gap_s):
    """Greedy: take the richest frame, then exclude everything within min_gap_s, repeat.
    One key frame per distinct sign/scene; consensus uses the neighbours at answer time."""
    pool = sorted(scored, key=lambda x: -x["rich"])
    picked, used = [], []
    for f in pool:
        if f["rich"] <= 0:
            continue
        if all(abs(f["t"] - u) >= min_gap_s for u in used):
            picked.append(f)
            used.append(f["t"])
        if len(picked) >= n:
            break
    picked.sort(key=lambda x: x["t"])
    return picked


def gen_questions(frame_path, ocr_lines, qper):
    raw = oll(GENQ.format(ocr="\n".join(ocr_lines), qper=qper),
              images=[base64.b64encode(Path(frame_path).read_bytes()).decode()])
    s = raw[raw.find("["): raw.rfind("]") + 1]
    try:
        items = json.loads(s)
        return [{"question": str(q.get("question", "")).strip(),
                 "answer": str(q.get("answer", "")).strip()}
                for q in items if q.get("question")][:qper]
    except Exception:
        return []


HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>TRACE — Munich walk gold</title>
<style>
body{font:15px/1.55 -apple-system,sans-serif;max-width:820px;margin:18px auto;padding:0 16px;color:#111}
h1{font-size:20px} .sub{color:#666;margin-bottom:14px}
#player{position:sticky;top:0;background:#fff;padding-bottom:8px;z-index:9}
.card{border:1px solid #ddd;border-radius:10px;padding:14px;margin:14px 0}
.card img{max-width:100%;border-radius:6px;display:block;margin:8px 0}
.q{font-weight:600;margin-bottom:6px} label{margin-right:14px;font-size:14px}
.seek{background:#1971c2;color:#fff;border:0;border-radius:6px;padding:5px 10px;cursor:pointer;font-size:13px}
input[type=text]{width:100%;padding:7px;font-size:14px;box-sizing:border-box;margin-top:6px}
details{margin-top:8px;color:#888;font-size:13px}
#bar{position:sticky;bottom:0;background:#fff;border-top:1px solid #ddd;padding:12px 0}
button#export{background:#e8590c;color:#fff;border:0;border-radius:8px;padding:10px 18px;font-size:15px;cursor:pointer}
#out{width:100%;height:80px;margin-top:8px;font:12px monospace} .no input[type=text]{opacity:.35}
</style></head><body>
<h1>TRACE — confirm the gold (Munich walk)</h1>
<div class="sub">For each question: click <b>▶ watch at…</b> to jump the video to that moment, look carefully,
and type the TRUE short answer (the box has an AI guess — fix it). If it's not answerable from the video there,
pick <b>not answerable</b>. Then <b>Export</b> at the bottom and paste the JSON back to the Chief.</div>
<div id="player"><div id="yt"></div></div>
<div id="app"></div>
<div id="bar"><button id="export">Export gold &rarr; clipboard</button>
<textarea id="out" placeholder="exported JSON appears here"></textarea></div>
<script src="https://www.youtube.com/iframe_api"></script>
<script>
const DATA = __DATA__; const YT = "__YT__";
let player;
function onYouTubeIframeAPIReady(){ player = new YT.Player('yt',
  {height:'360',width:'640',videoId:YT,playerVars:{rel:0}}); }
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const mmss = s => Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');
const app = document.getElementById('app');
DATA.forEach(it => {
  const c = document.createElement('div'); c.className='card'; c.id='c'+it.id;
  c.innerHTML =
    '<div class="q">Q'+it.id+': '+esc(it.question)+'</div>'+
    '<button class="seek" data-t="'+it.t+'">▶ watch at '+mmss(it.t)+'</button>'+
    '<img loading="lazy" src="'+it.src+'">'+
    '<label><input type="radio" name="a'+it.id+'" value="yes" checked> answerable</label>'+
    '<label><input type="radio" name="a'+it.id+'" value="no"> not answerable</label>'+
    '<input type="text" id="g'+it.id+'" value="'+esc(it.candidate)+'">'+
    '<details><summary>what the OCR read here</summary>'+esc(it.ocr)+'</details>';
  app.appendChild(c);
  c.querySelector('.seek').onclick = e => { if(player&&player.seekTo){player.seekTo(+e.target.dataset.t,true);player.playVideo();window.scrollTo({top:0,behavior:'smooth'});} };
  c.querySelectorAll('input[name=a'+it.id+']').forEach(r=>r.onchange=()=>{
    c.classList.toggle('no', c.querySelector('input[name=a'+it.id+']:checked').value==='no'); });
});
document.getElementById('export').onclick = () => {
  const res = DATA.map(it => ({ id: it.id, t: it.t, question: it.question,
    answerable: document.querySelector('input[name=a'+it.id+']:checked').value==='yes',
    gold: document.getElementById('g'+it.id).value.trim() }));
  const s = JSON.stringify(res, null, 0);
  document.getElementById('out').value = s;
  if (navigator.clipboard) navigator.clipboard.writeText(s);
};
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--yt", required=True, help="youtube video id (for the embedded player)")
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--n", type=int, default=45, help="key frames -> questions")
    ap.add_argument("--qper", type=int, default=1)
    ap.add_argument("--min-gap", type=float, default=6.0, help="seconds between key frames")
    ap.add_argument("--start", type=float, default=0, help="start second in the video")
    ap.add_argument("--dur", type=float, default=0, help="seconds to process from start (0=all)")
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"1/4 extracting frames [{args.start}s..+{args.dur}s] @ {args.fps}fps...", flush=True)
    frames = extract(args.video, args.outdir, args.fps, args.start, args.dur)
    print(f"    {len(frames)} frames @ {args.fps}fps", flush=True)

    print("2/4 OCR (Apple Vision) over all frames...", flush=True)
    memory, scored = {}, []
    for k, (t, p) in enumerate(frames):
        lines = ocr_image(p)
        memory[Path(p).name] = {"t": t, "frame": Path(p).name, "ocr": lines}
        scored.append({"t": t, "path": p, "lines": lines, "rich": richness(lines)})
        if k % 200 == 0:
            print(f"    {k}/{len(frames)}", flush=True)
    json.dump(memory, open(out / "ocr_memory.json", "w"), ensure_ascii=False)

    print("3/4 selecting text-rich key frames...", flush=True)
    keys = select_rich(scored, args.n, args.min_gap)
    print(f"    {len(keys)} key frames", flush=True)

    print("4/4 generating reading questions (gemma)...", flush=True)
    items = []
    for f in keys:
        for q in gen_questions(f["path"], f["lines"], args.qper):
            b64 = base64.b64encode(Path(f["path"]).read_bytes()).decode()
            items.append({"id": len(items), "t": f["t"],
                          "src": "data:image/jpeg;base64," + b64,
                          "question": q["question"], "candidate": q["answer"],
                          "ocr": " | ".join(f["lines"])})
        print(f"    q for t={f['t']}s ({len(items)} total)", flush=True)

    # questions.json (without the heavy base64) for the eval harness
    qjson = [{"id": it["id"], "t": it["t"], "frame": next(s["path"] for s in scored if s["t"] == it["t"]),
              "question": it["question"], "candidate": it["candidate"], "ocr": it["ocr"]}
             for it in items]
    json.dump(qjson, open(out / "questions.json", "w"), ensure_ascii=False, indent=2)

    html = HTML.replace("__DATA__", json.dumps(items, ensure_ascii=False)).replace("__YT__", args.yt)
    page = out / "gold_review_walk.html"
    page.write_text(html, encoding="utf-8")
    print(f"\nDONE: {len(items)} questions across {len(keys)} frames")
    print(f"  gold page: {page}")
    print(f"  memory:    {out/'ocr_memory.json'}  ({len(frames)} frames)")
    print(f"  questions: {out/'questions.json'}")


if __name__ == "__main__":
    main()
