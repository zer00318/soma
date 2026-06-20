#!/usr/bin/env python3
"""Regression tests for strict, clip-separated critic inputs."""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import objective_critic as critic  # noqa: E402


class ObjectiveCriticInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.questions = root / "questions.txt"
        self.gold = root / "gold.json"
        self.score = root / "score.jsonl"
        self.questions.write_text("objects: First question?\ntext: Second question?\n")
        self.gold.write_text(json.dumps({"items": {
            "1": {"gold": "one", "accept": ["one"]},
            "2": {"gold": "two", "accept": ["two"]},
        }}))
        self.profile = critic.ClipProfile(
            "walk", self.questions, self.gold, root / "critic.json", "test walk"
        )
        self._write_rows([
            {"i": 1, "question": "First question?", "answer": "one", "verdict": "correct"},
            {"i": 2, "question": "Second question?", "answer": "unsure", "verdict": "miss"},
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def _write_rows(self, rows):
        self.score.write_text("".join(json.dumps(row) + "\n" for row in rows))
        # Score must be newer than its frozen inputs.
        future = max(self.questions.stat().st_mtime, self.gold.stat().st_mtime) + 2
        os.utime(self.score, (future, future))

    def test_valid_checkpoint_has_hash_pinned_provenance(self):
        result = critic.prepare_run(self.profile, self.score, 24, now=self.score.stat().st_mtime + 10)
        self.assertEqual(result["evidence"]["current"]["ras"], 50.0)
        self.assertEqual(result["provenance"]["clip"], "walk")
        self.assertEqual(len(result["provenance"]["scoreboard"]["sha256"]), 64)

    def test_rejects_checkpoint_from_other_clip_by_question_identity(self):
        self._write_rows([
            {"i": 1, "question": "Whose lectures was I listening to?", "answer": "x",
             "verdict": "miss"},
            {"i": 2, "question": "Second question?", "answer": "x", "verdict": "miss"},
        ])
        with self.assertRaisesRegex(critic.InputError, "another clip"):
            critic.prepare_run(self.profile, self.score, 24, now=self.score.stat().st_mtime + 1)

    def test_rejects_incomplete_or_duplicate_checkpoint(self):
        self._write_rows([
            {"i": 1, "question": "First question?", "answer": "x", "verdict": "miss"},
        ])
        with self.assertRaisesRegex(critic.InputError, "incomplete"):
            critic.prepare_run(self.profile, self.score, 24, now=self.score.stat().st_mtime + 1)

        self._write_rows([
            {"i": 1, "question": "First question?", "answer": "x", "verdict": "miss"},
            {"i": 1, "question": "First question?", "answer": "x", "verdict": "miss"},
        ])
        with self.assertRaisesRegex(critic.InputError, "duplicate"):
            critic.prepare_run(self.profile, self.score, 24, now=self.score.stat().st_mtime + 1)

    def test_rejects_malformed_line_instead_of_skipping_it(self):
        self.score.write_text('{"i": 1}\nnot json\n')
        with self.assertRaisesRegex(critic.InputError, "malformed"):
            critic.prepare_run(self.profile, self.score, 24, now=time.time())

    def test_rejects_stale_checkpoint(self):
        now = self.score.stat().st_mtime + 25 * 3600
        with self.assertRaisesRegex(critic.InputError, "stale"):
            critic.prepare_run(self.profile, self.score, 24, now=now)

    def test_rejects_score_created_before_changed_gold(self):
        newer = self.score.stat().st_mtime + 5
        os.utime(self.gold, (newer, newer))
        with self.assertRaisesRegex(critic.InputError, "predates scoring inputs"):
            critic.prepare_run(self.profile, self.score, 24, now=newer + 1)

    def test_parse_verdict_requires_full_contract(self):
        good = {
            "doing_it_right": "mixed", "headline": "Measured but weak",
            "whats_real": [], "whats_suspect": [], "biggest_risks": [],
            "course_corrections": [], "plain_english_for_founder": "Keep testing.",
        }
        self.assertEqual(critic._parse_verdict(json.dumps(good)), good)
        del good["course_corrections"]
        self.assertIsNone(critic._parse_verdict(json.dumps(good)))

    def test_failed_fresh_attempt_clears_old_verdict(self):
        self.profile.out.write_text(json.dumps({"state": "complete", "verdict": {"old": True}}))
        prepared = critic.prepare_run(
            self.profile, self.score, 24, now=self.score.stat().st_mtime + 10
        )
        with mock.patch.object(critic, "_gen", side_effect=RuntimeError("local model down")):
            self.assertFalse(critic._run_one(prepared, "test-27b", 1))
        output = json.loads(self.profile.out.read_text())
        self.assertEqual(output["state"], "failed")
        self.assertNotIn("verdict", output)
        self.assertEqual(output["input_provenance"]["clip"], "walk")


if __name__ == "__main__":
    unittest.main()
