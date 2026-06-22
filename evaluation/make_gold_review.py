#!/usr/bin/env python3
"""Generate a self-contained HTML gold-review checklist from the ablation run.

Open the output in a browser (file://), look at each frame, set the TRUE answer
(or mark it not-answerable-from-this-frame), click Export, paste the JSON back.
We then recompute answerable-from-text + hallucination against YOUR gold instead
of gemma's unreliable auto-gold (which misread "Satoshi" as "Satomi").
"""
import json
from pathlib import Path

SRC = "evaluation/ras/posthoc_ablation_n16.json"
FRAMES_DIR = "../data/walks/walk_outside_20260614/work/run_frames"
OUT = "evaluation/gold_review.html"

rows = json.load(open(SRC))["rows"]
seen, items = set(), []
for r in rows:
    key = (r["frame"], r["question"])
    if key in seen:
        continue
    seen.add(key)
    items.append({
        "id": len(items),
        "src": f"{FRAMES_DIR}/{r['frame']}",
        "frame": r["frame"],
        "question": r["question"],
        "candidate": r["gold"],      # gemma's guess — to be corrected
        "sys": r["text_answer"],     # what TRACE answered (hidden by default)
    })

DATA = json.dumps(items, ensure_ascii=False)

TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8">
<title>TRACE gold review</title><style>
body{font:15px/1.5 -apple-system,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;color:#111}
h1{font-size:20px} .sub{color:#666;margin-bottom:20px}
.card{border:1px solid #ddd;border-radius:10px;padding:14px;margin:14px 0}
.card img{max-width:100%;border-radius:6px;display:block;margin-bottom:10px}
.q{font-weight:600;margin-bottom:8px} label{margin-right:14px}
input[type=text]{width:100%;padding:7px;font-size:14px;box-sizing:border-box;margin-top:4px}
details{margin-top:8px;color:#888;font-size:13px}
#bar{position:sticky;bottom:0;background:#fff;border-top:1px solid #ddd;padding:12px 0}
button{background:#e8590c;color:#fff;border:0;border-radius:8px;padding:10px 18px;font-size:15px;cursor:pointer}
#out{width:100%;height:90px;margin-top:8px;font:12px monospace}
.no input[type=text]{opacity:.4}
</style></head><body>
<h1>TRACE — confirm the gold</h1>
<div class="sub">For each frame: if the answer is visible in <b>this</b> image, set the correct short answer (the box is pre-filled with an AI guess — fix it). If it is NOT answerable from this frame, choose "not answerable". Then click <b>Export</b> at the bottom and paste the result back to the Chief.</div>
<div id="app"></div>
<div id="bar"><button id="export">Export adjudications &rarr; clipboard</button>
<textarea id="out" placeholder="exported JSON appears here"></textarea></div>
<script>
const DATA = __DATA__;
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const app = document.getElementById('app');
DATA.forEach(it => {
  const c = document.createElement('div'); c.className = 'card'; c.id = 'c'+it.id;
  c.innerHTML =
    '<img loading="lazy" src="'+it.src+'">'+
    '<div class="q">Q'+it.id+': '+esc(it.question)+'</div>'+
    '<label><input type="radio" name="a'+it.id+'" value="yes" checked> answerable from THIS frame</label>'+
    '<label><input type="radio" name="a'+it.id+'" value="no"> not answerable</label>'+
    '<input type="text" id="g'+it.id+'" value="'+esc(it.candidate)+'">'+
    '<details><summary>what TRACE answered</summary>'+esc(it.sys)+'</details>';
  app.appendChild(c);
  c.querySelectorAll('input[name=a'+it.id+']').forEach(r=>r.onchange=()=>{
    c.classList.toggle('no', c.querySelector('input[name=a'+it.id+']:checked').value==='no');
  });
});
document.getElementById('export').onclick = () => {
  const res = DATA.map(it => ({
    id: it.id,
    answerable: document.querySelector('input[name=a'+it.id+']:checked').value === 'yes',
    gold: document.getElementById('g'+it.id).value.trim()
  }));
  const s = JSON.stringify(res);
  document.getElementById('out').value = s;
  if (navigator.clipboard) navigator.clipboard.writeText(s);
};
</script></body></html>"""

Path(OUT).write_text(TEMPLATE.replace("__DATA__", DATA), encoding="utf-8")
print(f"wrote {OUT} with {len(items)} questions across {len({i['frame'] for i in items})} frames")
