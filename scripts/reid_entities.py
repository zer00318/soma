#!/usr/bin/env python3
"""Sprint 2 / step 2 — cross-frame RE-ID. Merge per-frame entity records into PERSISTENT entities.

WHY THIS EXISTS (the mis-attribution fix, second half):
  build_entity_capture.py emits, per SALIENT keyframe, SELF-CONTAINED records — each person with
  THEIR OWN clothing/accessories/holding (bound at capture, while the pixels still say who-wore-what),
  each text-bearing object with ITS OWN logo, plus an is_self_view flag + self_attributes. That kills
  the WITHIN-frame mixing ("a person in green, a person in pink, a North Face backpack" -> who?).

  But each keyframe is independent: "the green-tee guy" appears in frames 12, 13, 17 as three
  separate person records. We must STITCH those into ONE persistent entity so the brain can answer
  "what was HE wearing" from a single, consistent referent — and must NOT stitch two DIFFERENT people
  (green-tee guy vs pink-"Breakfast Club" April) into one, which would RE-CREATE the very
  mis-attribution we just removed at capture.

DETERMINISTIC, CPU-ONLY, NO MODEL. Re-ID is appearance-token overlap + temporal continuity:
  - SIGNATURE per record = discriminating appearance tokens (clothing colours, garment nouns,
    accessories). Held items change and are attributes, not identity tokens.
  - SIMILARITY = weighted Jaccard against RECENT sightings, with garment colours weighted heavily.
  - MERGE only inside a continuous time window, above MERGE_SIM, with no discriminating-slot
    conflict. Each identity absorbs at most one observation per frame, so similarly dressed people
    in a crowd remain distinct.
  - ROUTE egocentric body/POV records into the single self entity. Capture models sometimes emit
    the wearer's hands in both self_attributes and persons; the latter is not another person.

  Anti-OVER-merge (the dangerous failure): a hard CONFLICT on top/bottom colour blocks the merge no
    matter how close in time — green-top and pink-top are never the same person.
  Anti-UNDER-merge: changing held objects do not fragment identity, and recent sightings are
    compared individually so one noisy observation does not poison an accumulated signature.

OUTPUT entity_centric.json — a list of:
  {entity_id, type ("person"|"object"|"self"), label,
   attributes: [{attr, value, frames:[t...], confidence}],
   mentions: [t...]}
Confidence reuses scripts/evidence_confidence channel-reliability ideas (a capture-VLM record is a
"caption"-grade channel; a logo read off an object is "ocr"-grade). Re-ID itself is deterministic.

PUBLIC API:
  reid(frame_records)              -> {"entities":[...], "by_id":{id:entity}}
  load_records(ndjson_path)        -> [frame_record, ...]
  signature(person_record)         -> frozenset(tokens)
  similarity(sig_a, sig_b)         -> 0..1
  write_entity_centric(graph, out) -> path

CLI / UNIT TEST (CPU-only, no ollama / no VLM):
  python scripts/reid_entities.py <per_frame.ndjson> [--out entity_centric.json]
  python scripts/reid_entities.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Dict, FrozenSet, List, Optional

# Reuse the channel-reliability table so re-ID confidence sits on the SAME scale as the rest of the
# structural brain. Fall back to a local copy if imported standalone (keeps this file runnable alone).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:
    from evidence_confidence import CHANNEL_REL  # type: ignore
except Exception:  # pragma: no cover - standalone fallback
    CHANNEL_REL = {"speech": 0.92, "ocr": 0.90, "screen": 0.88, "world": 0.60, "caption": 0.40}

# ----------------------------------------------------------------------------- tunables
# A capture-VLM person/clothing record is a model READ of pixels -> "caption"-grade reliability.
# A logo/text string read off an object is verbatim text -> "ocr"-grade.
PERSON_CHANNEL = "caption"
OBJECT_TEXT_CHANNEL = "ocr"

MERGE_SIM = 0.28          # recent-sighting weighted-Jaccard within one continuous scene
SELF_MATCH_SIM = 0.24     # explicit self-view + stable appearance agreement
COLOR_WEIGHT = 3.0        # garment colours dominate the signature (cheap stable discriminator)
GARMENT_WEIGHT = 1.5      # garment nouns (shirt/shorts/jacket) matter more than misc tokens
DEFAULT_WEIGHT = 1.0
MAX_REID_GAP = 3.0        # lexical appearance alone is unsafe across a scene cut / long absence
POSITION_BONUS = 0.06     # useful for one-to-one association in a crowd, never an identity token
POSITION_PENALTY = 0.03
# Discriminating SLOTS where a direct mismatch is a HARD conflict -> never merge (anti-over-merge).
CONFLICT_SLOTS = ("top_color", "bottom_color")

_COLOR_WORDS = {
    "red", "orange", "yellow", "green", "blue", "purple", "pink", "black", "white", "gray",
    "grey", "brown", "beige", "tan", "navy", "teal", "maroon", "cream", "khaki", "olive",
    "gold", "silver", "magenta", "cyan", "violet", "turquoise", "lavender", "burgundy",
}
_GARMENT_WORDS = {
    "shirt", "tee", "tshirt", "t-shirt", "top", "blouse", "sweater", "sweatshirt", "hoodie",
    "jacket", "coat", "vest", "dress", "shorts", "pants", "trousers", "jeans", "skirt",
    "leggings", "sweatpants", "shoes", "sneakers", "boots", "sandals", "crocs", "hat", "cap",
    "beanie", "scarf", "gloves", "socks",
}
# stop tokens that carry no identity (kept out of the signature)
_STOP = set(
    "the a an and or of to in on at is was wearing wears worn has have with from this that it "
    "its as person man woman guy lady boy girl child kid people someone individual their his her "
    "appears looks looking left right center centre middle foreground background near next "
    "side color colour colored coloured holding holds carries carrying some other another "
    "visible unknown unclear blurry blurred focus casual attire standing walking sitting "
    "part specific garment details nothing possibly belonging".split()
)

# Capture models commonly duplicate the camera wearer's hands/body in ``persons`` despite the
# schema explicitly reserving those observations for ``self_attributes``.  These phrases identify
# an egocentric body crop, not an arbitrary full person.  Full-body descriptions (hair/build/man/
# woman) are deliberately absent so a real companion is retained in a mixed self-view frame.
_EGO_BODY = re.compile(
    r"\b(first[- ]person|pov|hands? visible|feet visible|arms? visible|visible hands?|"
    r"visible arms?|bare feet|no visible face)\b|^(?:hands?|feet|arms?)\b|"
    r"^(?:a |the )?person'?s? (?:arm|hand)\b",
    re.I,
)
_EXPLICIT_EGO = re.compile(r"\b(first[- ]person|pov|no visible face)\b", re.I)
_OTHER_IDENTITY = re.compile(r"\b(man|woman|boy|girl|child|kid|hair|beard|face)\b", re.I)


def _text(s) -> str:
    """Flatten loose capture fields before tokenizing them.

    The capture schema permits ``colors`` and self clothing to be lists.  The
    synthetic re-ID fixture only exercised strings, so the first real 120-frame
    artifact crashed before it could produce ``entity_centric.json``.
    """
    if s is None:
        return ""
    if isinstance(s, dict):
        return " ".join(_text(v) for v in s.values())
    if isinstance(s, (list, tuple, set)):
        return " ".join(_text(v) for v in s)
    return str(s)


def _toks(s) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9][a-z0-9\-]*", _text(s).lower())
            if len(w) > 1 and w not in _STOP]


# ----------------------------------------------------------------------------- slot extraction
def _norm_color(tok: str) -> str:
    return "gray" if tok == "grey" else tok


def _slot_colors(person: dict):
    """Pull the TOP and BOTTOM garment colours from a self-contained person record.

    These are the hard discriminators used both to weight the signature and to detect a CONFLICT
    (green top vs pink top => different people, regardless of how close in time they appear)."""
    clothing = person.get("clothing") or {}
    top = (clothing.get("top") or "") if isinstance(clothing, dict) else ""
    bottom = (clothing.get("bottom") or "") if isinstance(clothing, dict) else ""
    colors_field = clothing.get("colors") if isinstance(clothing, dict) else None

    def first_color(*texts):
        for t in texts:
            if isinstance(t, list):
                t = " ".join(str(x) for x in t)
            for w in _toks(t):
                if w in _COLOR_WORDS:
                    return _norm_color(w)
        return None

    top_color = first_color(top)
    bottom_color = first_color(bottom)
    # If a garment string had no colour but a colors[] list exists, fall back to it (top first).
    if (top_color is None or bottom_color is None) and colors_field:
        listed = [_norm_color(w) for w in _toks(colors_field) if w in _COLOR_WORDS]
        if top_color is None and listed:
            top_color = listed[0]
        if bottom_color is None and len(listed) > 1:
            bottom_color = listed[1]
    return {"top_color": top_color, "bottom_color": bottom_color}


def _person_text(person: dict, include_holding: bool = False) -> str:
    """Flatten a person record's identity-bearing fields into one string (position EXCLUDED)."""
    clothing = person.get("clothing") or {}
    parts = [person.get("appearance") or ""]
    if isinstance(clothing, dict):
        parts += [str(clothing.get("top") or ""), str(clothing.get("bottom") or "")]
        col = clothing.get("colors")
        parts.append(" ".join(map(str, col)) if isinstance(col, list) else str(col or ""))
    else:
        parts.append(str(clothing))
    # Held objects change from moment to moment and caused identity fragmentation in real capture
    # (the same pink-shirted person held a reader, keys, phone, then paper).  Accessories are part
    # of appearance; holdings remain bound attributes but are not an identity signature.
    for key in (("accessories", "holding") if include_holding else ("accessories",)):
        v = person.get(key)
        if isinstance(v, list):
            parts += [str(x) for x in v]
        elif v:
            parts.append(str(v))
    return " ".join(p for p in parts if p)


