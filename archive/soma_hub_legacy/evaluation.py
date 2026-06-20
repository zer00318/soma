from __future__ import annotations

import json
import statistics
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from soma_hub.policy import SENSITIVE_PATTERNS
from soma_hub.service import SomaHub


@dataclass(frozen=True)
class RecallScenario:
    seed_text: str
    query: str
    expected_substring: str


@dataclass(frozen=True)
class RefusalScenario:
    seed_text: str
    query: str
    forbidden_substring: str


def run_default_evaluation(dataset_path: Path | None = None) -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        hub = SomaHub(Path(temp_dir))
        dataset = load_dataset(dataset_path) if dataset_path else load_default_dataset()
        return run_evaluation(hub, dataset)


def run_evaluation(hub: SomaHub, dataset: dict) -> dict:
    recall_scenarios = dataset["recall"]
    refusal_scenarios = dataset["refusal"]
    recall_hits = 0
    recall_latencies: list[float] = []
    refusal_hits = 0
    refusal_latencies: list[float] = []
    leakage_failures = 0

    for scenario in recall_scenarios:
        ingest_started = time.perf_counter()
        hub.ingest_text(scenario.seed_text)
        recall_latencies.append(time.perf_counter() - ingest_started)

        answer_started = time.perf_counter()
        answer = hub.chat(scenario.query)
        recall_latencies.append(time.perf_counter() - answer_started)
        if scenario.expected_substring in answer["answer"].lower():
            recall_hits += 1

    metadata = hub.metadata()
    for record in metadata["recent"]:
        if _contains_sensitive_leak(record["summary"]):
            leakage_failures += 1

    for scenario in refusal_scenarios:
        hub.ingest_text(scenario.seed_text)
        refusal_started = time.perf_counter()
        answer = hub.chat(scenario.query)
        refusal_latencies.append(time.perf_counter() - refusal_started)
        if answer["intent"] == "disallowed_extraction" and scenario.forbidden_substring not in answer["answer"]:
            refusal_hits += 1

    return {
        "dataset_name": dataset.get("name", "default"),
        "recall_accuracy": recall_hits / len(recall_scenarios),
        "refusal_accuracy": refusal_hits / len(refusal_scenarios),
        "pii_leakage_rate": leakage_failures / max(len(metadata["recent"]), 1),
        "ingest_and_answer_latency_ms_p50": round(_median_ms(recall_latencies + refusal_latencies), 2),
        "ingest_and_answer_latency_ms_p95": round(_p95_ms(recall_latencies + refusal_latencies), 2),
        "recall_cases": len(recall_scenarios),
        "refusal_cases": len(refusal_scenarios),
        "memory_total": hub.metadata()["total"],
    }


def load_default_dataset() -> dict:
    return load_dataset(Path(__file__).resolve().parent.parent / "evaluation" / "default_dataset.json")


def load_dataset(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        "name": raw.get("name", path.stem),
        "recall": [RecallScenario(**item) for item in raw.get("recall", [])],
        "refusal": [RefusalScenario(**item) for item in raw.get("refusal", [])],
    }


def _contains_sensitive_leak(text: str) -> bool:
    return any(pattern.search(text) for pattern in SENSITIVE_PATTERNS.values())


def _median_ms(samples: list[float]) -> float:
    return statistics.median(samples) * 1000 if samples else 0.0


def _p95_ms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = min(len(ordered) - 1, int(len(ordered) * 0.95))
    return ordered[index] * 1000
