from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from evaluation import auto_score as score
from evaluation import run_live


class StructuralEvaluatorTest(unittest.TestCase):
    def test_explicit_epistemic_gold_rewards_honest_uncertainty(self) -> None:
        decision = score.grade_answer(
            "Is the phone connected?",
            "Could NOT confirm: no phone was visible, so there is insufficient context to claim it.",
            ["couldn't confirm", "insufficient"], ["yes connected"],
            "I can't confirm that from my memory.", "judge-model",
        )
        self.assertEqual(decision.verdict, "correct")
        self.assertEqual(decision.method, "structural_epistemic_gold")

    def test_positive_gold_keeps_refusal_as_miss(self) -> None:
        decision = score.grade_answer(
            "Was there a child?", "Yes, a child yelled.", ["child"], ["no child"],
            "I couldn't determine whether it was a child.", "judge-model",
        )
        self.assertEqual(decision.verdict, "miss")

    def test_refusal_with_accept_token_does_not_score_correct(self) -> None:
        decision = score.grade_answer(
            "How many calories were in the breakfast I ate, and what did I eat?",
            "Scrambled eggs, diced breakfast potatoes/home fries, and ketchup; roughly 495-695 kcal total.",
            ["eggs", "scrambled", "potatoes", "home fries", "ketchup", "500", "600", "700", "495", "695", "calorie"],
            ["pancakes", "cereal", "1500", "2000 calories", "pizza", "salad"],
            "The dossier mentions BREAKFAST multiple times, but it does not specify the contents "
            "of the breakfast or its calorie count. Therefore, I cannot answer this question.",
            "judge-model",
        )
        self.assertEqual(decision.verdict, "miss")
        self.assertEqual(decision.method, "structural_refusal")

    def test_reject_phrase_dominates_broad_accept_token(self) -> None:
        decision = score.deterministic_grade(
            "Yes, a child yelled.", ["child"], ["no child"], "No child was present."
        )
        self.assertEqual(decision.verdict, "wrong")

    def test_literal_accept_is_deterministic_and_timestamp_numbers_do_not_match(self) -> None:
        accepted = score.deterministic_grade(
            "White Crocs.", ["white crocs", "crocs"], ["boots"],
            "I wore white Crocs (seen at t=12.3s).",
        )
        self.assertEqual(accepted.verdict, "correct")
        self.assertFalse(score._cue_present("I saw two posters at t=63.5s", "3"))

    def test_clearly_different_long_quote_is_wrong(self) -> None:
        decision = score.deterministic_grade(
            'The draft began "You are taking over TRACE, a perception-to-text project."',
            ["taking over trace"], [],
            'The draft was "I am outside and need a prompt for a completely new chat."',
        )
        self.assertEqual(decision.verdict, "wrong")
        self.assertEqual(decision.method, "structural_quoted_mismatch")

    def test_judge_runtime_and_parse_failures_are_explicit_errors(self) -> None:
        with mock.patch.object(score, "_request_judge", side_effect=TimeoutError("timed out")):
            decision = score.grade_answer("Q", "gold", ["semantic cue"], [],
                                          "A committed paraphrase.", "judge-27b")
        self.assertEqual(decision.verdict, "error")
        self.assertIn("timed out", decision.error)
        self.assertEqual(decision.judge_model, "judge-27b")

        with mock.patch.object(score, "_request_judge", return_value="Probably correct."):
            decision = score.grade_answer("Q", "gold", ["semantic cue"], [],
                                          "A committed paraphrase.", "judge-27b")
        self.assertEqual(decision.verdict, "error")
        self.assertEqual(decision.method, "judge_parse_error")
        self.assertEqual(decision.judge_raw, "Probably correct.")

    def test_judge_cannot_neutralize_non_refusal_as_miss(self) -> None:
        with mock.patch.object(score, "_request_judge", return_value="miss"):
            decision = score.grade_answer("Which poster?", "Meissner", ["meissner"], [],
                                          "It was a starry-night poster.", "judge-27b")
        self.assertEqual(decision.verdict, "needs_review")
        self.assertEqual(decision.method, "judge_contract_conflict")

    def test_valid_independent_judge_decision_records_provenance(self) -> None:
        with mock.patch.object(score, "_request_judge", return_value="wrong"):
            decision = score.grade_answer("Q", "gold", ["semantic cue"], [],
                                          "A committed paraphrase.", "judge-27b")
        self.assertEqual(decision.verdict, "wrong")
        self.assertEqual(decision.judge_model, "judge-27b")
        self.assertEqual(decision.judge_raw, "wrong")

    def test_live_runner_persists_needs_review_instead_of_miss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            questions = root / "questions.txt"
            gold = root / "gold.json"
            memory = root / "world_memory.json"
            checkpoint = root / "checkpoint.jsonl"
            status = root / "status.json"
            questions.write_text("objects: Which poster was it?\n")
            gold.write_text(json.dumps({"items": {"1": {
                "q": "Which poster was it?", "gold": "The Meissner poster.",
                "accept": ["meissner"], "reject": [],
            }}}))
            memory.write_text("[]")
            argv = [
                "run_live.py", "--questions", str(questions), "--gold", str(gold),
                "--memory", str(memory), "--checkpoint", str(checkpoint),
                "--status", str(status), "--model", "answer-12b",
                "--judge-model", "judge-27b",
            ]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(run_live.ask_home, "ask", return_value={
                        "answer": "It was a starry-night advertisement."}), \
                    mock.patch.object(run_live.A, "_request_judge", return_value="miss"), \
                    mock.patch("cockpit_beat.beat"):
                result = run_live.main()
            self.assertEqual(result, 3)
            row = json.loads(checkpoint.read_text().strip())
            self.assertEqual(row["verdict"], "needs_review")
            self.assertTrue(row["needs_review"])
            self.assertEqual(row["answer_model"], "answer-12b")
            self.assertEqual(row["judge_model"], "judge-27b")
            live = json.loads(status.read_text())
            self.assertEqual(live["state"], "needs_review")
            self.assertEqual(live["done"], 0)

    def test_live_runner_turns_answer_timeout_into_miss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            questions = root / "questions.txt"
            gold = root / "gold.json"
            memory = root / "world_memory.json"
            checkpoint = root / "checkpoint.jsonl"
            status = root / "status.json"
            questions.write_text("objects: Which poster was it?\n")
            gold.write_text(json.dumps({"items": {"1": {
                "q": "Which poster was it?", "gold": "The Meissner poster.",
                "accept": ["meissner"], "reject": [],
            }}}))
            memory.write_text("[]")
            argv = [
                "run_live.py", "--questions", str(questions), "--gold", str(gold),
                "--memory", str(memory), "--checkpoint", str(checkpoint),
                "--status", str(status), "--model", "answer-12b",
                "--judge-model", "judge-27b", "--answer-timeout", "1",
            ]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(run_live, "_query_with_timeout",
                                      side_effect=TimeoutError("answer timed out after 1s")), \
                    mock.patch("cockpit_beat.beat"):
                result = run_live.main()
            self.assertEqual(result, 0)
            row = json.loads(checkpoint.read_text().strip())
            self.assertEqual(row["verdict"], "miss")
            self.assertEqual(row["grading"]["method"], "answer_timeout")
            live = json.loads(status.read_text())
            self.assertEqual(live["miss"], 1)


if __name__ == "__main__":
    unittest.main()
