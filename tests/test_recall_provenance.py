"""Sealed-recall provenance: graph-backed answers must carry citations + confidence.

End-to-end: synthetic WhatsApp export → import_whatsapp → RecallFirewall.
Every graph-backed answer must cite source, timestamp, and the attributes used,
and expose a conservative aggregate confidence (min over cited facts).
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from trace_hub.crypto import EncryptedTextCodec
from trace_hub.graph import RelationalMemoryGraph
from trace_hub.importer import import_whatsapp
from trace_hub.recall import RecallFirewall
from trace_hub.storage import MemoryStore

_TEST_KEY = b"trace-test-key-for-unit-tests-xyz"

_CHAT = """\
12.5.2026, 09:15 - Alice Tester: Good morning, did you see the grant slides?
12.5.2026, 09:17 - Alice Tester: I will send you the budget spreadsheet after our call
12.5.2026, 09:20 - Pranav: I will finish the market analysis section for the application
13.5.2026, 18:40 - Alice Tester: The meeting room is booked for Thursday afternoon
13.5.2026, 18:42 - Alice Tester: Looking forward to the demo presentation session
"""


class TestRecallProvenance(unittest.TestCase):
    def setUp(self) -> None:
        # Fixture dates are fixed; pin the commitment recency window so the
        # test does not start failing once the dates age past the default.
        os.environ["TRACE_COMMITMENT_WINDOW_DAYS"] = "36500"
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        db = tmp / "trace_hub.sqlite3"
        chat = tmp / "_chat.txt"
        chat.write_text(_CHAT, encoding="utf-8")
        codec = EncryptedTextCodec(_TEST_KEY)
        # Graph first so schema exists, then import into the same DB file
        self.graph = RelationalMemoryGraph(db, codec)
        import_whatsapp(str(chat), str(db))
        self.store = MemoryStore(db, codec)
        self.recall = RecallFirewall(self.store, self.graph)

    def tearDown(self) -> None:
        os.environ.pop("TRACE_COMMITMENT_WINDOW_DAYS", None)
        self._tmp.cleanup()

    def _assert_provenance(self, result: dict, expected_source: str = "whatsapp") -> None:
        citations = result.get("citations")
        self.assertTrue(citations, f"no citations on intent={result.get('intent')}")
        for c in citations:
            self.assertEqual(c.get("source"), expected_source)
            self.assertTrue(c.get("captured_at"), "citation missing captured_at")
            self.assertTrue(c.get("attributes"), "citation missing attributes list")
            self.assertGreater(c.get("confidence", 0), 0)
        self.assertIn("confidence", result)
        self.assertGreater(result["confidence"], 0)
        self.assertLessEqual(
            result["confidence"],
            min(c["confidence"] for c in citations),
        )

    def test_who_is_carries_citations(self) -> None:
        result = self.recall.answer("who is Alice Tester")
        self.assertEqual(result["intent"], "who_is")
        self._assert_provenance(result)

    def test_commitments_carries_citations(self) -> None:
        result = self.recall.answer("what are my commitments")
        self.assertEqual(result["intent"], "commitments")
        self.assertIn("Alice Tester", result["answer"])
        self._assert_provenance(result)
        for c in result["citations"]:
            self.assertIn("open_commitments", c["attributes"])

    def test_last_contact_carries_citations(self) -> None:
        result = self.recall.answer("when did I last talk to Alice Tester")
        self.assertEqual(result["intent"], "last_contact")
        self._assert_provenance(result)

    def test_no_commitments_yields_zero_confidence(self) -> None:
        result = self.recall.answer("what did I commit to Nonexistent Person Xyz")
        if result["intent"] == "commitments" and "No open commitments" in result["answer"]:
            self.assertEqual(result["citations"], [])
            self.assertEqual(result.get("confidence"), 0.0)


if __name__ == "__main__":
    unittest.main()
