#!/usr/bin/env python3
"""Wiring tests: PII is scrubbed AT THE STORAGE SEAM, on the real artifacts the
brain reasons over — not just in the standalone scrub_pii unit. Proves the
privacy claim is enforced end-to-end:
  - live ingest  (trace_brain_server._records_to_kf): phone reads -> kf_memory
  - demo build   (cockpit_ask_server._build_demo_memory): OCR cache -> kf_memory

Run: PYTHONPATH=scripts .venv/bin/python -m pytest evaluation/test_scrub_wiring.py -q
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# A line with three kinds of PII, plus the kind of fact the product MUST keep.
PII = "contact a.b@x.de or call +49 89 289 112, IBAN DE89370400440532013000"
KEEP = "WILHELM CONRAD RÖNTGEN 1845 - 1923"


def _assert_scrubbed_but_kept(blob: str):
    # PII gone
    assert "@x.de" not in blob, "email leaked"
    assert "289 112" not in blob, "phone leaked"
    assert "DE89370400440532013000" not in blob, "IBAN leaked"
    assert "[redacted]" in blob, "nothing was redacted"
    # the facts the product exists to remember survive
    assert "RÖNTGEN" in blob, "name was wrongly scrubbed"
    assert "1845 - 1923" in blob, "year-range was wrongly scrubbed"


def test_live_ingest_persists_scrubbed_memory():
    """The phone-ingest path that writes data/phone_captures/<m>/kf_memory.json."""
    import trace_brain_server as tbs

    kf = tbs._records_to_kf(
        [
            {"t": 0.0, "text": PII, "ocr": [PII]},
            {"t": 1.0, "text": KEEP, "ocr": [KEEP]},
        ]
    )
    _assert_scrubbed_but_kept(json.dumps(kf, ensure_ascii=False))


def test_demo_build_persists_scrubbed_memory():
    """The cockpit demo path that materialises the kf_memory.json the brain reads."""
    import cockpit_ask_server as cas

    tmp = Path(tempfile.mkdtemp(prefix="scrub_demo_")) / "ocr_memory.json"
    tmp.write_text(
        json.dumps(
            {"frame_000000_0.0s.jpg": [PII], "frame_000015_0.5s.jpg": [KEEP]},
            ensure_ascii=False,
        )
    )
    orig = cas.OCR_MEMO
    cas.OCR_MEMO = tmp
    try:
        built = cas._build_demo_memory(("sig", 1, 1.0))
        assert built is not None and built.get("path")
        stored = Path(built["path"]).read_text()
    finally:
        cas.OCR_MEMO = orig
    _assert_scrubbed_but_kept(stored)
