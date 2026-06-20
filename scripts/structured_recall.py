#!/usr/bin/env python3
"""Conservative structured recall for mechanically recoverable memory slots.

This layer runs before free-form generation. It returns an answer only when a
small, clip-neutral extractor can show repeat/consensus support and attach the
source observations. Unsupported or ambiguous inputs return ``None``.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict

try:
    import self_entity
except ImportError:  # package-style test/import
    from scripts import self_entity  # type: ignore


IDENTITY_MIN_CONFIDENCE = 0.90
MIN_REPEAT_SUPPORT = 2
EVENT_CLUSTER_GAP_S = 12.0
DISPLAY_CLUSTER_GAP_S = 4.1

_SELF_WORDS = {"i", "me", "my", "mine", "wearer", "camera"}
_IDENTITY_WORDS = {"name", "called", "identity"}
_EXAMPLE_WORDS = {"example", "examples", "sample", "samples", "specimen", "specimens", "case", "cases"}
_IDENTIFIER_WORDS = {"id", "ids", "identifier", "identifiers", "label", "labels", "number", "numbers", "code", "codes"}
_OUTFIT_WORDS = {"outfit", "outfits", "wear", "wearing", "wore", "clothes", "clothing", "dressed", "dress"}
_WEARABLE_WORDS = {
    "eyewear", "glasses", "spectacles", "watch", "wristwatch", "bracelet", "ring",
    "necklace", "earbuds", "headphones", "hat", "cap", "bag", "backpack",
}
_INSTITUTION_WORDS = {"institution", "university", "college", "institute", "academy", "school", "laboratory", "lab", "center", "centre"}
_DISPLAY_WORDS = {"poster", "posters", "billboard", "billboards", "mural", "murals", "advertisement", "advertisements"}
_OCCUPANCY_WORDS = {"crowd", "crowded", "busy", "empty", "occupancy"}
_PLACE_WORDS = {"station", "platform", "subway", "room", "venue", "hall", "street"}
_DISPLAY_RE = re.compile(r"\b(?:poster|billboard|mural|advertisement)s?\b", re.I)

_EVENT_RE = re.compile(
    r"\b(?:get(?:ting)? dressed|dress(?:ing)?|changing clothes|change of clothes|"
    r"choosing (?:an )?outfit|putting on clothes|outfit selection)\b", re.I)
_WEARING_RE = re.compile(r"\b(?:wearing|wears|wore|dressed in)\s+([^.;]{1,140})", re.I)

_GARMENTS = (
    "sweatpants", "sweat pants", "trousers", "joggers", "shorts", "jeans", "pants",
    "t-shirt", "t shirt", "shirt", "hoodie", "sweater", "jacket", "coat", "dress",
    "skirt", "socks", "crocs", "sneakers", "sandals", "shoes", "boots",
)
_GARMENT_RE = re.compile(r"\b(" + "|".join(re.escape(item) for item in _GARMENTS) + r")\b", re.I)
_COLOURS = {
    "black", "white", "gray", "grey", "red", "blue", "green", "yellow", "orange",
    "purple", "pink", "brown", "beige", "tan", "navy", "cream", "silver", "dark", "light",
}
_CATEGORY = {
    "sweatpants": "bottom", "sweat pants": "bottom", "trousers": "bottom",
    "joggers": "bottom", "shorts": "bottom", "jeans": "bottom", "pants": "bottom",
    "t-shirt": "top", "t shirt": "top", "shirt": "top", "hoodie": "top",
    "sweater": "top", "jacket": "outerwear", "coat": "outerwear", "dress": "body",
    "skirt": "bottom", "socks": "footwear", "crocs": "footwear",
    "sneakers": "footwear", "sandals": "footwear", "shoes": "footwear", "boots": "footwear",
}

_LABELED_ID_RE = re.compile(
    r"\b(?:example|sample|specimen|case)\s*"
    r"(?:id|identifier|number|no\.?|#|label(?:ed)?)?\s*[:=#-]?\s*"
    r"([A-Z0-9][A-Z0-9._/-]{0,31})\b", re.I)
_INVALID_IDENTIFIERS = {"id", "identifier", "number", "no", "label", "labeled"}

_INSTITUTION_KIND = r"University|Institute|College|Academy|School|Laboratory|Laboratories|Center|Centre"
_INSTITUTION_PATTERNS = (
    re.compile(r"\b((?:" + _INSTITUTION_KIND + r")\s+of\s+"
               r"[A-Z][A-Za-z&.'-]*(?:\s+[A-Z][A-Za-z&.'-]*){0,5})\b", re.I),
    re.compile(r"\b([A-Z][A-Za-z&.'-]*(?:\s+[A-Z][A-Za-z&.'-]*){0,5}\s+"
               r"(?:" + _INSTITUTION_KIND + r"))\b", re.I),
)
_INSTITUTION_LEAD = {"at", "from", "the", "to", "visit", "visiting", "welcome"}
_INSTITUTION_GENERIC = {
    "year", "old", "student", "students", "life", "class", "during", "young", "adult",
}


def _tokens(question):
    return set(re.findall(r"[a-z]+", (question or "").lower()))


def classify_slot(question):
    words = _tokens(question)
    self_scoped = bool(words & _SELF_WORDS)
    if self_scoped and words & _IDENTITY_WORDS:
        return "wearer_identity"
    if (self_scoped and words & _OUTFIT_WORDS and not words & _WEARABLE_WORDS
            and (words & {"outfit", "outfits", "clothes", "clothing", "dressed", "dress"}
                 or words & {"wear", "wearing", "wore"})):
        return "wearer_outfit"
    if ({"how", "many"} <= words or "total" in words) and words & _DISPLAY_WORDS:
        return "display_count"
    if words & _OCCUPANCY_WORDS and words & _PLACE_WORDS:
        return "occupancy"
    if words & _EXAMPLE_WORDS:
        return "labeled_examples"
    if words & _INSTITUTION_WORDS:
        return "named_institution"
    return None


def _load_json(path, default):
    try:
        with open(path) as source:
            value = json.load(source)
        return value
    except Exception:
        return default


def _keyframes(memory_dir):
    rows = _load_json(os.path.join(memory_dir, "kf_memory.json"), [])
    return rows if isinstance(rows, list) else []


def _text(value):
    if isinstance(value, list):
        return " ".join(str(item) for item in value if item)
    return str(value or "")


def _visible_text_observations(memory_dir):
    observations = []
    for row in _keyframes(memory_dir):
        text = _text(row.get("ocr") or row.get("_ocr_txt"))
        if text.strip():
            observations.append({"channel": "ocr", "t": row.get("t"),
                                 "frame": row.get("frame"), "text": text})
    screen = _load_json(os.path.join(memory_dir, "screen_memory.json"), [])
    for row in screen if isinstance(screen, list) else []:
        text = _text(row.get("screen_ocr_txt") or row.get("screen_ocr"))
        if text.strip():
            observations.append({"channel": "screen", "t": row.get("t"),
                                 "frame": row.get("frame"), "text": text})
    entity_path = os.path.join(memory_dir, "entity_capture.json")
    try:
        with open(entity_path) as source:
            raw = source.read()
        try:
            decoded = json.loads(raw)
            entity_rows = decoded if isinstance(decoded, list) else [decoded]
        except (TypeError, json.JSONDecodeError):
            entity_rows = []
            for line in raw.splitlines():
                try:
                    entity_rows.append(json.loads(line))
                except (TypeError, json.JSONDecodeError):
                    continue
        for row in entity_rows:
            if not isinstance(row, dict) or row.get("parse_ok") is False:
                continue
            for item in row.get("text_objects") or []:
                if not isinstance(item, dict):
                    continue
                text = _text(item.get("logo_or_text") or item.get("text"))
                if text.strip():
                    observations.append({"channel": "entity_text", "t": row.get("t"),
                                         "frame": row.get("frame"), "text": text})
    except OSError:
        pass
    return observations


def _entity_rows(memory_dir):
    path = os.path.join(memory_dir, "entity_capture.json")
    try:
        with open(path) as source:
            raw = source.read()
    except OSError:
        return []
    try:
        decoded = json.loads(raw)
        rows = decoded if isinstance(decoded, list) else [decoded]
    except (TypeError, json.JSONDecodeError):
        rows = []
        for line in raw.splitlines():
            try:
                rows.append(json.loads(line))
            except (TypeError, json.JSONDecodeError):
                continue
    return [row for row in rows if isinstance(row, dict) and row.get("parse_ok") is not False]


def _provenance(observations):
    return [{key: row.get(key) for key in ("channel", "t", "frame", "text")
             if row.get(key) is not None} for row in observations]


def _identity(memory_dir):
    attrs = self_entity.self_attributes(memory_dir)
    name = attrs.get("name")
    confidence = float(attrs.get("name_confidence") or 0.0)
    if not name or confidence < IDENTITY_MIN_CONFIDENCE:
        return None

    by_name = Counter()
    evidence = []
    for t, channel, text in self_entity._iter_observations(memory_dir):
        if channel != "speech":
            continue
        for candidate, kind in self_entity._candidate_names_from_segment(text):
            if kind != "addressee":
                continue
            by_name[candidate.lower()] += 1
            if candidate.lower() == str(name).lower():
                evidence.append({"channel": channel, "t": t, "text": text})
    chosen_support = by_name.get(str(name).lower(), 0)
    competing = max((count for candidate, count in by_name.items()
                     if candidate != str(name).lower()), default=0)
    if not evidence or chosen_support <= competing:
        return None
    return {
        "slot": "wearer_identity",
        "value": name,
        "answer": f"The wearer was addressed as {name}.",
        "confidence": confidence,
        "provenance": _provenance(evidence),
    }


def _labeled_examples(memory_dir):
    support = defaultdict(list)
    display = {}
    for observation in _visible_text_observations(memory_dir):
        for match in _LABELED_ID_RE.finditer(observation["text"]):
            identifier = match.group(1).strip("._/-")
            if not identifier or identifier.lower() in _INVALID_IDENTIFIERS:
                continue
            key = identifier.casefold()
            display.setdefault(key, identifier.upper())
            support[key].append(observation)
    qualified = [(key, rows) for key, rows in support.items()
                 if len({(row.get("channel"), row.get("t"), row.get("text"))
                         for row in rows}) >= MIN_REPEAT_SUPPORT]
    if not qualified:
        return None
    qualified.sort(key=lambda item: (-len(item[1]), display[item[0]]))
    values = [display[key] for key, _ in qualified]
    evidence = [row for _, rows in qualified for row in rows]
    return {
        "slot": "labeled_examples",
        "value": values,
        "answer": "Repeated visible labels identify: " + ", ".join(values) + ".",
        "confidence": 0.90,
        "provenance": _provenance(evidence),
    }


def _event_window(records):
    event_rows = []
    for row in records:
        text = (str(row.get("caption") or "") + " " + _text(row.get("ocr"))).strip()
        t = row.get("t")
        if isinstance(t, (int, float)) and _EVENT_RE.search(text):
            event_rows.append((float(t), row))
    event_rows.sort(key=lambda item: item[0])
    clusters = []
    for item in event_rows:
        if not clusters or item[0] - clusters[-1][-1][0] > EVENT_CLUSTER_GAP_S:
            clusters.append([item])
        else:
            clusters[-1].append(item)
    clusters = [cluster for cluster in clusters if len(cluster) >= MIN_REPEAT_SUPPORT]
    if not clusters:
        return None
    winner = max(clusters, key=lambda cluster: (len(cluster), cluster[-1][0] - cluster[0][0]))
    return winner[0][0], winner[-1][0]


def _outfit_item(clause, garment_match):
    garment = garment_match.group(1).lower().replace("sweat pants", "sweatpants")
    prefix = clause[max(0, garment_match.start() - 24):garment_match.start()].lower()
    colour = next((word for word in reversed(re.findall(r"[a-z]+", prefix))
                   if word in _COLOURS), None)
    phrase = (colour + " " if colour else "") + garment
    return _CATEGORY.get(garment, garment), phrase


def _outfit(memory_dir):
    records = _keyframes(memory_dir)
    window = _event_window(records)
    if not window:
        return None
    start, end = window
    support = defaultdict(list)
    category_values = defaultdict(Counter)
    for row in records:
        t = row.get("t")
        if not isinstance(t, (int, float)) or not start <= float(t) <= end:
            continue
        caption = str(row.get("caption") or "")
        if not self_entity._classify_cues(caption):
            continue
        for clause_match in _WEARING_RE.finditer(caption):
            clause = clause_match.group(1)
            for garment_match in _GARMENT_RE.finditer(clause):
                category, phrase = _outfit_item(clause, garment_match)
                category_values[category][phrase] += 1
                support[(category, phrase)].append({
                    "channel": "caption", "t": t, "frame": row.get("frame"), "text": caption})

    winners = []
    for category, values in category_values.items():
        ranked = values.most_common()
        if not ranked or ranked[0][1] < MIN_REPEAT_SUPPORT:
            continue
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            continue
        winners.append((category, ranked[0][0], ranked[0][1]))
    if not winners:
        return None
    winners.sort()
    values = [phrase for _, phrase, _ in winners]
    evidence = [row for category, phrase, _ in winners for row in support[(category, phrase)]]
    confidence = min(0.95, 0.70 + 0.05 * min(sum(count for _, _, count in winners), 5))
    return {
        "slot": "wearer_outfit",
        "value": values,
        "answer": "During the detected dressing event, the wearer had "
                  + ", ".join(values) + ".",
        "confidence": round(confidence, 3),
        "provenance": _provenance(evidence),
    }


def _clean_institution(value):
    words = value.strip().split()
    while words and words[0].lower() in _INSTITUTION_LEAD:
        words.pop(0)
    return " ".join(words).strip(" ,.;:-")


def _institution(memory_dir):
    support = defaultdict(list)
    display = {}
    observations = _visible_text_observations(memory_dir)
    for observation in observations:
        for pattern in _INSTITUTION_PATTERNS:
            for match in pattern.finditer(observation["text"]):
                name = _clean_institution(match.group(1))
                if not name:
                    continue
                key = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
                name_words = set(key.split())
                kind_words = {word.lower() for word in re.findall(
                    r"[A-Za-z]+", _INSTITUTION_KIND)}
                distinctive = name_words - kind_words - _INSTITUTION_GENERIC
                if not distinctive:
                    continue
                display.setdefault(key, name)
                support[key].append(observation)
    # Full institution names often come from a structured text-object read while
    # Apple OCR independently captures only the distinctive name tokens. Count
    # that partial cross-channel corroboration without inventing the institution.
    kind_words = {word.lower() for word in re.findall(r"[A-Za-z]+", _INSTITUTION_KIND)}
    for key in list(support):
        core = {word for word in key.split() if word not in kind_words and len(word) > 2}
        if not core:
            continue
        seen = {(row.get("channel"), row.get("t"), row.get("text")) for row in support[key]}
        for observation in observations:
            words = set(re.findall(r"[a-z0-9]+", observation["text"].lower()))
            marker = (observation.get("channel"), observation.get("t"), observation.get("text"))
            if core <= words and marker not in seen:
                support[key].append(observation)
                seen.add(marker)
    qualified = []
    for key, rows in support.items():
        distinct = {(row.get("channel"), row.get("t"), row.get("text")) for row in rows}
        channels = {row.get("channel") for row in rows}
        if len(distinct) >= MIN_REPEAT_SUPPORT or len(channels) >= 2:
            qualified.append((key, rows))
    if not qualified:
        return None
    qualified.sort(key=lambda item: (-len(item[1]), display[item[0]]))
    if len(qualified) > 1 and len(qualified[0][1]) == len(qualified[1][1]):
        return None
    key, evidence = qualified[0]
    name = display[key]
    channels = {row.get("channel") for row in evidence}
    confidence = 0.95 if len(channels) >= 2 else 0.90
    return {
        "slot": "named_institution",
        "value": name,
        "answer": f"Repeated visible text names {name}.",
        "confidence": confidence,
        "provenance": _provenance(evidence),
    }


def _time_clusters(times, gap):
    clusters = []
    for t in sorted(set(times)):
        if not clusters or t - clusters[-1][-1] > gap:
            clusters.append([t])
        else:
            clusters[-1].append(t)
    return clusters


def _display_count(memory_dir):
    rows = []
    for row in _keyframes(memory_dir):
        t = row.get("t")
        if isinstance(t, (int, float)) and _DISPLAY_RE.search(str(row.get("caption") or "")):
            rows.append(row)
    clusters = [cluster for cluster in _time_clusters(
        [float(row["t"]) for row in rows], DISPLAY_CLUSTER_GAP_S) if len(cluster) >= 2]
    if not clusters:
        return None
    evidence = []
    for cluster in clusters:
        representative = next(row for row in rows if float(row["t"]) == cluster[0])
        evidence.append({"channel": "caption", "t": representative.get("t"),
                         "frame": representative.get("frame"),
                         "text": representative.get("caption")})
    count = len(clusters)
    return {
        "slot": "display_count",
        "value": count,
        "answer": f"I counted {count} distinct poster/display viewing episodes.",
        "confidence": min(0.95, 0.70 + 0.05 * count),
        "provenance": _provenance(evidence),
    }


def _occupancy(memory_dir):
    place_re = re.compile(r"\b(?:station|platform|subway|room|venue|hall|street)\b", re.I)
    place_rows = [row for row in _keyframes(memory_dir)
                  if isinstance(row.get("t"), (int, float))
                  and place_re.search(str(row.get("caption") or ""))]
    clusters = [cluster for cluster in _time_clusters(
        [float(row["t"]) for row in place_rows], DISPLAY_CLUSTER_GAP_S) if len(cluster) >= 3]
    if not clusters:
        return None
    window = max(clusters, key=lambda cluster: (len(cluster), cluster[-1] - cluster[0]))
    captured = [row for row in _entity_rows(memory_dir)
                if isinstance(row.get("t"), (int, float)) and window[0] <= row["t"] <= window[-1]]
    if len(captured) < 5:
        return None
    person_counts = [len(row.get("persons") or []) for row in captured]
    evidence = [{"channel": "entity_capture", "t": row.get("t"),
                 "frame": row.get("frame"), "text": f"persons={len(row.get('persons') or [])}"}
                for row in captured]
    if max(person_counts, default=0) == 0:
        answer = (f"The captured place segment was empty rather than crowded: "
                  f"no people were recorded across {len(captured)} structured frames.")
        value = "empty"
    elif sum(count >= 3 for count in person_counts) >= 3:
        answer = (f"The captured place segment was crowded: at least three people were "
                  f"recorded in {sum(count >= 3 for count in person_counts)} structured frames.")
        value = "crowded"
    else:
        return None
    return {"slot": "occupancy", "value": value, "answer": answer,
            "confidence": 0.90, "provenance": _provenance(evidence)}


_EXTRACTORS = {
    "wearer_identity": _identity,
    "labeled_examples": _labeled_examples,
    "wearer_outfit": _outfit,
    "named_institution": _institution,
    "display_count": _display_count,
    "occupancy": _occupancy,
}


def recall(question, memory_path):
    """Return a provenance-bearing structured answer or ``None``."""
    slot = classify_slot(question)
    if slot is None:
        return None
    memory_dir = os.path.dirname(os.path.abspath(memory_path))
    return _EXTRACTORS[slot](memory_dir)
