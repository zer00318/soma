#!/usr/bin/env python3
"""Temporal same-event relations over structured entity-capture rows.

The capture schema binds OCR to the object it was printed on, but every frame is
otherwise independent.  This module turns those rows into short object/person
episodes without inventing ownership:

* OCR variants on one object type in a continuous window are grouped together.
* Incompatible reads remain separate conflict groups with frame provenance.
* Text attached to an object is ``contains_text`` evidence for that object.
* Text near a person is only ``same_episode`` evidence, never proof they own/wore it.
* A focused query never borrows text from a temporally separate episode.

CPU-only and deterministic. No clip names, question templates, or model calls.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable


EPISODE_GAP_SECONDS = 2.0
COOCCURRENCE_SECONDS = 0.8

_STOP = set(
    "a an the this that what which who whose was were is are did do does on in at of to "
    "near next beside by with from name named text word words writing written read says said "
    "person people object item thing visible shown show me my i he she they it".split()
)
_COLORS = set(
    "red orange yellow green blue purple pink black white gray grey brown beige tan navy teal "
    "maroon cream khaki olive gold silver".split()
)
_OBJECT_ALIASES = {
    "posters": "poster", "signs": "sign", "screens": "screen",
    "t-shirt": "shirt", "tshirt": "shirt", "tee": "shirt",
}
_TEXT_SURFACE_HEADS = {"poster", "sign", "screen", "board", "display", "placard", "banner"}


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_text(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(v) for v in value)
    return str(value).strip()


def _normalize(value) -> str:
    raw = unicodedata.normalize("NFKD", _text(value)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", raw.lower())).strip()


def _tokens(value) -> set[str]:
    return {t for t in _normalize(value).split() if len(t) > 1 and t not in _STOP}


def canonical_object_type(value) -> str:
    """Stable object noun for loose capture labels such as ``blue wall poster``."""
    norm = _normalize(value)
    if not norm:
        return "object"
    toks = [t for t in norm.split() if t not in {"a", "an", "the"} and t not in _COLORS]
    if not toks:
        toks = norm.split()
    # Preserve useful display compounds while removing incidental adjectives.
    if len(toks) >= 2 and toks[-1] in {"screen", "sign", "tag", "reader"}:
        key = " ".join(toks[-2:])
    else:
        key = toks[-1]
    key = _OBJECT_ALIASES.get(key, key)
    if key.endswith("s") and len(key) > 4 and not key.endswith("ss"):
        key = key[:-1]
    return key


def _token_compatible(a: str, b: str) -> bool:
    if a == b:
        return True
    if len(a) == 1 or len(b) == 1:
        return a[0] == b[0]
    return len(a) >= 4 and len(b) >= 4 and a[0] == b[0] and SequenceMatcher(None, a, b).ratio() >= 0.72


def ocr_variants_match(a: str, b: str) -> bool:
    """Conservative OCR equivalence; short differing codes remain conflicts."""
    aa, bb = _normalize(a), _normalize(b)
    if not aa or not bb:
        return False
    if aa == bb:
        return True
    at, bt = aa.split(), bb.split()
    if len(at) == len(bt) and all(_token_compatible(x, y) for x, y in zip(at, bt)):
        return True
    aset, bset = set(at), set(bt)
    overlap = len(aset & bset) / max(1, len(aset | bset))
    return overlap >= 0.6 and min(len(aa), len(bb)) >= 5


def _provenance(row: dict, row_index: int, item_index: int) -> dict:
    return {
        "t": row.get("t"),
        "frame": row.get("frame", ""),
        "row_index": row_index,
        "item_index": item_index,
    }


def _add_text_group(episode: dict, value: str, provenance: dict) -> None:
    if not _normalize(value):
        return
    for group in episode["text_groups"]:
        if any(ocr_variants_match(value, variant["value"]) for variant in group["variants"]):
            variant = next((v for v in group["variants"] if _normalize(v["value"]) == _normalize(value)), None)
            if variant is None:
                variant = {"value": value, "provenance": []}
                group["variants"].append(variant)
            variant["provenance"].append(provenance)
            if len(value) > len(group["canonical"]):
                group["canonical"] = value
            return
    episode["text_groups"].append({
        "group_id": len(episode["text_groups"]),
        "canonical": value,
        "variants": [{"value": value, "provenance": [provenance]}],
    })


def _person_blob(person: dict) -> str:
    return " ".join([
        _text(person.get("appearance")), _text(person.get("clothing")),
        _text(person.get("accessories")), _text(person.get("position")),
    ]).strip()


def _person_similarity(a: dict, b: dict) -> float:
    aa, bb = _tokens(_person_blob(a)), _tokens(_person_blob(b))
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def _near(times_a: Iterable[float], times_b: Iterable[float], window: float) -> bool:
    return any(abs(a - b) <= window for a in times_a for b in times_b)


def _same_focus_family(key: str, wanted: set[str]) -> bool:
    """Allow a noisy poster/sign label to be recovered by distinctive episode context."""
    head = key.split()[-1]
    wanted_heads = {item.split()[-1] for item in wanted}
    return bool(head in _TEXT_SURFACE_HEADS and wanted_heads & _TEXT_SURFACE_HEADS)


def _object_episode_evidence(ep: dict) -> str:
    """All evidence that truly belongs to, or co-occurs with, this one episode."""
    parts = list(ep.get("labels") or [])
    for group in ep.get("text_groups") or []:
        parts.append(group.get("canonical", ""))
        parts.extend(v.get("value", "") for v in group.get("variants") or [])
    parts.extend(p.get("descriptor", "") for p in ep.get("cooccurring_people") or [])
    for other in ep.get("cooccurring_objects") or []:
        parts.append(other.get("object_type", ""))
        parts.extend(other.get("labels") or [])
        for group in other.get("text_groups") or []:
            parts.append(group.get("canonical", ""))
            parts.extend(v.get("value", "") for v in group.get("variants") or [])
    return " ".join(parts)


def _context_match_score(context_tokens: set[str], evidence_tokens: set[str]) -> int:
    """Count distinctive context tokens with conservative OCR/spelling tolerance."""
    return sum(
        1 for wanted in context_tokens
        if any(_token_compatible(wanted, observed) for observed in evidence_tokens)
    )


def _temporal_components(episodes: list[dict], gap: float) -> list[list[dict]]:
    components: list[list[dict]] = []
    for episode in sorted(episodes, key=lambda ep: (ep["start"], ep["end"])):
        if components and episode["start"] <= max(ep["end"] for ep in components[-1]) + gap:
            components[-1].append(episode)
        else:
            components.append([episode])
    return components


def _merge_query_component(component: list[dict]) -> dict:
    """One same-event view over separately captured text fragments on a surface."""
    representative = max(
        component,
        key=lambda ep: (ep["end"] - ep["start"], len(ep["sightings"]),
                        max((len(g["canonical"]) for g in ep["text_groups"]), default=0)),
    )
    merged = dict(representative)
    merged["start"] = min(ep["start"] for ep in component)
    merged["end"] = max(ep["end"] for ep in component)
    merged["labels"] = sorted({label for ep in component for label in ep.get("labels") or []})
    merged["sightings"] = [s for ep in component for s in ep.get("sightings") or []]
    merged["text_groups"] = [g for ep in component for g in ep.get("text_groups") or []]
    merged["conflicts"] = [c for ep in component for c in ep.get("conflicts") or []]
    merged["cooccurring_people"] = [
        p for ep in component for p in ep.get("cooccurring_people") or []
    ]
    merged["cooccurring_objects"] = [
        obj for ep in component for obj in ep.get("cooccurring_objects") or []
        if obj.get("episode_id") not in {member["episode_id"] for member in component}
    ]
    merged["component_episode_ids"] = [ep["episode_id"] for ep in component]
    return merged


def build_relation_index(
    rows: list[dict],
    episode_gap: float = EPISODE_GAP_SECONDS,
    cooccurrence_window: float = COOCCURRENCE_SECONDS,
) -> dict:
    """Build object/person episodes plus auditable same-event relations."""
    valid = [
        (i, row) for i, row in enumerate(rows or [])
        if isinstance(row, dict) and row.get("parse_ok") is not False
        and isinstance(row.get("t"), (int, float))
    ]
    valid.sort(key=lambda pair: (pair[1]["t"], pair[0]))

    object_episodes: list[dict] = []
    by_object: dict[str, list[dict]] = {}
    for row_index, row in valid:
        t = float(row["t"])
        for item_index, obj in enumerate(row.get("text_objects") or []):
            if not isinstance(obj, dict):
                continue
            label = _text(obj.get("object") or obj.get("name"))
            key = canonical_object_type(label)
            value = _text(obj.get("logo_or_text") or obj.get("text") or obj.get("logo"))
            candidates = [
                ep for ep in by_object.get(key, [])
                if 0 <= t - ep["end"] <= episode_gap and t != ep["end"]
            ]
            compatible = [
                ep for ep in candidates
                if not value or any(
                    ocr_variants_match(value, group["canonical"])
                    for group in ep["text_groups"]
                )
            ]
            if compatible:
                episode = max(compatible, key=lambda ep: ep["end"])
            elif len(candidates) == 1:
                # Temporal continuity says it may be the same surface, but incompatible OCR must
                # remain a visible conflict rather than being averaged into one answer.
                episode = candidates[0]
            else:
                episode = {
                    "episode_id": f"object:{key}:{len(by_object.get(key, []))}",
                    "focus_type": "object", "focus_key": key, "labels": [],
                    "start": t, "end": t, "sightings": [], "text_groups": [],
                    "cooccurring_people": [], "cooccurring_objects": [], "conflicts": [],
                }
                by_object.setdefault(key, []).append(episode)
                object_episodes.append(episode)
            provenance = _provenance(row, row_index, item_index)
            episode["start"] = min(episode["start"], t)
            episode["end"] = max(episode["end"], t)
            if label and label not in episode["labels"]:
                episode["labels"].append(label)
            episode["sightings"].append({"t": t, "label": label, "text": value,
                                         "provenance": provenance})
            _add_text_group(episode, value, provenance)

    person_episodes: list[dict] = []
    for row_index, row in valid:
        t = float(row["t"])
        used: set[str] = set()
        for item_index, person in enumerate(row.get("persons") or []):
            if not isinstance(person, dict):
                continue
            candidates = [
                ep for ep in person_episodes
                if ep["episode_id"] not in used and 0 <= t - ep["end"] <= episode_gap
                and t != ep["end"]
            ]
            scored = [(max((_person_similarity(person, s["person"]) for s in ep["sightings"][-3:]),
                           default=0.0), ep) for ep in candidates]
            score, episode = max(scored, default=(0.0, None), key=lambda pair: pair[0])
            if episode is None or score < 0.25:
                episode = {
                    "episode_id": f"person:{len(person_episodes)}", "focus_type": "person",
                    "focus_key": "person", "start": t, "end": t, "sightings": [],
                    "cooccurring_objects": [],
                }
                person_episodes.append(episode)
            episode["start"] = min(episode["start"], t)
            episode["end"] = max(episode["end"], t)
            episode["sightings"].append({
                "t": t, "person": person, "descriptor": _person_blob(person),
                "provenance": _provenance(row, row_index, item_index),
            })
            used.add(episode["episode_id"])

    for obj in object_episodes:
        obj_times = [s["t"] for s in obj["sightings"]]
        obj["cooccurring_people"] = [
            {"episode_id": person["episode_id"],
             "descriptor": max((s["descriptor"] for s in person["sightings"]), key=len, default="person"),
             "times": [s["t"] for s in person["sightings"]]}
            for person in person_episodes
            if _near(obj_times, [s["t"] for s in person["sightings"]], cooccurrence_window)
        ]
        obj["cooccurring_objects"] = [
            {"episode_id": other["episode_id"], "object_type": other["focus_key"],
             "labels": other["labels"], "text_groups": other["text_groups"]}
            for other in object_episodes
            if other["episode_id"] != obj["episode_id"]
            and _near(obj_times, [s["t"] for s in other["sightings"]], cooccurrence_window)
        ]
        if len(obj["text_groups"]) > 1:
            obj["conflicts"].append({
                "kind": "incompatible_text_groups",
                "values": [g["canonical"] for g in obj["text_groups"]],
                "provenance": [v["provenance"] for g in obj["text_groups"] for v in g["variants"]],
            })

    for person in person_episodes:
        person_times = [s["t"] for s in person["sightings"]]
        person["cooccurring_objects"] = [
            {"episode_id": obj["episode_id"], "object_type": obj["focus_key"],
             "text_groups": obj["text_groups"], "conflicts": obj["conflicts"]}
            for obj in object_episodes
            if _near(person_times, [s["t"] for s in obj["sightings"]], cooccurrence_window)
        ]

    return {
        "schema": "same_event_relations.v1", "episode_gap_seconds": episode_gap,
        "cooccurrence_seconds": cooccurrence_window,
        "object_episodes": object_episodes, "person_episodes": person_episodes,
    }


def query_focus(index: dict, focus: str, limit: int = 4) -> dict:
    """Return text relations for a focus item, never crossing episode boundaries."""
    qtokens = _tokens(focus)
    objects = index.get("object_episodes") or []
    object_keys = {ep["focus_key"] for ep in objects}
    wanted_keys = {key for key in object_keys if key in qtokens or _tokens(key) & qtokens}

    if wanted_keys:
        direct_candidates = [ep for ep in objects if ep["focus_key"] in wanted_keys]
        candidates = [
            ep for ep in objects
            if ep["focus_key"] in wanted_keys or _same_focus_family(ep["focus_key"], wanted_keys)
        ]
        focus_tokens = set().union(*(_tokens(key) for key in wanted_keys))
        context_tokens = qtokens - focus_tokens
        scored = []
        for ep in candidates:
            context_overlap = _context_match_score(
                context_tokens, _tokens(_object_episode_evidence(ep)))
            scored.append((context_overlap, ep))
        max_context = max((score for score, _ in scored), default=0)
        if not context_tokens or max_context == 0:
            # A generic type hit is not enough to choose a name-bearing surface. Preserve the
            # direct alternatives for inspection, but make the binding explicitly non-answerable.
            return {"focus_type": "object", "focus": sorted(wanted_keys),
                    "binding": "ambiguous" if direct_candidates else "none",
                    "episodes": direct_candidates[:limit]}
        matched = [ep for score, ep in scored if score == max_context and score > 0]
        components = _temporal_components(matched, float(index.get("cooccurrence_seconds") or COOCCURRENCE_SECONDS))
        selected = [_merge_query_component(component) for component in components[:limit]]
        ambiguous = len(selected) != 1 or any(ep.get("conflicts") for ep in selected)
        return {"focus_type": "object", "focus": sorted(wanted_keys),
                "binding": "ambiguous" if ambiguous else "bound", "episodes": selected}

    people = index.get("person_episodes") or []
    scored_people = []
    for ep in people:
        descriptor = " ".join(s["descriptor"] for s in ep["sightings"])
        score = len(_tokens(descriptor) & qtokens)
        if score:
            scored_people.append((score, ep))
    if not scored_people:
        return {"focus_type": None, "focus": [], "binding": "none", "episodes": []}
    best = max(score for score, _ in scored_people)
    selected = [ep for score, ep in scored_people if score == best][:limit]
    return {"focus_type": "person", "focus": ["person"],
            "binding": "ambiguous" if len(selected) != 1 else "bound", "episodes": selected}


def compact_relation_summary(rows: list[dict], question: str, limit: int = 4) -> str:
    """Question-focused dossier block with explicit binding strength and provenance."""
    result = query_focus(build_relation_index(rows), question, limit=limit)
    if not result["episodes"]:
        return ""
    lines = ["=== SAME-EVENT RELATIONS (temporal binding; conflicts preserved) ==="]
    for ep in result["episodes"]:
        span = f"t={ep['start']:.1f}-{ep['end']:.1f}s"
        if result["focus_type"] == "object":
            groups = ep.get("text_groups") or []
            reads = []
            for group in groups:
                variants = sorted({v["value"] for v in group["variants"]})
                times = sorted({p["t"] for v in group["variants"] for p in v["provenance"]})
                reads.append(f'"{group["canonical"]}" variants={variants} at {times}')
            state = (
                "AMBIGUOUS"
                if result.get("binding") == "ambiguous" or ep.get("conflicts")
                else "BOUND"
            )
            line = f"[{span}] FOCUS OBJECT {ep['focus_key']}: {state} contains_text "
            line += "; ".join(reads[:6]) if reads else "(no readable text)"
            people = [p["descriptor"][:140] for p in ep.get("cooccurring_people") or []]
            if people:
                line += "; SAME EPISODE people: " + " | ".join(people[:3])
            others = []
            for other in ep.get("cooccurring_objects") or []:
                texts = [g["canonical"] for g in other.get("text_groups") or []]
                label = other["object_type"]
                if texts:
                    label += " (" + " | ".join(texts[:2]) + ")"
                others.append(label)
            others = sorted(set(others))
            if others:
                line += "; SAME EPISODE objects: " + ", ".join(others[:6])
            if ep.get("conflicts"):
                line += "; CONFLICT preserved - do not choose one text without more evidence"
        else:
            descriptor = max((s["descriptor"] for s in ep["sightings"]), key=len, default="person")
            reads = []
            for obj in ep.get("cooccurring_objects") or []:
                for group in obj.get("text_groups") or []:
                    reads.append(f'{obj["object_type"]} contains "{group["canonical"]}"')
            line = f"[{span}] FOCUS PERSON {descriptor}: SAME EPISODE text: "
            line += "; ".join(reads[:8]) if reads else "(none)"
            line += "; co-occurrence only - ownership is not inferred"
        lines.append(line[:1200])
    if result["binding"] == "ambiguous":
        lines.append("RELATION BINDING: ambiguous across episodes/conflicting reads; refuse to pick one.")
    else:
        lines.append("RELATION BINDING: one temporally supported focus episode.")
    return "\n".join(lines)
