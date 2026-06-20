#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from artifact_provenance import provenance_matches, raw_source_sha256, source_fingerprint


class MemoryProvenanceTests(unittest.TestCase):
    def test_stale_or_foreign_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            with open(os.path.join(a, "kf_memory.json"), "w") as out:
                json.dump([{"t": 1, "caption": "clip a"}], out)
            with open(os.path.join(b, "kf_memory.json"), "w") as out:
                json.dump([{"t": 1, "caption": "clip b"}], out)
            artifact = {"_provenance": {"source_fingerprint": source_fingerprint(a)}}
            self.assertTrue(provenance_matches(artifact, a))
            self.assertFalse(provenance_matches(artifact, b))

            with open(os.path.join(a, "kf_memory.json"), "w") as out:
                json.dump([{"t": 2, "caption": "clip a changed"}], out)
            self.assertFalse(provenance_matches(artifact, a))

    def test_legacy_unversioned_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as memory:
            with open(os.path.join(memory, "kf_memory.json"), "w") as out:
                json.dump([], out)
            self.assertFalse(provenance_matches({"summary": "foreign facts"}, memory))

    def test_raw_capture_hash_is_part_of_artifact_identity(self):
        with tempfile.TemporaryDirectory() as memory:
            with open(os.path.join(memory, "kf_memory.json"), "w") as out:
                json.dump([{"t": 0, "caption": "same derived text"}], out)
            pack_path = os.path.join(memory, "evidence_pack.json")
            first_hash = "a" * 64
            with open(pack_path, "w") as out:
                json.dump({"source": {"sha256": first_hash}}, out)
            first = source_fingerprint(memory)
            self.assertEqual(raw_source_sha256(memory), first_hash)

            with open(pack_path, "w") as out:
                json.dump({"source": {"sha256": "b" * 64}}, out)
            self.assertNotEqual(first, source_fingerprint(memory))


if __name__ == "__main__":
    unittest.main()
