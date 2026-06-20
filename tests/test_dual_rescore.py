from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_dual_rescore import (
    ClipSpec,
    MODEL_RE,
    _checkpoint_rows,
    command_for,
    assert_local_gemma,
    prepare_checkpoint,
    run_all,
)


class DualRescoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_spec(self, name: str, total: int = 2) -> ClipSpec:
        base = self.root / name
        memory_dir = base / "memory"
        memory_dir.mkdir(parents=True)
        questions = base / "questions.txt"
        questions.write_text("# frozen battery\n" + "\n".join(f"other: Q{i}" for i in range(1, total + 1)))
        gold = base / "gold.json"
        gold.write_text(json.dumps({"items": {
            str(i): {"q": f"Q{i}", "gold": f"A{i}"} for i in range(1, total + 1)
        }}))
        memory = memory_dir / "world_memory.json"
        memory.write_text('{"objects": []}')
        return ClipSpec(
            name=name,
            questions=questions,
            gold=gold,
            memory=memory,
            checkpoint=self.root / "checkpoints" / f"{name}.jsonl",
            status=self.root / "cockpit" / f"eval_live_{name}.json",
        )

    @staticmethod
    def complete_checkpoint(spec: ClipSpec, total: int = 2) -> None:
        spec.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {"i": i, "verdict": "correct" if i == 1 else "miss", "pending": False}
            for i in range(1, total + 1)
        ]
        spec.checkpoint.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    def test_two_lanes_are_queued_then_run_sequentially(self) -> None:
        walk = self.make_spec("walk")
        cold = self.make_spec("cold")
        seen = []

        def invoke(spec: ClipSpec, _command: list[str]) -> int:
            other = cold if spec.name == "walk" else walk
            seen.append((spec.name, json.loads(other.status.read_text())["state"]))
            self.complete_checkpoint(spec)
            return 0

        result = run_all(
            [walk, cold], "gemma3:12b-it-qat", Path("python"), Path("runner.py"),
            "test-run", self.root / "cockpit" / "dual_rescore.json", invoke=invoke,
        )

        self.assertEqual(result, 0)
        self.assertEqual(seen, [("walk", "queued"), ("cold", "complete")])
        self.assertEqual(json.loads(walk.status.read_text())["state"], "complete")
        self.assertEqual(json.loads(cold.status.read_text())["state"], "complete")
        batch = json.loads((self.root / "cockpit" / "dual_rescore.json").read_text())
        self.assertEqual(batch["state"], "complete")
        self.assertTrue(batch["local_only"])

    def test_resume_skips_complete_lane_and_keeps_partial_progress(self) -> None:
        walk = self.make_spec("walk")
        cold = self.make_spec("cold")
        self.complete_checkpoint(walk)
        cold.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        cold.checkpoint.write_text(json.dumps({"i": 1, "verdict": "wrong", "pending": False}) + "\n")
        invoked = []

        def invoke(spec: ClipSpec, _command: list[str]) -> int:
            invoked.append(spec.name)
            with spec.checkpoint.open("a") as handle:
                handle.write(json.dumps({"i": 2, "verdict": "correct", "pending": False}) + "\n")
            return 0

        result = run_all(
            [walk, cold], "gemma3:12b-it-qat", Path("python"), Path("runner.py"),
            "resume-run", self.root / "cockpit" / "dual_rescore.json", invoke=invoke,
        )

        self.assertEqual(result, 0)
        self.assertEqual(invoked, ["cold"])
        self.assertEqual(len(_checkpoint_rows(cold.checkpoint, 2)), 2)

    def test_failure_is_explicit_and_checkpoint_remains_resumable(self) -> None:
        walk = self.make_spec("walk")
        cold = self.make_spec("cold")

        def fail(spec: ClipSpec, _command: list[str]) -> int:
            spec.checkpoint.parent.mkdir(parents=True, exist_ok=True)
            spec.checkpoint.write_text(json.dumps({"i": 1, "verdict": "miss"}) + "\n")
            return 9

        result = run_all(
            [walk, cold], "gemma3:12b-it-qat", Path("python"), Path("runner.py"),
            "fail-run", self.root / "cockpit" / "dual_rescore.json", invoke=fail,
        )

        self.assertEqual(result, 9)
        failed = json.loads(walk.status.read_text())
        self.assertEqual(failed["state"], "failed")
        self.assertEqual(failed["done"], 1)
        self.assertTrue(failed["resumable"])
        self.assertEqual(json.loads(cold.status.read_text())["state"], "queued")

    def test_checkpoint_identity_prevents_mixed_runs(self) -> None:
        walk = self.make_spec("walk")
        prepare_checkpoint(walk, "fingerprint-a", "gemma3:12b-it-qat")
        self.complete_checkpoint(walk)
        with self.assertRaisesRegex(RuntimeError, "different inputs/model"):
            prepare_checkpoint(walk, "fingerprint-b", "gemma3:12b-it-qat")

    def test_answer_and_judge_models_are_in_command_and_checkpoint_identity(self) -> None:
        walk = self.make_spec("walk")
        prepare_checkpoint(walk, "fingerprint-a", "gemma3:12b-it-qat",
                           judge_model="gemma3:27b-it-qat")
        meta = json.loads(walk.checkpoint.with_suffix(".jsonl.meta.json").read_text())
        self.assertEqual(meta["answer_model"], "gemma3:12b-it-qat")
        self.assertEqual(meta["judge_model"], "gemma3:27b-it-qat")
        self.assertTrue(meta["models_independent"])
        command = command_for(walk, Path("python"), Path("runner"),
                              "gemma3:12b-it-qat", "gemma3:27b-it-qat")
        self.assertEqual(command[command.index("--judge-model") + 1], "gemma3:27b-it-qat")
        self.complete_checkpoint(walk)
        with self.assertRaisesRegex(RuntimeError, "different inputs/model"):
            prepare_checkpoint(walk, "fingerprint-a", "gemma3:12b-it-qat",
                               judge_model="gemma3:12b-it-qat")

    def test_later_error_invalidates_earlier_final_grade(self) -> None:
        walk = self.make_spec("walk", total=1)
        walk.checkpoint.parent.mkdir(parents=True)
        walk.checkpoint.write_text(
            json.dumps({"i": 1, "verdict": "correct"}) + "\n" +
            json.dumps({"i": 1, "verdict": "error", "needs_review": True}) + "\n"
        )
        self.assertEqual(_checkpoint_rows(walk.checkpoint, 1), {})

    def test_non_gemma_models_are_rejected_before_network_call(self) -> None:
        self.assertIsNotNone(MODEL_RE.fullmatch("gemma3:12b-it-qat"))
        with self.assertRaisesRegex(ValueError, "only local Gemma"):
            assert_local_gemma("gpt-remote")


if __name__ == "__main__":
    unittest.main()