def signature(person: dict) -> FrozenSet[str]:
    """Discriminating appearance tokens for a person record. Position deliberately omitted so a
    moving person (left -> center) still re-IDs to the same entity (anti-under-merge)."""
    toks = set(_toks(_person_text(person)))
    # colour tokens normalised so grey==gray collide in the signature
    return frozenset(_norm_color(t) if t in _COLOR_WORDS else t for t in toks)


def _meaningful_self_attributes(attrs) -> bool:
    if not isinstance(attrs, dict):
        return bool(attrs)
    return any(_toks(v) for v in attrs.values())


def _looks_egocentric(person: dict) -> bool:
    """True only for a body-part/POV observation that capture duplicated as a person."""
    appearance = _text(person.get("appearance"))
    if _EXPLICIT_EGO.search(appearance):
        return True
    return bool(_EGO_BODY.search(appearance) and not _OTHER_IDENTITY.search(appearance))


def _self_identity_tokens(attrs) -> FrozenSet[str]:
    """Identity-bearing self evidence, excluding transient held objects."""
    if not isinstance(attrs, dict):
        return frozenset(_toks(attrs))
    text = " ".join(_text(attrs.get(k)) for k in ("clothing", "body", "accessories"))
    return frozenset(_norm_color(t) if t in _COLOR_WORDS else t for t in _toks(text))


