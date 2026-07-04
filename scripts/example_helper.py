#!/usr/bin/env python3
"""The 20-line helper (spec §5, packet P02): ANY process that POSTs this shape is a
TRACE sense. Copy this file, change helper_id and the observation loop, done — the
spine never changes. Optionally add your helper_id to config/helpers.json so coverage
reports group it; unregistered helpers work too.

    .venv/bin/python scripts/example_helper.py "the kettle just boiled"
"""
import json
import sys
import time
import urllib.request

HUB = "http://127.0.0.1:8765/capture/perception"

observation = {
    "contract": 1,
    "helper_id": "example_kettle_watcher",
    "text": sys.argv[1] if len(sys.argv) > 1 else "EVENT | kettle | boiled | example helper",
    "t_ms": int(time.time() * 1000),
    "confidence": 0.9,
    "session_id": "example-session",
    "provenance": {"script": "example_helper.py"},
}

req = urllib.request.Request(HUB, data=json.dumps(observation).encode(),
                             headers={"Content-Type": "application/json"})
print(urllib.request.urlopen(req, timeout=10).read().decode())
