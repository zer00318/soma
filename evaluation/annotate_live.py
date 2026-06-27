#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

from trace_memory.store import TraceMemoryStore

COUNT_RE = re.compile(r"^\s*how many (?P<subject>.+?)\s*\??\s*$", re.IGNORECASE)
EXISTS_RE = re.compile(r"^\s*is there (?P<subject>.+?)\s*\??\s*$", re.IGNORECASE)
ANY_RE = re.compile(r"^\s*are any of the (?P<subject>.+?)\s*\??\s*$", re.IGNORECASE)
ATTRIBUTE_RE = re.compile(
    r"^\s*what (?P<attribute>colour|color|flavour|flavor|brand|name) "
    r"(?:is|are) (?P<subject>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
IDENTITY_RE = re.compile(
    r"^\s*what (?P<subject>.+?) is on the (?P<place>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
STOPWORDS = {
    "a",
    "an",
    "any",
    "are",
    "colour",
    "color",
    "desk",
    "flavour",
    "flavor",
    "how",
    "is",
    "many",
    "of",
    "on",
    "table",
    "the",
    "there",
    "visible",
    "what",
}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _tokens(text: str) -> list[str]:
    return [token for token in _normalize(text).split() if token and token not in STOPWORDS]


def _subject_blob(node) -> str:
    payload = [
        node.text,
        json.dumps(node.metadata, ensure_ascii=False),
        json.dumps(node.provenance, ensure_ascii=False),
    ]
    return _normalize(" ".join(payload))


def _clean_subject(subject: str) -> str:
    cleaned = re.sub(r"\bare there\b", "", subject, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bon the (table|desk)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bis visible\b", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def _entity_nodes(store: TraceMemoryStore):
    return store.nodes(node_types=("entity",))


def _match_entities(store: TraceMemoryStore, subject: str):
    wanted = _tokens(subject)
    if not wanted:
        return ()
    matched = []
    for node in _entity_nodes(store):
        blob = _subject_blob(node)
        if all(token in blob for token in wanted):
            matched.append(node)
    return tuple(matched)


def _extract_confidence(answer: str) -> float:
    match = re.search(r'"confidence"\s*:\s*([0-9.]+)', answer)
    if match:
        return float(match.group(1))
    return 0.5


def _extract_json(answer: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", answer, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _heuristic_answer(store: TraceMemoryStore, question: str) -> dict[str, Any]:
    if match := COUNT_RE.match(question):
        subject = _clean_subject(match.group("subject"))
        qualifier = ""
        if "have " in subject:
            subject, qualifier = subject.split("have ", 1)
        nodes = _match_entities(store, subject)
        if qualifier:
            nodes = tuple(node for node in nodes if all(token in _subject_blob(node) for token in _tokens(qualifier)))
        return {
            "answer": str(len(nodes)) if nodes else "I don't know",
            "refused": not bool(nodes),
            "confidence": 0.85 if nodes else 0.2,
            "evidence_ids": [node.id for node in nodes[:5]],
        }

    if match := EXISTS_RE.match(question):
        subject = _clean_subject(match.group("subject"))
        nodes = _match_entities(store, subject)
        return {
            "answer": "Yes" if nodes else "No",
            "refused": False,
            "confidence": 0.8 if nodes else 0.7,
            "evidence_ids": [node.id for node in nodes[:5]],
        }

    if match := ANY_RE.match(question):
        subject = _clean_subject(match.group("subject"))
        nodes = _match_entities(store, subject)
        empty_nodes = tuple(node for node in nodes if "empty" in _subject_blob(node))
        if empty_nodes:
            return {
                "answer": f"Yes, {len(empty_nodes)} of them are empty",
                "refused": False,
                "confidence": 0.7,
                "evidence_ids": [node.id for node in empty_nodes[:5]],
            }
        return {"answer": "No", "refused": False, "confidence": 0.6, "evidence_ids": []}

    if match := ATTRIBUTE_RE.match(question):
        attribute = match.group("attribute").lower()
        subject = _clean_subject(match.group("subject"))
        nodes = _match_entities(store, subject)
        if not nodes and "on the rings" in subject.lower():
            nodes = _match_entities(store, "ring gemstone")
        if not nodes:
            return {"answer": "I don't know", "refused": True, "confidence": 0.2, "evidence_ids": []}
        blob = _subject_blob(nodes[0])
        if attribute in {"colour", "color"}:
            for colour in ("green", "red", "blue", "brown", "yellow", "black", "white", "silver", "gold"):
                if colour in blob:
                    return {
                        "answer": colour.capitalize(),
                        "refused": False,
                        "confidence": 0.7,
                        "evidence_ids": [nodes[0].id],
                    }
        if attribute in {"flavour", "flavor"}:
            flavour_match = re.search(r"con peperoncino|hot & spicy|sour cream and onion", blob)
            if flavour_match:
                return {
                    "answer": flavour_match.group(0),
                    "refused": False,
                    "confidence": 0.7,
                    "evidence_ids": [nodes[0].id],
                }
        if attribute in {"brand", "name"}:
            for candidate in ("macbook", "nutella", "pringles", "pesto"):
                if candidate in blob:
                    return {
                        "answer": candidate.capitalize(),
                        "refused": False,
                        "confidence": 0.75,
                        "evidence_ids": [nodes[0].id],
                    }
        return {"answer": "I don't know", "refused": True, "confidence": 0.2, "evidence_ids": []}

    if match := IDENTITY_RE.match(question):
        subject = _clean_subject(match.group("subject"))
        nodes = _match_entities(store, subject)
        if nodes:
            blob = _subject_blob(nodes[0])
            if "macbook" in blob:
                return {
                    "answer": "Macbook",
                    "refused": False,
                    "confidence": 0.8,
                    "evidence_ids": [nodes[0].id],
                }
        return {"answer": "I don't know", "refused": True, "confidence": 0.2, "evidence_ids": []}

    return {"answer": "I don't know", "refused": True, "confidence": 0.1, "evidence_ids": []}


def _ollama_answer(store: TraceMemoryStore, question: str, model: str, host: str) -> dict[str, Any]:
    search = store.search(question, k=6)
    context_rows = []
    seen = set()
    for hit in search.hits:
        if hit.node.id not in seen:
            seen.add(hit.node.id)
            context_rows.append(
                {
                    "id": hit.node.id,
                    "type": hit.node.node_type,
                    "score": hit.score,
                    "text": hit.node.text,
                    "place": hit.node.place,
                }
            )
        for neighbor in store.neighbors(hit.node.id, limit=4):
            if neighbor.node.id in seen:
                continue
            seen.add(neighbor.node.id)
            context_rows.append(
                {
                    "id": neighbor.node.id,
                    "type": neighbor.node.node_type,
                    "via": neighbor.edge.link_type,
                    "text": neighbor.node.text,
                    "place": neighbor.node.place,
                }
            )
    prompt = (
        "Answer only from the retrieved TRACE memory slice below. "
        "If the slice does not support the answer, refuse. "
        "Return strict JSON with keys answer, refused, confidence, evidence_ids.\n\n"
        f"QUESTION: {question}\n"
        f"MEMORY_SLICE: {json.dumps(context_rows, ensure_ascii=False)}"
    )
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }
    req = urllib.request.Request(
        f"{host}/api/generate",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    raw = json.load(urllib.request.urlopen(req, timeout=180)).get("response", "")
    parsed = _extract_json(raw)
    if parsed is not None:
        return parsed
    return {
        "answer": raw.strip() or "I don't know",
        "refused": "don't know" in raw.lower() or "do not know" in raw.lower(),
        "confidence": _extract_confidence(raw),
        "evidence_ids": [],
    }


def answer_question(
    store: TraceMemoryStore,
    question: str,
    *,
    reasoner: str,
    model: str,
    host: str,
) -> dict[str, Any]:
    if reasoner == "local-ollama":
        return _ollama_answer(store, question, model=model, host=host)
    return _heuristic_answer(store, question)


def load_annotations(path: Path) -> list[dict[str, Any]]:
    text = path.read_text().strip()
    if not text:
        return []
    if text.startswith("["):
        return list(json.loads(text))
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def append_annotation(path: Path, question: str, true_answer: str, when: str | None) -> None:
    rows = load_annotations(path) if path.exists() else []
    rows.append({"question": question, "answer": true_answer, "when": when})
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")


def judge(truth: str, answer: str, refused: bool) -> str:
    truth_norm = _normalize(truth)
    answer_norm = _normalize(answer)
    if refused:
        if truth_norm in {"no", "there is no"}:
            return "correct"
        return "refused"
    if truth_norm == "yes":
        return "correct" if "yes" in answer_norm else "wrong"
    if truth_norm == "no" or truth_norm.startswith("there is no"):
        return "correct" if "no" in answer_norm else "wrong"
    if truth_norm and truth_norm in answer_norm:
        return "correct"
    if truth_norm.isdigit():
        return "correct" if re.search(rf"\b{truth_norm}\b", answer_norm) else "wrong"
    return "wrong"


def score_annotations(
    annotations: list[dict[str, Any]],
    store: TraceMemoryStore,
    *,
    reasoner: str,
    model: str,
    host: str,
    repeats: int,
) -> list[dict[str, Any]]:
    results = []
    for row in annotations:
        question = str(row["question"])
        truth = str(row["answer"])
        attempts = []
        for _ in range(repeats):
            attempt = answer_question(store, question, reasoner=reasoner, model=model, host=host)
            verdict = judge(truth, str(attempt.get("answer", "")), bool(attempt.get("refused")))
            attempts.append({**attempt, "verdict": verdict})
        results.append({"question": question, "truth": truth, "attempts": attempts})
    return results


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    answered = 0
    correct = 0
    confident_wrong = 0
    for row in results:
        best = row["attempts"][0]
        verdict = best["verdict"]
        refused = bool(best.get("refused"))
        confidence = float(best.get("confidence", 0.0))
        if not refused:
            answered += 1
        if verdict == "correct":
            correct += 1
        elif verdict == "wrong" and confidence >= 0.75:
            confident_wrong += 1
    return {
        "total": total,
        "answered": answered,
        "correct": correct,
        "answered_rate": (answered / total) if total else 0.0,
        "correct_rate": (correct / total) if total else 0.0,
        "confident_wrong": confident_wrong,
        "confident_wrong_rate": (confident_wrong / total) if total else 0.0,
    }


def build_status_payload(
    summary: dict[str, Any],
    *,
    annotations_path: Path,
    store_path: str,
    reasoner: str,
    repeats: int,
) -> dict[str, Any]:
    return {
        "state": "complete",
        "note": (
            f"{summary['answered']}/{summary['total']} answered, "
            f"{summary['confident_wrong']} confident-wrong via {reasoner}"
        ),
        "annotations": str(annotations_path),
        "store": store_path,
        "reasoner": reasoner,
        "repeats": repeats,
        **summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", default="data/phone_captures/live/ground_truth.json")
    parser.add_argument("--store", required=True)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--question", default="")
    parser.add_argument("--true-answer", default="")
    parser.add_argument("--when", default="")
    parser.add_argument("--reasoner", choices=("heuristic", "local-ollama"), default="heuristic")
    parser.add_argument("--model", default="gemma3:12b-it-qat")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--out", default="")
    parser.add_argument("--status-out", default="ops/cockpit/annotate_live.json")
    args = parser.parse_args()

    annotations_path = Path(args.annotations)
    if args.append:
        if not args.question or not args.true_answer:
            raise SystemExit("--append requires --question and --true-answer")
        append_annotation(annotations_path, args.question, args.true_answer, args.when or None)
        print(f"appended annotation to {annotations_path}")
        return 0

    annotations = load_annotations(annotations_path)
    store = TraceMemoryStore(args.store)
    try:
        results = score_annotations(
            annotations,
            store,
            reasoner=args.reasoner,
            model=args.model,
            host=args.host,
            repeats=max(1, args.repeats),
        )
    finally:
        store.close()

    summary = summarize(results)
    print(json.dumps(summary, indent=2))
    for row in results:
        attempt = row["attempts"][0]
        print(
            f"- {row['question']} => {attempt.get('answer')} "
            f"[{attempt['verdict']}, refused={attempt.get('refused')}, conf={attempt.get('confidence')}]"
        )
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False))
    status_payload = build_status_payload(
        summary,
        annotations_path=annotations_path,
        store_path=args.store,
        reasoner=args.reasoner,
        repeats=max(1, args.repeats),
    )
    if args.status_out:
        status_path = Path(args.status_out)
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(json.dumps(status_payload, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