def _person_is_self_duplicate(person: dict, row: dict) -> bool:
    """Conservatively recognize a ``persons`` record that is really the camera wearer.

    A body/POV crop is sufficient even when the model missed ``is_self_view``.  A full person is
    routed to self only when the model did set that flag *and* its stable appearance agrees with
    self_attributes.  This preserves companions in frames that contain both the wearer's hands
    and another person.
    """
    if _looks_egocentric(person):
        return True
    if not row.get("is_self_view"):
        return False
    self_sig = _self_identity_tokens(row.get("self_attributes") or {})
    person_sig = signature(person)
    return bool(self_sig and person_sig and similarity(self_sig, person_sig) >= SELF_MATCH_SIM)


def _tok_weight(tok: str) -> float:
    if tok in _COLOR_WORDS:
        return COLOR_WEIGHT
    if tok in _GARMENT_WORDS:
        return GARMENT_WEIGHT
    return DEFAULT_WEIGHT


def similarity(sig_a: FrozenSet[str], sig_b: FrozenSet[str]) -> float:
    """Weighted Jaccard over two signatures (colours/garments weigh more). 0 when either empty."""
    if not sig_a or not sig_b:
        return 0.0
    inter = sig_a & sig_b
    union = sig_a | sig_b
    wi = sum(_tok_weight(t) for t in inter)
    wu = sum(_tok_weight(t) for t in union)
    return wi / wu if wu else 0.0


