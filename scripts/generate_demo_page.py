#!/usr/bin/env python
"""Generate a self-contained, offline demo page from the pre-computed answer cache.

No server, no network, no model call at show time — the cache is embedded inline, so the
3-minute pitch cannot dice-roll or stall. Every answer shown is the real agent output.

    .venv/bin/python scripts/generate_demo_page.py --cache ops/demo/demo_cache.json --out ops/demo/demo.html
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

BEAT_LABEL = {
    "recall": "IT REMEMBERS EVERYTHING",
    "brands": "IT READS THE FINE PRINT",
    "detail": "DOWN TO THE FLAVOUR",
    "listing": "IT KNOWS WHERE THINGS ARE",
    "attribute": "IT NOTICES DETAILS",
    "presence": "IT ANSWERS WHAT IT SAW",
    "moat": "IT WILL NOT MAKE THINGS UP",
}

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TRACE — a memory you can trust</title>
<style>
:root{{--bg:#0a0b10;--card:#14161f;--line:#232634;--txt:#e8eaf0;--dim:#8b90a3;
--good:#34d399;--warn:#fbbf24;--accent:#7c9cff}}
*{{box-sizing:border-box}}
body{{margin:0;background:radial-gradient(1200px 600px at 50% -10%,#161a2b,#0a0b10);
color:var(--txt);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
-webkit-font-smoothing:antialiased;padding:32px 18px 80px}}
.wrap{{max-width:760px;margin:0 auto}}
h1{{font-size:30px;letter-spacing:-.5px;margin:0 0 4px}}
.tag{{color:var(--dim);margin:0 0 30px;font-size:15px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;
margin:14px 0;cursor:pointer;transition:.15s;user-select:none}}
.card:hover{{border-color:#33384a}}
.beat{{font-size:11px;letter-spacing:1.5px;color:var(--accent);font-weight:700;margin-bottom:6px}}
.q{{font-size:18px;font-weight:600}}
.a{{margin-top:14px;font-size:17px;display:none;animation:fade .25s ease}}
.card.open .a{{display:block}}
.badge{{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;
padding:3px 10px;border-radius:999px;margin-bottom:10px}}
.b-good{{background:rgba(52,211,153,.12);color:var(--good);border:1px solid rgba(52,211,153,.3)}}
.b-refuse{{background:rgba(251,191,36,.12);color:var(--warn);border:1px solid rgba(251,191,36,.3)}}
.dot{{width:7px;height:7px;border-radius:50%;background:currentColor}}
.ev{{margin-top:12px;display:flex;flex-wrap:wrap;gap:6px}}
.chip{{font-size:11px;color:var(--dim);background:#0e1018;border:1px solid var(--line);
border-radius:8px;padding:4px 9px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.hint{{color:var(--dim);font-size:13px;margin-top:6px}}
.foot{{color:var(--dim);font-size:13px;text-align:center;margin-top:34px;line-height:1.7}}
@keyframes fade{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1}}}}
</style></head><body><div class="wrap">
<h1>TRACE</h1>
<p class="tag">A memory for everything you see &mdash; that you can actually trust. Tap a question.</p>
<div id="cards"></div>
<p class="foot">On-device &middot; raw video is deleted after reading &middot; only the words it saw are kept.<br>
Every answer here is the real engine&rsquo;s output over a genuine capture of this room.</p>
</div>
<script>
const DATA = __DATA__;
const LABEL = __LABEL__;
const cards = document.getElementById('cards');
DATA.entries.forEach(e => {{
  const d = document.createElement('div'); d.className='card';
  const refused = e.refused;
  const badge = refused
    ? '<div class="badge b-refuse"><span class="dot"></span>WON\\'T INVENT IT &mdash; it never saw this</div>'
    : '<div class="badge b-good"><span class="dot"></span>GROUNDED &middot; confidence '+Math.round(e.confidence*100)+'%</div>';
  const ev = (e.evidence||[]).map(x=>'<span class="chip">'+x.replace(/</g,'&lt;')+'</span>').join('');
  d.innerHTML = '<div class="beat">'+(LABEL[e.beat]||e.beat.toUpperCase())+'</div>'
    + '<div class="q">'+e.question+'</div>'
    + '<div class="hint">tap to reveal</div>'
    + '<div class="a">'+badge+'<div>'+e.answer+'</div>'
    + (ev?'<div class="ev">'+ev+'</div>':'')+'</div>';
  d.onclick=()=>{{d.classList.toggle('open'); const h=d.querySelector('.hint'); if(h)h.style.display=d.classList.contains('open')?'none':'block';}};
  cards.appendChild(d);
}});
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    data = json.loads(Path(args.cache).read_text())
    html = PAGE.replace("__DATA__", json.dumps(data)).replace("__LABEL__", json.dumps(BEAT_LABEL))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(html)
    print(f"wrote demo page -> {args.out} ({len(data['entries'])} beats)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
