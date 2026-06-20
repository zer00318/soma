import json
import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from post_capture_identity import checkpoint_rows, job_run_id


class PostCaptureIdentityTests(unittest.TestCase):
    def test_raw_source_or_prompt_change_invalidates_resume(self):
        with tempfile.TemporaryDirectory() as memory:
            pack = os.path.join(memory, "evidence_pack.json")
            with open(pack, "w") as out:
                json.dump({"source": {"sha256": "a" * 64}}, out)
            first = job_run_id(memory, "entity", 1, "model", "prompt", {"cap": 10}, ["f1"])
            with open(pack, "w") as out:
                json.dump({"source": {"sha256": "b" * 64}}, out)
            second = job_run_id(memory, "entity", 1, "model", "prompt", {"cap": 10}, ["f1"])
            changed_prompt = job_run_id(
                memory, "entity", 1, "model", "new prompt", {"cap": 10}, ["f1"])
            self.assertNotEqual(first, second)
            self.assertNotEqual(second, changed_prompt)

    def test_checkpoint_loader_uses_only_matching_run(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "rows.ndjson")
            with open(path, "w") as out:
                out.write(json.dumps({"_run_id": "old", "frame": "a", "value": 1}) + "\n")
                out.write(json.dumps({"_run_id": "new", "frame": "a", "value": 2}) + "\n")
            self.assertEqual(checkpoint_rows(path, "new")["a"]["value"], 2)
            self.assertEqual(checkpoint_rows(path, "missing"), {})


if __name__ == "__main__":
    unittest.main()