def _conflict(slots_a: dict, slots_b: dict) -> bool:
    """A HARD discriminating-slot conflict -> the two records CANNOT be the same person.
    Only fires when BOTH sides assert a value for a conflict slot and they differ."""
    for slot in CONFLICT_SLOTS:
        va, vb = slots_a.get(slot), slots_b.get(slot)
        if va and vb and va != vb:
            return True
    return False


# ----------------------------------------------------------------------------- object text helpers
def _object_key(obj: dict):
    """A text-bearing object's identity = its object noun + its bound logo/text (lowercased).
    Binding the logo to ITS object here is what stops 'North Face' floating to a person/board."""
    name = (obj.get("object") or obj.get("name") or "").strip().lower()
    logo = (obj.get("logo_or_text") or obj.get("logo") or obj.get("text") or "").strip().lower()
    name_key = re.sub(r"\W+", "_", name).strip("_") or "object"
    logo_key = re.sub(r"\W+", "_", logo).strip("_")
    return name_key, logo_key, name, logo


# ----------------------------------------------------------------------------- the re-ID core
class _PersonEntity:
    __slots__ = ("eid", "sig", "slots", "last_t", "records")

    def __init__(self, eid, sig, slots, t, record):
        self.eid = eid
        self.sig = set(sig)
        self.slots = dict(slots)
        self.last_t = t
        self.records = [(t, record)]

    def absorb(self, sig, slots, t, record):
        self.sig |= set(sig)               # accumulate seen tokens (a person gains attributes)
        for k, v in slots.items():         # fill empty discriminating slots; keep first non-empty
            if v and not self.slots.get(k):
                self.slots[k] = v
        self.last_t = t
        self.records.append((t, record))

    def match_similarity(self, sig, t, position) -> float:
        """Compare against recent observations, not an ever-growing union of old attributes."""
        if isinstance(t, (int, float)) and isinstance(self.last_t, (int, float)):
            gap = t - self.last_t
            if gap < 0 or gap > MAX_REID_GAP:
                return 0.0
        # A frame cannot contain the same distinct person twice. This creates one-to-one frame
        # assignment even when two people have identical clothing descriptions.
        if t == self.last_t:
            return 0.0
        recent = self.records[-4:]
        score = max((similarity(signature(rec), sig) for _, rec in recent), default=0.0)
        previous_position = str((recent[-1][1].get("position") if recent else "") or "")
        position = str(position or "")
        if position and previous_position:
            score += POSITION_BONUS if position == previous_position else -POSITION_PENALTY
        return max(0.0, min(1.0, score))


