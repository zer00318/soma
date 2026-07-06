#!/usr/bin/env python3
"""P34 induction spike, data side: raw AX tree snapshots for grammar induction.

Every INTERVAL_S, if the frontmost app is a browser with a URL, dump the FULL
walked tree (roles, text, geometry, paths — not the daemon's salience-capped
rows) to evaluation/ax_corpus/<domain>/<ts>.json. Induction needs many
snapshots of the SAME container over time; this collector builds that corpus
fast. Local-only, gitignored, privacy-blocklist respected.

  nohup .venv/bin/python scripts/ax_corpus_collector.py >> /tmp/trace_ax_corpus.log 2>&1 &
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ax_adapter import ax_trusted, enable_web_ax, walk_front_window  # noqa: E402
from mac_screen_daemon import active_tab_url, is_private, load_blocklist  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "evaluation" / "ax_corpus"
INTERVAL_S = 45


def main() -> int:
    if not ax_trusted():
        print("no AX trust — abort")
        return 1
    blocklist = load_blocklist()
    seen_pids: set = set()
    n = 0
    print(f"[ax-corpus] collecting every {INTERVAL_S}s", flush=True)
    while True:
        time.sleep(INTERVAL_S)
        try:
            from AppKit import NSWorkspace
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is None:
                continue
            name = str(app.localizedName())
            url = active_tab_url(name)
            if not url or is_private(url, blocklist):
                n += 0
                if name.endswith("Browser") and not url:
                    print(f"[ax-corpus] no url from {name} (Automation TCC?)", flush=True)
                continue
            pid = int(app.processIdentifier())
            if pid not in seen_pids:
                enable_web_ax(pid)
                seen_pids.add(pid)
            els = walk_front_window(pid)
            if len(els) < 5:
                continue
            joined = " ".join(e["text"] for e in els)
            if is_private(joined, blocklist):
                continue
            domain = urllib.parse.urlparse(url).netloc or "unknown"
            out_dir = CORPUS / domain
            out_dir.mkdir(parents=True, exist_ok=True)
            stamp = int(time.time() * 1000)
            (out_dir / f"{stamp}.json").write_text(json.dumps(
                {"t_ms": stamp, "app": name, "url": url, "elements": els}))
            n += 1
            if n % 10 == 1:
                print(f"[ax-corpus] {n} snapshots ({domain}: {len(els)} els)", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[ax-corpus] tick failed: {exc}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