def _emit_confidence(value: str, channel: str, frame_count: int) -> float:
    """Confidence for an attribute: channel reliability (caption vs ocr), nudged up when the SAME
    attribute is corroborated across MULTIPLE frames (a stable green tee seen 4x is safer than a
    one-frame read). Cross-FRAME corroboration only — frequency within one frame proves nothing."""
    base = CHANNEL_REL.get(channel, 0.40)
    if frame_count >= 3:
        base = min(1.0, base + 0.20)
    elif frame_count >= 2:
        base = min(1.0, base + 0.10)
    return round(base, 3)


def _person_attributes(records) -> List[dict]:
    """Collapse a merged person's per-frame records into attribute rows, each carrying the FRAMES
    that support it and a corroboration-aware confidence."""
    # attr -> value -> set(frames)
    acc: Dict[str, Dict[str, set]] = {}

    def add(attr, value, t):
        value = (value or "").strip()
        if not value:
            return
        acc.setdefault(attr, {}).setdefault(value, set()).add(round(t, 1) if isinstance(t, (int, float)) else t)

    for t, rec in records:
        clothing = rec.get("clothing") or {}
        if isinstance(clothing, dict):
            add("top", clothing.get("top"), t)
            add("bottom", clothing.get("bottom"), t)
            col = clothing.get("colors")
            add("colors", ", ".join(map(str, col)) if isinstance(col, list) else col, t)
        elif clothing:
            for item in clothing if isinstance(clothing, (list, tuple, set)) else [clothing]:
                add("clothing", str(item), t)
        for acc_item in (rec.get("accessories") or []):
            add("accessory", str(acc_item), t)
        for held in (rec.get("holding") or []):
            add("holding", str(held), t)
        add("position", rec.get("position"), t)
        add("appearance", rec.get("appearance"), t)

    out = []
    for attr, values in acc.items():
        for value, frames in values.items():
            fr = sorted(frames, key=lambda x: (x is None, x))
            out.append({
                "attr": attr, "value": value, "frames": fr,
                "confidence": _emit_confidence(value, PERSON_CHANNEL, len(fr)),
            })
    # most-corroborated, then most-confident first
    out.sort(key=lambda a: (-len(a["frames"]), -a["confidence"]))
    return out


def _person_label(slots: dict, attributes: List[dict]) -> str:
    """A human-readable, DISTINGUISHING label, preferring the discriminating colours."""
    top = slots.get("top_color")
    bottom = slots.get("bottom_color")
    if top and bottom:
        return "person in %s top, %s bottom" % (top, bottom)
    if top:
        return "person in %s top" % top
    if bottom:
        return "person in %s bottom" % bottom
    # else fall back to the most-corroborated garment/appearance token
    for a in attributes:
        if a["attr"] in ("top", "bottom", "appearance") and a["value"]:
            return "person (%s)" % a["value"][:40]
    return "unidentified person"


def reid(frame_records: List[dict]) -> dict:
    """Merge per-frame entity records into persistent entities. Deterministic, CPU-only.

    frame_records: rows from build_entity_capture (NDJSON). Each:
      {t, frame, persons:[{appearance,clothing:{top,bottom,colors},accessories,holding,position}],
       text_objects:[{object, logo_or_text}], is_self_view:bool, self_attributes:{...}}

    Returns {"entities":[entity...], "by_id":{id:entity}}.
    """
    # stable temporal order so re-ID is deterministic and continuity is meaningful
    rows = sorted(frame_records, key=lambda r: (r.get("t") is None, r.get("t"), str(r.get("frame"))))

    person_entities: List[_PersonEntity] = []
    next_pid = [0]

    def assign_person(person, t):
        sig = signature(person)
        slots = _slot_colors(person)
        # Best non-conflicting, recent candidate. Clothing words alone cannot prove identity after
        # temporal continuity has been lost across a cut.
        best, best_sim = None, 0.0
        for pe in person_entities:
            if _conflict(pe.slots, slots):
                continue  # hard anti-over-merge: distinct discriminating colour
            s = pe.match_similarity(sig, t, person.get("position"))
            if s > best_sim:
                best, best_sim = pe, s
        if best is not None and best_sim >= MERGE_SIM:
            best.absorb(sig, slots, t, person)
            return
        # Otherwise create a new identity. A split is safer than binding a later same-colour
        # stranger to this person after temporal continuity has been lost.
        eid = "person:%d" % next_pid[0]
        next_pid[0] += 1
        person_entities.append(_PersonEntity(eid, sig, slots, t, person))

    # ---- self: one persistent entity, fed by every is_self_view frame's self_attributes ----
    self_records = []  # (t, self_attributes/person-like record)
    for r in rows:
        t = r.get("t")
        for p in (r.get("persons") or []):
            if _person_is_self_duplicate(p, r):
                self_records.append((t, p))
            else:
                assign_person(p, t)
        # Trust meaningful structured self evidence even if the model missed its boolean flag.
        # Empty normalized dictionaries occur on almost every frame and must not create self.
        sa = r.get("self_attributes") or {}
        if _meaningful_self_attributes(sa):
            self_records.append((t, sa))

    entities: List[dict] = []

    # self entity (only if we actually saw the wearer's own body/attributes)
    if self_records:
        attrs = _person_attributes(self_records)
        mentions = sorted({t for t, _ in self_records if t is not None})
        entities.append({
            "entity_id": "self", "type": "self", "label": "the wearer (camera/self)",
            "attributes": attrs, "mentions": mentions,
        })

    # person entities
    for pe in sorted(person_entities, key=lambda e: e.records[0][0] if e.records[0][0] is not None else 1e18):
        attrs = _person_attributes(pe.records)
        mentions = sorted({t for t, _ in pe.records if t is not None})
        entities.append({
            "entity_id": pe.eid, "type": "person", "label": _person_label(pe.slots, attrs),
            "attributes": attrs, "mentions": mentions,
        })

    # ---- objects: text-bearing objects merged by (object noun + bound logo/text) ----
    obj_acc: Dict[tuple, dict] = {}
    for r in rows:
        t = r.get("t")
        for obj in (r.get("text_objects") or []):
            name_key, logo_key, name, logo = _object_key(obj)
            key = (name_key, logo_key)
            slot = obj_acc.get(key)
            if slot is None:
                slot = obj_acc[key] = {
                    "name": name or name_key.replace("_", " "), "logo": logo, "frames": set(),
                }
            if t is not None:
                slot["frames"].add(round(t, 1) if isinstance(t, (int, float)) else t)

    for (name_key, logo_key), slot in obj_acc.items():
        frames = sorted(slot["frames"], key=lambda x: (x is None, x))
        attrs = []
        if slot["logo"]:
            attrs.append({
                "attr": "logo_or_text", "value": slot["logo"], "frames": frames,
                "confidence": _emit_confidence(slot["logo"], OBJECT_TEXT_CHANNEL, len(frames)),
            })
        label = slot["name"] + ((' reading "%s"' % slot["logo"]) if slot["logo"] else "")
        entities.append({
            "entity_id": "object:%s%s" % (name_key, ":" + logo_key if logo_key else ""),
            "type": "object", "label": label, "attributes": attrs, "mentions": frames,
        })

    by_id = {e["entity_id"]: e for e in entities}
    return {"entities": entities, "by_id": by_id}


# ----------------------------------------------------------------------------- IO
def load_records(ndjson_path: str) -> List[dict]:
    """Read the per-frame extractor NDJSON (or a JSON array). Tolerant of blank/garbage lines."""
    rows: List[dict] = []
    with open(ndjson_path) as fh:
        head = fh.read()
    head_strip = head.lstrip()
    if head_strip.startswith("["):
        try:
            arr = json.loads(head_strip)
            return [r for r in arr if isinstance(r, dict)]
        except Exception:
            pass
    for ln in head.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
            if isinstance(r, dict):
                rows.append(r)
        except Exception:
            continue
    return rows


def write_entity_centric(graph: dict, out_path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    json.dump(graph["entities"], open(out_path, "w"), indent=2, ensure_ascii=False)
    return out_path


# ----------------------------------------------------------------------------- self-test (CPU only)
def _selftest() -> int:
    """Synthetic per-frame records: 2 DISTINCT people across 5 frames + 1 text object + a self view.

    Frames (t):
      0: green-tee guy (left)                          object: North Face backpack
      1: green-tee guy (center)         pink "Breakfast Club" woman (right)
      2:                                pink "Breakfast Club" woman (center)
      3: green-tee guy (right)                                                + self_view (my hands)
      4: pink woman (left)
    ASSERT: exactly 2 person entities; green/black stays with the guy and pink/blue with the woman
    (attributes do NOT cross); the backpack logo binds to the backpack; one self entity.
    """
    green = {"appearance": "young man", "clothing": {"top": "green t-shirt", "bottom": "black shorts",
                                                            "colors": ["green", "black"]},
             "accessories": [], "holding": [], "position": "left"}
    green_c = dict(green); green_c["position"] = "center"
    green_r = dict(green); green_r["position"] = "right"
    pink = {"appearance": "woman", "clothing": {"top": "pink Breakfast Club shirt", "bottom": "blue jeans"},
            "accessories": ["sunglasses"], "holding": [], "position": "right"}
    pink_c = dict(pink); pink_c["position"] = "center"
    pink_l = dict(pink); pink_l["position"] = "left"
    backpack = {"object": "backpack", "logo_or_text": "North Face"}

    frames = [
        {"t": 0.0, "frame": "f0", "persons": [green], "text_objects": [backpack], "is_self_view": False},
        {"t": 1.0, "frame": "f1", "persons": [green_c, pink], "text_objects": [], "is_self_view": False},
        {"t": 2.0, "frame": "f2", "persons": [pink_c], "text_objects": [], "is_self_view": False},
        {"t": 3.0, "frame": "f3", "persons": [green_r], "text_objects": [],
         "is_self_view": True, "self_attributes": {"clothing": {"top": "gray hoodie"},
                                                    "holding": ["phone"], "appearance": "my own hands"}},
        {"t": 4.0, "frame": "f4", "persons": [pink_l], "text_objects": [backpack], "is_self_view": False},
    ]

    g = reid(frames)
    ents = g["entities"]
    persons = [e for e in ents if e["type"] == "person"]
    objects = [e for e in ents if e["type"] == "object"]
    selves = [e for e in ents if e["type"] == "self"]

    print("=" * 78)
    print("RE-ID self-test: 5 synthetic frames, 2 distinct people + 1 object + 1 self view")
    print("entities: %d  (persons=%d, objects=%d, self=%d)"
          % (len(ents), len(persons), len(objects), len(selves)))
    for e in ents:
        top = e["attributes"][0] if e["attributes"] else None
        print("  [%-6s] %-38s mentions=%s  top_attr=%s"
              % (e["type"], e["label"][:38], e["mentions"],
                 ("%s=%r conf=%.2f f=%s" % (top["attr"], top["value"][:24], top["confidence"], top["frames"])
                  if top else "-")))

    failures = []

    # (1) exactly two distinct people (no over-merge, no under-merge)
    if len(persons) != 2:
        failures.append("expected 2 person entities, got %d (over/under-merge)" % len(persons))

    # (2) attributes do NOT cross: one person has green top + black bottom; the OTHER pink + blue.
    def vals(e, attr):
        return {a["value"].lower() for a in e["attributes"] if a["attr"] == attr}

    if len(persons) == 2:
        guy = next((p for p in persons if any("green" in v for v in vals(p, "top"))), None)
        woman = next((p for p in persons if any("pink" in v for v in vals(p, "top"))), None)
        if guy is None or woman is None:
            failures.append("could not find a distinct green-top and pink-top person")
        else:
            if guy is woman:
                failures.append("green and pink collapsed into ONE person (over-merge!)")
            # the guy must NOT carry pink/blue; the woman must NOT carry green/black (no crossing)
            guy_blob = " ".join(a["value"].lower() for a in guy["attributes"])
            woman_blob = " ".join(a["value"].lower() for a in woman["attributes"])
            if "pink" in guy_blob or "breakfast" in guy_blob:
                failures.append("pink/Breakfast-Club leaked onto the green-tee guy (cross-attribution!)")
            if "blue jeans" in guy_blob:
                failures.append("blue jeans leaked onto the green-tee guy")
            if "green" in woman_blob or "black shorts" in woman_blob:
                failures.append("green/black leaked onto the pink woman (cross-attribution!)")
            # the guy appears in 3 frames (0,1,3) and the woman in 3 (1,2,4) -> under-merge check
            if sorted(guy["mentions"]) != [0.0, 1.0, 3.0]:
                failures.append("green guy mentions wrong (under-merge?): %s" % guy["mentions"])
            if sorted(woman["mentions"]) != [1.0, 2.0, 4.0]:
                failures.append("pink woman mentions wrong (under-merge?): %s" % woman["mentions"])

    # (3) the backpack's logo binds to the backpack (object), seen in 2 frames
    bp = next((o for o in objects if "backpack" in o["entity_id"]), None)
    if bp is None:
        failures.append("backpack object entity missing")
    else:
        logo = " ".join(a["value"].lower() for a in bp["attributes"] if a["attr"] == "logo_or_text")
        if "north face" not in logo:
            failures.append("'North Face' did not bind to the backpack; got %r" % logo)
        if bp["mentions"] != [0.0, 4.0]:
            failures.append("backpack mentions wrong: %s" % bp["mentions"])

    # (4) exactly one self entity, carrying the wearer's own attrs, NOT a stranger's outfit
    if len(selves) != 1:
        failures.append("expected exactly 1 self entity, got %d" % len(selves))
    else:
        self_blob = " ".join(a["value"].lower() for a in selves[0]["attributes"])
        if "gray hoodie" not in self_blob:
            failures.append("self entity lost its own clothing ('gray hoodie'); got %r" % self_blob)
        if "green" in self_blob or "pink" in self_blob:
            failures.append("a stranger's outfit leaked into 'self' (the original bug!)")

    print("-" * 78)
    if failures:
        print("FAILURES:")
        for f in failures:
            print("  - " + f)
        return 1
    print("ALL CHECKS PASSED: 2 distinct people, no cross-attribution, logo bound to object, 1 self.")
    return 0


# ----------------------------------------------------------------------------- CLI
def main(argv) -> int:
    ap = argparse.ArgumentParser(description="Cross-frame re-ID of per-frame entity records.")
    ap.add_argument("ndjson", nargs="?", help="per-frame extractor NDJSON (from build_entity_capture)")
    ap.add_argument("--out", default=None, help="write entity_centric.json here")
    ap.add_argument("--selftest", action="store_true", help="run the CPU-only synthetic unit test")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.ndjson:
        ap.print_usage()
        print("error: provide a per-frame NDJSON path, or --selftest", file=sys.stderr)
        return 2

    records = load_records(args.ndjson)
    graph = reid(records)
    print("%d frame records -> %d entities (%s)" % (
        len(records), len(graph["entities"]),
        ", ".join("%s=%d" % (t, sum(1 for e in graph["entities"] if e["type"] == t))
                  for t in ("self", "person", "object"))))
    for e in graph["entities"]:
        top = e["attributes"][0] if e["attributes"] else None
        print("  [%-6s] %-40s mentions=%d attrs=%d  %s" % (
            e["type"], e["label"][:40], len(e["mentions"]), len(e["attributes"]),
            ("top=%s=%r" % (top["attr"], top["value"][:30]) if top else "")))
    out = args.out or (os.path.splitext(args.ndjson)[0] + ".entity_centric.json")
    write_entity_centric(graph, out)
    print("WROTE %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
