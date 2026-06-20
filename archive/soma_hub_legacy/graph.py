from __future__ import annotations

import json
import math
import re
import sqlite3
import unicodedata
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from soma_hub.crypto import EncryptedTextCodec
from soma_hub.location import PlaceCandidate, PlaceResolver


CERTAINTY_CONFIDENCE = {
    "likely": 0.78,
    "uncertain": 0.42,
    "provisional": 0.38,
}

CURRENT_CONFIDENCE_THRESHOLD = 0.70
PROMOTE_OBSERVATION_COUNT = 3
PROMOTE_STABILITY_COUNT = 3


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_label(value: str) -> str:
    cleaned = value.lower()
    cleaned = re.sub(r"[^a-z0-9/ -]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    aliases = {
        "foreground subject": "visible person",
        "person visible": "visible person",
        "additional face/person": "background person",
        "bus sign": "transit sign",
        "visible sign/board": "text surface",
        "wall/transit sign": "text surface",
        "black over-ear headphones": "headphones",
        "over-ear headphones": "headphones",
        "gray shirt": "shirt",
        "grey shirt": "shirt",
    }
    return aliases.get(cleaned, cleaned)


def label_kind(label: str) -> str:
    normalized = normalize_label(label)
    if "speech" in normalized or "transcript" in normalized:
        return "speech_segment"
    if any(token in normalized for token in ("sign", "board", "text", "screen", "display", "document", "surface")):
        return "text_surface"
    if "person" in normalized or "people" in normalized:
        return "person"
    return "object"


def infer_text_surface_label(visible_text: str) -> str:
    normalized = visible_text.lower()
    transit_clues = (
        "garching-forschungszentrum",
        "max-planck-campus",
        "walther-meißner",
        "walther-meissner",
        "lichtenbergstr",
        "anna-boyksen",
        "isarstr",
        "boltzmannstr",
        "bus",
        "p+r",
        "u-bahn",
        "s-bahn",
        "bahnhof",
    )
    if any(clue in normalized for clue in transit_clues):
        return "transit sign"

    screen_clues = (
        "instagram",
        "views",
        "post",
        "follow",
        "edited",
        "wikipedia",
        "article",
        "archive",
        "featured",
        "sun ",
        "jun",
        "%",
        "0:0",
        "10:",
    )
    if any(clue in normalized for clue in screen_clues):
        return "display screen"

    if re.search(r"\b\d{1,2}:\d{2}\b", normalized):
        return "display screen"
    if re.search(r"\b[a-z0-9-]+\.(com|org|net|de|io)\b", normalized):
        return "display screen"

    return "text surface"


@dataclass(frozen=True)
class PerceptionFact:
    ontology: str
    label: str
    attributes: str
    relation_text: str
    certainty: str
    raw_text: str
    confidence: float
    extra: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExtractedRelation:
    relation_type: str
    object_label: str | None = None
    object_text: str | None = None


@dataclass(frozen=True)
class ExtractedAttribute:
    key: str
    value: str
    source: str


import hashlib
from typing import Dict, List, Tuple, Any

class RelationExtractor:
    def __init__(self, ontology: Dict[str, Any] = None):
        """
        Initialize with optional ontology mapping.
        Ontology should define expected entity types for each relation,
        e.g. {'worn_by': ('person', 'object'), ...}
        """
        self.ontology = ontology or {}
        # Map relation name → handler function
        self.handlers = {
            "worn_by": self._handle_worn_by,
            "held_by": self._handle_held_by,
            "near":    self._handle_near,
            "inside":  self._handle_inside,
            "above":   self._handle_above,
            "below":   self._handle_below,
        }

    # ----------------------------------------------------------------------
    # Canonical ID handling
    # ----------------------------------------------------------------------
    @staticmethod
    def _canonical_id(obj: Dict[str, Any]) -> str:
        """
        Return a stable identifier for an object.
        Prefer an explicit 'canonical_id' field; otherwise fall back to a
        SHA‑256 hash of the concatenated immutable fields (id, type, bbox).
        """
        if "canonical_id" in obj:
            return str(obj["canonical_id"])
        hasher = hashlib.sha256()
        for key in ("id", "type"):
            hasher.update(str(obj.get(key, "")).encode("utf-8"))
        if "bbox" in obj:
            hasher.update(str(obj["bbox"]).encode("utf-8"))
        return str(hasher.hexdigest())

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------
    def ingest_packet(self, packet: Dict[str, Any]) -> List[Tuple[str, str, str]]:
        """
        Parse a structured perception packet and return a list of extracted
        relations as (subject_canonical_id, predicate, object_canonical_id).
        """
        # Build lookup: canonical_id → object dict for fast access
        objects_by_id = {self._canonical_id(o): o for o in packet.get("objects", [])}
        relations: List[Tuple[str, str, str]] = []

        # Explicit relationship statements (if any)
        for rel in packet.get("relationships", []):
            sub_cid = self._canonical_id(rel["source"])
            obj_cid = self._canonical_id(rel["target"])
            relations.append((sub_cid, rel["type"], obj_cid))

        # Derive spatial / attribute based relations
        for src_obj in packet.get("objects", []):
            src_cid = self._canonical_id(src_obj)
            for tgt_obj in packet.get("objects", []):
                if src_cid == self._canonical_id(tgt_obj):
                    continue
                tgt_cid = self._canonical_id(tgt_obj)

                # Try each ontology relation; first handler that returns True wins
                for rel_name, handler in self.handlers.items():
                    if handler(src_obj, tgt_obj):
                        relations.append((src_cid, rel_name, tgt_cid))
                        break  # stop checking other handlers for this pair

        return relations

    # ----------------------------------------------------------------------
    # Handler methods
    # ----------------------------------------------------------------------
    def _handle_worn_by(self, src: Dict[str, Any], tgt: Dict[str, Any]) -> bool:
        """Example: a person (src) is wearing an object (tgt)."""
        allowed_src = self.ontology.get("worn_by", [None])[0]
        allowed_tgt = self.ontology.get("worn_by", [None])[1]
        return (src.get("type") == allowed_src and tgt.get("type") == allowed_tgt)

    def _handle_held_by(self, src: Dict[str, Any], tgt: Dict[str, Any]) -> bool:
        allowed_src = self.ontology.get("held_by", [None])[0]
        allowed_tgt = self.ontology.get("held_by", [None])[1]
        return (src.get("type") == allowed_src and tgt.get("type") == allowed_tgt)

    def _handle_near(self, src: Dict[str, Any], tgt: Dict[str, Any]) -> bool:
        """Spatial “near” based on centroid distance ≤ 5.0 m (placeholder)."""
        src_bbox = src.get("bbox")
        tgt_bbox = tgt.get("bbox")
        if not (src_bbox and tgt_bbox):
            return False

        def centroid(b):
            x1, y1, x2, y2 = b
            return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

        cx1, cy1 = centroid(src_bbox)
        cx2, cy2 = centroid(tgt_bbox)
        import math
        dist = math.hypot(cx1 - cx2, cy1 - cy2)
        return dist <= 5.0

    def _handle_inside(self, src: Dict[str, Any], tgt: Dict[str, Any]) -> bool:
        """src is inside tgt if its bbox fully contains within tgt's bbox."""
        src_bbox = src.get("bbox")
        tgt_bbox = tgt.get("bbox")
        if not (src_bbox and tgt_bbox):
            return False
        return (src_bbox[0] >= tgt_bbox[0] and src_bbox[1] >= tgt_bbox[1] and
                src_bbox[2] <= tgt_bbox[2] and src_bbox[3] <= tgt_bbox[3])

    def _handle_above(self, src: Dict[str, Any], tgt: Dict[str, Any]) -> bool:
        """src is above tgt if its bottom edge (ymax) ≤ tgt's top edge (ymin)."""
        src_bbox = src.get("bbox")
        tgt_bbox = tgt.get("bbox")
        if not (src_bbox and tgt_bbox):
            return False
        return src_bbox[3] <= tgt_bbox[1]

    def _handle_below(self, src: Dict[str, Any], tgt: Dict[str, Any]) -> bool:
        """src is below tgt if its top edge (ymin) >= tgt's bottom edge (ymax)."""
        src_bbox = src.get("bbox")
        tgt_bbox = tgt.get("bbox")
        if not (src_bbox and tgt_bbox):
            return False
        return src_bbox[1] >= tgt_bbox[3]

class PerceptionPacketParser:
    def parse_text(self, text: str, default_confidence: float | None = None) -> list[PerceptionFact]:
        facts: list[PerceptionFact] = []
        for line in text.splitlines():
            fact = self.parse_line(line, default_confidence=default_confidence)
            if fact:
                facts.append(fact)
        return facts

    def parse_line(self, line: str, default_confidence: float | None = None) -> PerceptionFact | None:
        cleaned = " ".join(line.strip().split())
        cleaned = re.sub(r";?\s*tracked for \d+ detector frames\b", "", cleaned, flags=re.IGNORECASE)
        if not (cleaned.startswith("OBJECT |") or cleaned.startswith("EVENT |")):
            return None

        parts = [part.strip() for part in cleaned.split("|")]
        if len(parts) < 3:
            return None
        ontology = parts[0].upper()
        label = parts[1]
        attributes = parts[2] if len(parts) > 2 else ""
        relation_text = parts[3] if len(parts) > 3 else ""
        certainty = self._certainty(parts[4] if len(parts) > 4 else "")
        confidence = default_confidence if default_confidence is not None else CERTAINTY_CONFIDENCE.get(certainty, 0.55)
        return PerceptionFact(
            ontology=ontology,
            label=label,
            attributes=attributes,
            relation_text=relation_text,
            certainty=certainty,
            raw_text=cleaned,
            confidence=confidence,
            extra=parts[5:],
        )

    def _relations_from_attributes(self, attributes: str) -> list[ExtractedRelation]:
        """Synthesise located_at / near relations from key=value attribute pairs."""
        relations: list[ExtractedRelation] = []
        for key, value in re.findall(r"(\w+)=([^\s,]+)", attributes):
            if key == "location":
                relations.append(ExtractedRelation(relation_type="located_at", object_label=value.replace("_", " ")))
            elif key == "near":
                relations.append(ExtractedRelation(relation_type="near", object_label=value.replace("_", " ")))
        return relations

    def extract_relations(self, fact: PerceptionFact, place: PlaceCandidate | None) -> list[ExtractedRelation]:
        text = f"{fact.attributes} {fact.relation_text}".lower()
        relations: list[ExtractedRelation] = []

        if "worn by visible person" in text or "on visible person" in text:
            relations.append(ExtractedRelation("worn_by", object_label="visible person"))
        if "worn on head" in text:
            relations.append(ExtractedRelation("worn_by", object_label="visible person"))
            relations.append(ExtractedRelation("on", object_text="head"))
        if "held by visible person" in text or "held in hand" in text:
            relations.append(ExtractedRelation("held_by", object_label="visible person"))
        if "above visible person" in text or "above the visible person" in text:
            relations.append(ExtractedRelation("above", object_label="visible person"))
        if "below visible person" in text or "below the visible person" in text:
            relations.append(ExtractedRelation("below", object_label="visible person"))
        if "behind/near foreground subject" in text:
            if normalize_label(fact.label) == "background person":
                relations.append(ExtractedRelation("near", object_text="foreground subject"))
                relations.append(ExtractedRelation("behind", object_text="foreground subject"))
            else:
                relations.append(ExtractedRelation("near", object_label="visible person"))
                relations.append(ExtractedRelation("behind", object_label="visible person"))
        elif "overlapping/near visible person" in text:
            relations.append(ExtractedRelation("near", object_label="visible person"))
        elif " near " in f" {text} ":
            near_target = self._near_target(text)
            if normalize_label(near_target) == "visible person":
                relations.append(ExtractedRelation("near", object_label="visible person"))
            else:
                relations.append(ExtractedRelation("near", object_text=near_target))
        if "inside" in text:
            relations.append(ExtractedRelation("inside", object_text=self._after_keyword(text, "inside")))
        if " on " in f" {text} " and not any(rel.relation_type == "on" for rel in relations):
            relations.append(ExtractedRelation("on", object_text=self._after_keyword(text, "on")))
        if "ocr text" in text or "text includes" in text or "written" in text:
            visible_text = self._clean_visible_text(self._quoted_text(fact.raw_text) or fact.attributes)
            if visible_text:
                relations.append(ExtractedRelation("contains_text", object_text=visible_text))
        frame_region = self._frame_region(text)
        if frame_region:
            relations.append(ExtractedRelation("seen_in_frame_region", object_text=frame_region))
        foreground = self._foreground_status(text)
        if foreground:
            relations.append(ExtractedRelation("foreground_status", object_text=foreground))
        if place:
            relations.append(ExtractedRelation("located_at", object_text=place.name))

        # Synthesise located_at / near from structured key=value attributes
        relations.extend(self._relations_from_attributes(fact.attributes))

        subject_norm = normalize_label(fact.label)
        deduped: dict[tuple[str, str, str], ExtractedRelation] = {}
        for relation in relations:
            if relation.object_label and normalize_label(relation.object_label) == subject_norm:
                continue
            if relation.object_text and normalize_label(relation.object_text) == subject_norm:
                continue
            key = (relation.relation_type, relation.object_label or "", relation.object_text or "")
            deduped[key] = relation
        return list(deduped.values())

    def extract_attributes(self, fact: PerceptionFact) -> list[ExtractedAttribute]:
        label_norm = normalize_label(fact.label)
        kind = label_kind(fact.label)
        text = f"{fact.label} {fact.attributes} {fact.relation_text}".lower()
        attributes: list[ExtractedAttribute] = []

        color = self._first_color(text)
        if color:
            attributes.append(ExtractedAttribute("color", color, "visible_color"))

        if kind == "person":
            if "human figure" in text or "face/partial person" in text or "person" in text:
                attributes.append(ExtractedAttribute("entity_type", "person", "visible_detection"))
            if "face/partial person" in text or "face detected" in text:
                attributes.append(ExtractedAttribute("face.visible", "face or partial face visible", "visible_detection"))
            if "human figure" in text or "body" in text:
                attributes.append(ExtractedAttribute("body.visible", "body/upper body visible", "visible_detection"))
            if "adult" in text:
                attributes.append(ExtractedAttribute("age_visible", "adult appearing", "visible_descriptor"))
            age_approx = self._age_approx(text)
            if age_approx:
                attributes.append(ExtractedAttribute("age.approx", age_approx, "visible_descriptor"))
            stature = self._stature(text)
            if stature:
                attributes.append(ExtractedAttribute("stature", stature, "visible_descriptor"))
            if "medium build" in text:
                attributes.append(ExtractedAttribute("build", "medium build", "visible_descriptor"))
            if "curly" in text and "hair" in text:
                attributes.append(ExtractedAttribute("hair.style", "curly", "visible_descriptor"))
            hair_length = self._hair_length(text)
            if hair_length:
                attributes.append(ExtractedAttribute("hair.length", hair_length, "visible_descriptor"))
            hair_color = self._hair_color(text)
            if hair_color:
                attributes.append(ExtractedAttribute("hair.color", hair_color, "visible_descriptor"))
            if "glasses" in text or "eyeglasses" in text:
                attributes.append(ExtractedAttribute("eyewear", "glasses", "visible_descriptor"))
            if "eyes visible" in text:
                attributes.append(ExtractedAttribute("eyes.visible", "eyes visible", "visible_descriptor"))
            if "beard" in text or "facial hair" in text:
                attributes.append(ExtractedAttribute("facial_hair", "visible facial hair", "visible_descriptor"))
            mark_detail = self._mark_detail(text)
            if mark_detail:
                attributes.append(ExtractedAttribute("mark.visible", mark_detail, "visible_descriptor"))
            handedness = self._handedness(text)
            if handedness:
                attributes.append(ExtractedAttribute("handedness", handedness, "visible_descriptor"))
            gait = self._gait_observation(text)
            if gait:
                attributes.append(ExtractedAttribute("gait", gait, "visible_descriptor"))
            clothing = self._clothing_value(text)
            if clothing:
                attributes.append(ExtractedAttribute("clothing.upper", clothing, "visible_descriptor"))
            lower_clothing = self._lower_clothing_value(text)
            if lower_clothing:
                attributes.append(ExtractedAttribute("clothing.lower", lower_clothing, "visible_descriptor"))
            shoes = self._shoe_value(text)
            if shoes:
                attributes.append(ExtractedAttribute("clothing.feet", shoes, "visible_descriptor"))
            headwear = self._headwear_value(text)
            if headwear:
                attributes.append(ExtractedAttribute("clothing.head", headwear, "visible_descriptor"))

        if kind == "object":
            if any(word in label_norm for word in ("bag", "backpack", "tote", "pouch")):
                attributes.append(ExtractedAttribute("object_type", "bag", "visible_detection"))
                bag_size = self._bag_size(text)
                if bag_size:
                    attributes.append(ExtractedAttribute("size", bag_size, "visible_descriptor"))
                material = self._material(text)
                if material:
                    attributes.append(ExtractedAttribute("material", material, "visible_descriptor"))
                if "zip" in text or "zipper" in text:
                    attributes.append(ExtractedAttribute("closure", "zipper", "visible_descriptor"))
                strap = self._strap_detail(text)
                if strap:
                    attributes.append(ExtractedAttribute("strap", strap, "visible_descriptor"))
                if "pocket" in text:
                    attributes.append(ExtractedAttribute("pocket", "visible pocket", "visible_descriptor"))
                pattern = self._pattern(text)
                if pattern:
                    attributes.append(ExtractedAttribute("pattern", pattern, "visible_descriptor"))
                wear = self._wear_detail(text)
                if wear:
                    attributes.append(ExtractedAttribute("wear", wear, "visible_descriptor"))
            elif label_norm in {"headphones", "eyeglasses", "glasses", "shirt"}:
                attributes.append(ExtractedAttribute("object_type", label_norm, "visible_detection"))
        elif kind == "text_surface":
            quoted = self._quoted_text(fact.raw_text)
            cleaned_text = self._clean_visible_text(quoted or fact.attributes)
            if quoted:
                attributes.append(ExtractedAttribute("text.visible", cleaned_text, "ocr"))
            surface_type = infer_text_surface_label(cleaned_text)
            attributes.append(ExtractedAttribute("object_type", surface_type, "visible_detection"))

        deduped: dict[tuple[str, str], ExtractedAttribute] = {}
        for attribute in attributes:
            if attribute.value:
                deduped[(attribute.key, attribute.value)] = attribute
        return list(deduped.values())

    def _certainty(self, value: str) -> str:
        lower = value.lower()
        if "likely" in lower:
            return "likely"
        if "uncertain" in lower:
            return "uncertain"
        if "provisional" in lower:
            return "provisional"
        return "uncertain"

    def _quoted_text(self, value: str) -> str | None:
        match = re.search(r'"([^"]{2,})"', value)
        return match.group(1).strip() if match else None

    def _after_keyword(self, value: str, keyword: str) -> str:
        match = re.search(rf"\b{re.escape(keyword)}\b\s+([^;,.|]+)", value)
        if not match:
            return ""
        return match.group(1).strip()

    def _near_target(self, value: str) -> str:
        target = self._after_keyword(value, "near")
        return target or "nearby object/place"

    def _frame_region(self, value: str) -> str | None:
        match = re.search(r"\b(upper|middle|lower)\s+(left|center|right)\s+frame\b", value)
        if match:
            return f"{match.group(1)} {match.group(2)} frame"
        match = re.search(r"\b(upper|middle|lower)\s+frame\b", value)
        if match:
            return f"{match.group(1)} frame"
        return None

    def _foreground_status(self, value: str) -> str | None:
        for phrase in (
            "dominant foreground object",
            "large visible object",
            "medium visible object",
            "small visible object",
        ):
            if phrase in value:
                return phrase
        return None

    def _first_color(self, value: str) -> str | None:
        for color in (
            "black",
            "white",
            "gray",
            "grey",
            "blue",
            "red",
            "green",
            "yellow",
            "brown",
            "tan",
            "orange",
            "purple",
            "pink",
            "silver",
            "gold",
        ):
            if re.search(rf"\b{color}\b", value):
                return "gray" if color == "grey" else color
        return None

    def _hair_color(self, value: str) -> str | None:
        match = re.search(r"\b(black|brown|dark|blond|blonde|gray|grey|white|red)(?:\s+[\w-]+){0,2}\s+hair\b", value)
        if not match:
            match = re.search(r"\bhair\s+(?:is\s+)?(black|brown|dark|blond|blonde|gray|grey|white|red)\b", value)
        if not match:
            return None
        color = match.group(1)
        return "gray" if color == "grey" else color

    def _hair_length(self, value: str) -> str | None:
        match = re.search(r"\b(short|medium|long|shoulder-length|buzzed|shaved)(?:\s+[\w-]+){0,2}\s+hair\b", value)
        return match.group(1) if match else None

    def _age_approx(self, value: str) -> str | None:
        match = re.search(r"\b(child|teen|teenager|young adult|adult|older adult|elderly)\b", value)
        if not match:
            return None
        mapping = {
            "teenager": "teen",
            "young adult": "young adult",
            "older adult": "older adult",
        }
        return mapping.get(match.group(1), match.group(1))

    def _stature(self, value: str) -> str | None:
        match = re.search(r"\b(tall|short|average height)\b", value)
        return match.group(1) if match else None

    def _clothing_value(self, value: str) -> str | None:
        match = re.search(r"\b((?:black|white|gray|grey|blue|red|green|brown|dark|light)[a-z -]*\s+(?:shirt|t-shirt|jacket|hoodie|coat|sweater))\b", value)
        if match:
            return match.group(1).replace("grey", "gray").strip()
        if "upper-body clothing" in value:
            color = self._first_color(value)
            return f"{color} upper-body clothing" if color else "upper-body clothing"
        return None

    def _lower_clothing_value(self, value: str) -> str | None:
        match = re.search(r"\b((?:black|white|gray|grey|blue|red|green|brown|dark|light)[a-z -]*\s+(?:pants|trousers|jeans|shorts|skirt))\b", value)
        return match.group(1).replace("grey", "gray").strip() if match else None

    def _shoe_value(self, value: str) -> str | None:
        match = re.search(r"\b((?:black|white|gray|grey|blue|red|green|brown|dark|light)[a-z -]*\s+(?:shoes|sneakers|boots|sandals))\b", value)
        return match.group(1).replace("grey", "gray").strip() if match else None

    def _headwear_value(self, value: str) -> str | None:
        match = re.search(r"\b((?:black|white|gray|grey|blue|red|green|brown|dark|light)[a-z -]*\s+(?:hat|cap|helmet|beanie))\b", value)
        return match.group(1).replace("grey", "gray").strip() if match else None

    def _mark_detail(self, value: str) -> str | None:
        for phrase in (
            "tattoo visible",
            "scar visible",
            "birthmark visible",
            "freckles visible",
            "mole visible",
        ):
            if phrase in value:
                return phrase
        return None

    def _handedness(self, value: str) -> str | None:
        match = re.search(r"\b(left-handed|right-handed)\b", value)
        return match.group(1) if match else None

    def _gait_observation(self, value: str) -> str | None:
        for phrase in ("limp visible", "running", "walking", "standing", "seated"):
            if phrase in value:
                return phrase
        return None

    import warnings
    def _clean_visible_text(self, value: str) -> str:
        warnings.warn("PerceptionPacketParser is deprecated. Use RelationExtractor with structured JSON instead.", DeprecationWarning)
        pieces = [
            self._clean_visible_text_piece(piece)
            for piece in re.split(r"\s*/\s*", value)
        ]
        deduped: dict[str, str] = {}
        for piece in pieces:
            if not piece:
                continue
            if not self._useful_visible_text_piece(piece):
                continue
            key = re.sub(r"[^a-z0-9äöüß]+", " ", piece.lower()).strip()
            if len(key) < 2:
                continue
            deduped.setdefault(key, piece)
        self._drop_subsumed_visible_text(deduped)
        return " / ".join(deduped.values())

    def _clean_visible_text_piece(self, value: str) -> str:
        piece = " ".join(value.split()).strip(" ,:;|-")
        if not piece:
            return ""

        replacements = [
            (r"\b(?!max-)[a-z]{1,4}-planck-campus\b", "Max-Planck-Campus"),
            (r"\bmax[\s-]+planck[\s-]+campus\b", "Max-Planck-Campus"),
            (r"(?<!-)\bplanck-campus\b", "Max-Planck-Campus"),
            (r"\bgarching[- ](?:for|fors|forsch|ror|rors)[a-z-]*\b", "Garching-Forschungszentrum"),
            (r"\bwalther-mei(?:b|n|ß|ss)ner-?str\.?", "Walther-Meißner-Str."),
            (r"\blichtenbergst(?:r|ı)?\.?", "Lichtenbergstr."),
            (r"\b(?:su[,.]?\s+)?bo[ulilzt]{1,5}manns(?:tr|tt|ir|t|e|u)?\.?", "Boltzmannstr."),
            (r"\b(?:u[,.]?\s+)?bolzmanns(?:tr|tt|ir|t|e|u)?\.?", "Boltzmannstr."),
            (r"\bboli[zt]mannst(?:r|ı)?\.?", "Boltzmannstr."),
            (r"\banna-boyksen-str\.?", "Anna-Boyksen-Str."),
            (r"\bisarstr\.?", "Isarstr."),
        ]
        for pattern, replacement in replacements:
            piece = re.sub(pattern, replacement, piece, flags=re.IGNORECASE)

        piece = re.sub(r"\bbus\b", "BUS", piece, flags=re.IGNORECASE)
        piece = re.sub(r"\s+", " ", piece).strip(" ,:;|-")
        canonical = self._canonical_visible_text_piece(piece)
        if canonical:
            return canonical
        return piece

    def _canonical_visible_text_piece(self, value: str) -> str | None:
        lower = value.lower()
        if "garching-forschungszentrum" in lower:
            return "Garching-Forschungszentrum"
        if "max-planck-campus" in lower:
            return "Max-Planck-Campus"
        if "walther-meißner-str" in lower and "lichtenbergstr" in lower:
            return "Walther-Meißner-Str., Lichtenbergstr."
        if "anna-boyksen-str" in lower and "isarstr" in lower and "boltzmannstr" in lower:
            return "Anna-Boyksen-Str., Isarstr., Boltzmannstr."
        if re.search(r"\b(?:p\s*[+•*-]\s*r|p\s*r)\b", lower):
            return "P+R"
        if re.search(r"\bbus\b", lower, flags=re.IGNORECASE):
            return "BUS"
        if "walther-meißner-str" in lower:
            return "Walther-Meißner-Str."
        if "lichtenbergstr" in lower:
            return "Lichtenbergstr."
        if "anna-boyksen-str" in lower:
            return "Anna-Boyksen-Str."
        if "isarstr" in lower:
            return "Isarstr."
        if "boltzmannstr" in lower:
            return "Boltzmannstr."
        return None

    def _drop_subsumed_visible_text(self, deduped: dict[str, str]) -> None:
        keys = set(deduped)
        if "walther meißner str lichtenbergstr" in keys:
            deduped.pop("walther meißner str", None)
            deduped.pop("lichtenbergstr", None)
        if "anna boyksen str isarstr boltzmannstr" in keys:
            deduped.pop("anna boyksen str", None)
            deduped.pop("isarstr", None)
            deduped.pop("boltzmannstr", None)

    def _useful_visible_text_piece(self, value: str) -> bool:
        normalized = re.sub(r"[^a-z0-9äöüß.-]+", " ", value.lower()).strip()
        if not normalized:
            return False
        if value == "P+R":
            return True
        known_fragments = (
            "garching",
            "forschungszentrum",
            "max-planck-campus",
            "walther-meißner",
            "walther-meissner",
            "lichtenberg",
            "boltzmann",
            "anna-boyksen",
            "isarstr",
            "bus",
        )
        if any(fragment in normalized for fragment in known_fragments):
            return True

        compact = re.sub(r"[^a-z0-9äöüß]+", "", normalized)
        if compact in {
            "str",
            "nstr",
            "istr",
            "rstr",
            "nnstr",
            "annstr",
            "anstr",
            "mannstr",
            "zmannstr",
            "nst",
            "annst",
            "nannstr",
            "nannst",
        }:
            return False
        letters = sum(1 for char in normalized if char.isalpha())
        digits = sum(1 for char in normalized if char.isdigit())
        if digits and digits >= letters:
            return False
        if len(compact) < 5 or letters < 4:
            return False
        return True

    def _material(self, value: str) -> str | None:
        for material in ("leather", "nylon", "canvas", "fabric", "cloth", "plastic", "metal"):
            if re.search(rf"\b{material}\b", value):
                return material
        return None

    def _bag_size(self, value: str) -> str | None:
        match = re.search(r"\b(small|medium|large|compact|oversized)\b(?:\s+\w+){0,3}\s+\b(?:bag|backpack|tote|pouch)\b", value)
        return match.group(1) if match else None

    def _strap_detail(self, value: str) -> str | None:
        for phrase in ("single strap", "double strap", "shoulder strap", "crossbody strap"):
            if phrase in value:
                return phrase
        return None

    def _pattern(self, value: str) -> str | None:
        match = re.search(r"\b(striped|plaid|checkered|solid|patterned)\b", value)
        return match.group(1) if match else None

    def _wear_detail(self, value: str) -> str | None:
        for phrase in (
            "dirty lower right corner",
            "dirty spot",
            "worn corner",
            "scuffed",
            "scratched",
            "frayed",
            "stained",
            "wear and tear",
        ):
            if phrase in value:
                return phrase
        return None


class RelationalMemoryGraph:
    def __init__(self, db_path: Path, codec: EncryptedTextCodec) -> None:
        self.db_path = db_path
        self.codec = codec
        self.parser = PerceptionPacketParser()
        self.place_resolver = PlaceResolver()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS graph_entities (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    label_norm TEXT NOT NULL,
                    label TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    observation_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(kind, label_norm)
                );

                CREATE TABLE IF NOT EXISTS graph_places (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    provider_place_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    accuracy_m REAL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(provider, provider_place_id)
                );

                CREATE TABLE IF NOT EXISTS graph_events (
                    id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    observation_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS graph_relations (
                    id TEXT PRIMARY KEY,
                    subject_entity_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    object_entity_id TEXT,
                    object_text TEXT,
                    event_id TEXT,
                    place_id TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    observation_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS graph_attributes (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    attribute_key TEXT NOT NULL,
                    attribute_value TEXT NOT NULL,
                    source TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    observation_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(entity_id, attribute_key, attribute_value)
                );

                CREATE TABLE IF NOT EXISTS graph_observations (
                    id TEXT PRIMARY KEY,
                    captured_at TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    entity_id TEXT,
                    event_id TEXT,
                    place_id TEXT,
                    confidence REAL NOT NULL,
                    stability_count INTEGER NOT NULL,
                    scene_phase TEXT NOT NULL,
                    motion_score REAL,
                    evidence_cipher TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS graph_encounters (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    place_id TEXT REFERENCES graph_places(id) ON DELETE SET NULL,
                    session_id TEXT,
                    observation_count INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_encounters_open
                    ON graph_encounters(entity_id, started_at) WHERE ended_at IS NULL;

                CREATE INDEX IF NOT EXISTS idx_graph_entities_last_seen
                    ON graph_entities(last_seen_at DESC);
                CREATE INDEX IF NOT EXISTS idx_graph_relations_type
                    ON graph_relations(relation_type);
                CREATE INDEX IF NOT EXISTS idx_graph_attributes_entity
                    ON graph_attributes(entity_id);
                CREATE INDEX IF NOT EXISTS idx_graph_observations_captured
                    ON graph_observations(captured_at DESC);
                CREATE TABLE IF NOT EXISTS graph_messages (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    from_me INTEGER NOT NULL,
                    text_enc TEXT NOT NULL,
                    text_length INTEGER NOT NULL,
                    media_kind TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_graph_messages_entity
                    ON graph_messages(entity_id, sent_at);
                """
            )

    # ── Message corpus (encrypted at rest) ────────────────────────────────
    # The graph's digests (topics, commitments) answer "who is X" — but the
    # product bar is a text simulation of lived experience, so the actual
    # said-words must be retrievable: "what was the long message I wrote",
    # "what message mentioned good friday". Content is AES-GCM encrypted;
    # search decrypts per-contact scope only (sealed recall, never a dump).

    def replace_messages(self, entity_id: str, messages: list[dict]) -> int:
        """Replace the stored corpus for one contact (idempotent re-import).

        messages: [{ts, from_me, text, media_kind?}]
        """
        with self._connect() as conn:
            conn.execute("DELETE FROM graph_messages WHERE entity_id=?", (entity_id,))
            for m in messages:
                text = str(m.get("text") or "").strip()
                if not text:
                    continue
                conn.execute(
                    """INSERT INTO graph_messages
                       (id, entity_id, sent_at, from_me, text_enc, text_length, media_kind)
                       VALUES (?,?,?,?,?,?,?)""",
                    (str(uuid4()), entity_id, str(m.get("ts") or ""),
                     1 if m.get("from_me") else 0,
                     self.codec.encrypt(text), len(text), m.get("media_kind")),
                )
            return conn.execute(
                "SELECT COUNT(*) FROM graph_messages WHERE entity_id=?", (entity_id,)
            ).fetchone()[0]

    def search_messages(
        self,
        label: str,
        terms: list[str] | None = None,
        from_me: bool | None = None,
        date_prefixes: list[str] | None = None,
        longest: bool = False,
        limit: int = 3,
    ) -> list[dict]:
        """Sealed content search: one contact's corpus, decrypted in-process.

        Returns [{sent_at, from_me, text, media_kind}] best-first.
        """
        prof = self.resolve_person(label, limit=1)
        if not prof:
            return []
        entity_id = prof[0]["id"]
        sql = "SELECT sent_at, from_me, text_enc, text_length, media_kind FROM graph_messages WHERE entity_id=?"
        params: list[Any] = [entity_id]
        if from_me is not None:
            sql += " AND from_me=?"
            params.append(1 if from_me else 0)
        if date_prefixes:
            sql += " AND (" + " OR ".join("sent_at LIKE ?" for _ in date_prefixes) + ")"
            params.extend(p if "%" in p else f"{p}%" for p in date_prefixes)
        if longest:
            sql += " ORDER BY text_length DESC LIMIT 40"
        else:
            sql += " ORDER BY sent_at DESC LIMIT 4000"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        wanted = [t.lower() for t in (terms or []) if t]
        out: list[dict] = []
        for r in rows:
            try:
                text = self.codec.decrypt(r["text_enc"])
            except Exception:
                continue
            low = text.lower()
            if wanted and not all(t in low for t in wanted):
                continue
            out.append({
                "sent_at": r["sent_at"], "from_me": bool(r["from_me"]),
                "text": text, "media_kind": r["media_kind"],
            })
            if len(out) >= limit:
                break
        return out

    def ingest_packet(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("memory_text") or payload.get("text") or "").strip()
        if not text:
            raise ValueError("memory_text or text is required")

        captured_at = str(payload.get("captured_at") or payload.get("timestamp") or utc_now())
        source_type = str(payload.get("source_type") or payload.get("source") or "vision")
        provider = str(payload.get("provider") or payload.get("source") or "native_perception")
        scene_phase = str(payload.get("scene_phase") or "unknown")
        motion_score = self._float_or_none(payload.get("motion_score"))
        stability_count = int(payload.get("stability_count") or payload.get("observations") or 1)
        default_confidence = self._float_or_none(payload.get("confidence"))
        metadata = dict(payload.get("metadata") or {})
        if payload.get("location_hint") and "location_hint" not in metadata:
            metadata["location_hint"] = payload["location_hint"]

        place = self.place_resolver.from_payload({**payload, "metadata": metadata})
        facts = self.parser.parse_text(text, default_confidence=default_confidence)
        spatial_words = self._spatial_words_from_metadata(metadata)
        if not facts and not spatial_words:
            return {
                "captured_at": captured_at,
                "entities": 0,
                "events": 0,
                "relations": 0,
                "observations": 0,
                "place": asdict(place) if place else None,
            }

        entity_ids: list[str] = []
        event_ids: list[str] = []
        relation_ids: list[str] = []
        observation_ids: list[str] = []
        object_entity_ids_by_label: dict[str, str] = {}
        spatial_pose_attribute_ids: list[str] = []

        with self._connect() as conn:
            place_id = self._upsert_place(conn, place, captured_at) if place else None
            for fact in facts:
                if fact.ontology == "OBJECT":
                    entity_id = self._upsert_entity(conn, fact, captured_at, metadata, stability_count, scene_phase)
                    entity_ids.append(entity_id)
                    object_entity_ids_by_label[normalize_label(fact.label)] = entity_id
                    for attribute in self.parser.extract_attributes(fact):
                        self._upsert_attribute(
                            conn,
                            entity_id,
                            attribute,
                            captured_at,
                            fact.confidence,
                            metadata,
                            stability_count=stability_count,
                            scene_phase=scene_phase,
                        )
                    for relation in self.parser.extract_relations(fact, place):
                        relation_ids.append(
                            self._upsert_relation(
                                conn,
                                entity_id,
                                relation,
                                place_id,
                                captured_at,
                                fact.confidence,
                                metadata,
                                stability_count=stability_count,
                                scene_phase=scene_phase,
                            )
                        )
                        self._upsert_relation_attributes(
                            conn,
                            entity_id,
                            fact,
                            relation,
                            captured_at,
                            fact.confidence,
                            metadata,
                            stability_count=stability_count,
                            scene_phase=scene_phase,
                        )
                    observation_ids.append(
                        self._insert_observation(
                            conn,
                            captured_at,
                            source_type,
                            provider,
                            fact.confidence,
                            stability_count,
                            scene_phase,
                            motion_score,
                            fact.raw_text,
                            metadata,
                            entity_id=entity_id,
                            place_id=place_id,
                        )
                    )
                elif fact.ontology == "EVENT":
                    event_id = self._upsert_event(conn, fact, captured_at, metadata)
                    event_ids.append(event_id)
                    event_subject_id = self._upsert_event_subject(conn, fact, captured_at, metadata, stability_count, scene_phase)
                    if event_subject_id:
                        relation_ids.append(
                            self._upsert_relation(
                                conn,
                                event_subject_id,
                                ExtractedRelation("involved_in_event", object_text=fact.attributes),
                                place_id,
                                captured_at,
                                fact.confidence,
                                metadata,
                                event_id=event_id,
                                stability_count=stability_count,
                                scene_phase=scene_phase,
                            )
                        )
                        for relation in self.parser.extract_relations(fact, place):
                            relation_ids.append(
                                self._upsert_relation(
                                    conn,
                                    event_subject_id,
                                    relation,
                                    place_id,
                                    captured_at,
                                    fact.confidence,
                                    metadata,
                                    event_id=event_id,
                                    stability_count=stability_count,
                                    scene_phase=scene_phase,
                                )
                            )
                    if place_id:
                        relation_ids.append(
                            self._upsert_relation(
                                conn,
                                event_subject_id or self._upsert_entity(conn, fact, captured_at, metadata, stability_count, scene_phase),
                                ExtractedRelation("located_at", object_text=place.name if place else None),
                                place_id,
                                captured_at,
                                fact.confidence,
                                metadata,
                                event_id=event_id,
                                stability_count=stability_count,
                                scene_phase=scene_phase,
                            )
                        )
                    observation_ids.append(
                        self._insert_observation(
                            conn,
                            captured_at,
                            source_type,
                            provider,
                            fact.confidence,
                            stability_count,
                            scene_phase,
                            motion_score,
                            fact.raw_text,
                            metadata,
                            event_id=event_id,
                            place_id=place_id,
                        )
                    )

            if "active_entity_labels" in payload:
                active_norms = {normalize_label(str(label)) for label in payload["active_entity_labels"]}
                self._mark_inactive_entities_stale(conn, active_norms, captured_at, metadata)
            spatial_pose_attribute_ids.extend(
                self._upsert_spatial_word_map(
                    conn,
                    metadata,
                    spatial_words,
                    captured_at,
                    default_confidence if default_confidence is not None else 0.75,
                    object_entity_ids_by_label,
                )
            )

        return {
            "captured_at": captured_at,
            "entities": len(set(entity_ids)),
            "events": len(set(event_ids)),
            "relations": len(set(relation_ids)),
            "observations": len(observation_ids),
            "spatial_pose_attributes": len(set(spatial_pose_attribute_ids)),
            "place": asdict(place) if place else None,
        }

    def metadata(self, limit: int = 30) -> dict[str, Any]:
        with self._connect() as conn:
            counts = {
                "entities": conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0],
                "events": conn.execute("SELECT COUNT(*) FROM graph_events").fetchone()[0],
                "relations": conn.execute("SELECT COUNT(*) FROM graph_relations").fetchone()[0],
                "attributes": conn.execute("SELECT COUNT(*) FROM graph_attributes").fetchone()[0],
                "observations": conn.execute("SELECT COUNT(*) FROM graph_observations").fetchone()[0],
                "places": conn.execute("SELECT COUNT(*) FROM graph_places").fetchone()[0],
            }
            by_status = {
                row["status"]: row["count"]
                for row in conn.execute("SELECT status, COUNT(*) AS count FROM graph_entities GROUP BY status")
            }
            recent_entities = [dict(row) for row in conn.execute(
                """
                SELECT id, kind, label, last_seen_at, confidence, observation_count, status
                FROM graph_entities ORDER BY last_seen_at DESC LIMIT ?
                """,
                (limit,),
            )]
            recent_relations = [self._relation_row(row) for row in conn.execute(
                """
                SELECT r.id, r.relation_type, s.label AS subject, o.label AS object_label,
                       r.object_text, p.name AS place, r.last_seen_at, r.confidence,
                       r.observation_count, r.status
                FROM graph_relations r
                JOIN graph_entities s ON s.id = r.subject_entity_id
                LEFT JOIN graph_entities o ON o.id = r.object_entity_id
                LEFT JOIN graph_places p ON p.id = r.place_id
                ORDER BY r.last_seen_at DESC LIMIT ?
                """,
                (limit,),
            )]
            recent_places = [dict(row) for row in conn.execute(
                """
                SELECT provider, provider_place_id, name, latitude, longitude, accuracy_m, last_seen_at
                FROM graph_places ORDER BY last_seen_at DESC LIMIT ?
                """,
                (limit,),
            )]
            recent_attributes = [dict(row) for row in conn.execute(
                """
                SELECT a.id, e.label AS entity, e.kind, a.attribute_key, a.attribute_value,
                       a.source, a.last_seen_at, a.confidence, a.observation_count, a.status
                FROM graph_attributes a
                JOIN graph_entities e ON e.id = a.entity_id
                ORDER BY a.last_seen_at DESC LIMIT ?
                """,
                (limit,),
            )]
        return {
            **counts,
            "entities_by_status": by_status,
            "recent_entities": recent_entities,
            "recent_relations": recent_relations,
            "recent_attributes": recent_attributes,
            "recent_places": recent_places,
        }

    def query_relations(self, label: str | None = None, relation_type: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if label:
            clauses.append("(s.label_norm LIKE ? OR o.label_norm LIKE ? OR r.object_text LIKE ?)")
            needle = f"%{normalize_label(label)}%"
            params.extend([needle, needle, f"%{label}%"])
        if relation_type:
            clauses.append("r.relation_type = ?")
            params.append(relation_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            return [self._relation_row(row) for row in conn.execute(
                f"""
                SELECT r.id, r.relation_type, s.label AS subject, o.label AS object_label,
                       r.object_text, p.name AS place, r.last_seen_at, r.confidence,
                       r.observation_count, r.status
                FROM graph_relations r
                JOIN graph_entities s ON s.id = r.subject_entity_id
                LEFT JOIN graph_entities o ON o.id = r.object_entity_id
                LEFT JOIN graph_places p ON p.id = r.place_id
                {where}
                ORDER BY r.last_seen_at DESC LIMIT ?
                """,
                params,
            )]

    def ingest_vlm_enrichment(self, entity_id: str, vlm_description: str, captured_at: str) -> dict[str, str]:
        """Parse a free-text VLM description and upsert structured attributes for entity_id."""
        text = vlm_description.lower()
        attrs: dict[str, str] = {}

        age_m = re.search(r'\b(\d{1,3})\s*(?:year|yr)s?\s*old\b|\b(teen|young adult|middle.aged|elderly)\b', text)
        if age_m:
            attrs["approximate_age"] = age_m.group(1) or age_m.group(2) or ""

        for col in ("blond", "brown", "black", "gray", "grey", "white", "red", "auburn"):
            if re.search(rf"\bhair.*{col}|{col}.*hair\b", text):
                attrs["hair_color"] = col
                break

        clothing_m = re.search(
            r'\b(?P<color>red|blue|green|black|white|grey|gray|yellow|orange|purple|pink|navy|beige)\s+'
            r'(?P<type>shirt|t-shirt|blouse|jacket|coat|sweater|hoodie|top)\b', text
        )
        if clothing_m:
            attrs["clothing_top_color"] = clothing_m.group("color")
            attrs["clothing_top_type"] = clothing_m.group("type")

        for kw in ("stocky", "muscular", "slim", "slender", "average build", "broad"):
            if re.search(rf"\b{kw}\b", text):
                attrs["build"] = kw
                break

        expr_m = re.search(r'\b(smiling|neutral|frowning|surprised|happy|sad|angry)\b', text)
        if expr_m:
            attrs["expression"] = expr_m.group(1)

        with self._connect() as conn:
            for key, value in attrs.items():
                row = conn.execute(
                    "SELECT id, observation_count FROM graph_attributes WHERE entity_id=? AND attribute_key=? AND attribute_value=?",
                    (entity_id, key, value),
                ).fetchone()
                if row:
                    conn.execute(
                        "UPDATE graph_attributes SET last_seen_at=?, observation_count=? WHERE id=?",
                        (captured_at, int(row["observation_count"]) + 1, row["id"]),
                    )
                else:
                    conn.execute(
                        """INSERT INTO graph_attributes
                           (id, entity_id, attribute_key, attribute_value, source,
                            first_seen_at, last_seen_at, confidence, observation_count, status, metadata_json)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (str(uuid4()), entity_id, key, value, "vlm_enrichment",
                         captured_at, captured_at, 0.65, 1, "provisional", "{}"),
                    )
        return attrs

    def ingest_enrichment_detail(
        self,
        entity_id: str,
        detail_focus: str,
        description: str,
        captured_at: str,
        level: int = 1,
    ) -> str:
        """Store one progressive-enrichment pass verbatim as an attribute.

        Keys are vlm_overview / vlm_attributes / vlm_minutiae — the ladder's
        knowledge depth is visible in the graph itself, with provenance.
        """
        key = f"vlm_{detail_focus}"
        value = " ".join(description.split())[:600]
        if not value:
            return ""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM graph_attributes WHERE entity_id=? AND attribute_key=?",
                (entity_id, key),
            ).fetchone()
            if row:
                conn.execute(
                    """UPDATE graph_attributes
                       SET attribute_value=?, last_seen_at=?,
                           observation_count=observation_count+1
                       WHERE id=?""",
                    (value, captured_at, row["id"]),
                )
                return str(row["id"])
            new_id = str(uuid4())
            conn.execute(
                """INSERT INTO graph_attributes
                   (id, entity_id, attribute_key, attribute_value, source,
                    first_seen_at, last_seen_at, confidence, observation_count, status, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (new_id, entity_id, key, value, "vlm_enrichment",
                 captured_at, captured_at, 0.7, 1, "provisional",
                 json.dumps({"level": level})),
            )
            return new_id

    def search_messages_all(
        self, terms: list[str], from_me: bool | None = None, limit: int = 8
    ) -> list[dict]:
        """Corpus-wide content search for reverse questions
        ('who did I send the good friday message to')."""
        wanted = [t.lower() for t in terms if t]
        if not wanted:
            return []
        sql = """SELECT m.entity_id, m.sent_at, m.from_me, m.text_enc, e.label
                 FROM graph_messages m JOIN graph_entities e ON e.id = m.entity_id
                 WHERE e.status != 'archived'"""
        params: list[Any] = []
        if from_me is not None:
            sql += " AND m.from_me=?"
            params.append(1 if from_me else 0)
        sql += " ORDER BY m.sent_at DESC"
        out: list[dict] = []
        with self._connect() as conn:
            for r in conn.execute(sql, params):
                try:
                    text = self.codec.decrypt(r["text_enc"])
                except Exception:
                    continue
                low = text.lower()
                if all(t in low for t in wanted):
                    out.append({
                        "contact": r["label"], "sent_at": r["sent_at"],
                        "from_me": bool(r["from_me"]), "text": text,
                    })
                    if len(out) >= limit:
                        break
        return out

    # Sentence-leading capitalized words that are grammar, not names.
    _QUESTION_WORDS = frozenset(
        "what who whom whose where when why how did do does is are was were "
        "the my our tell show find which i has have had can could should "
        "would will whats about and or in on at to from with anything "
        "something everything please give list".split()
    )

    def context_bundle(self, question: str, since: str | None = None) -> list[dict]:
        """Deterministic sealed retrieval for grounded answering.

        Returns context items [{kind, label, text, observed, source}] —
        person fact sheets, their recent/longest messages, corpus-wide
        content hits, and matching object entities with vision facts. The
        LLM layer may ONLY answer from these items.

        `since` (ISO timestamp) restricts vision facts to observations at or
        after that moment — walk-1 lesson: desk-era facts answering
        "during my walk" questions produced a 75% hallucination rate.
        """
        items: list[dict] = []
        # candidate person names: capitalized runs, minus grammar words —
        # 'What did Ziwei Zhang send' must yield 'Ziwei Zhang', never 'What'.
        names: list[str] = []
        for run in re.findall(r"\b([A-Z][\w'.ß-]*(?:\s+[A-Z][\w'.ß-]*){0,3})\b", question):
            tokens = run.split()
            while tokens and tokens[0].lower() in self._QUESTION_WORDS:
                tokens.pop(0)
            while tokens and tokens[-1].lower() in self._QUESTION_WORDS:
                tokens.pop()
            if tokens:
                names.append(" ".join(tokens))
        # lowercase names ('what did ziwei say') — substring match only, no
        # fuzzy: fuzzy on arbitrary words drags random contacts into context.
        # PERSONS only: profiles() also matches object entities ('bottle').
        if not names:
            for t in re.split(r"\W+", question.lower()):
                if len(t) >= 4 and t not in self._QUESTION_WORDS:
                    hits = self.profiles(label=t, limit=3).get("profiles", [])
                    if any(p.get("kind") == "person" for p in hits):
                        names.append(t)
                if len(names) >= 2:
                    break
        seen_ids: set[str] = set()
        for name in names[:3]:
            for p in self.resolve_person(name, limit=1):
                if p.get("kind") not in (None, "person"):
                    continue
                if p["id"] in seen_ids:
                    continue
                seen_ids.add(p["id"])
                cs = p.get("canonical_slots") or {}
                facts = "; ".join(
                    f"{k}={str(v.get('value'))[:160]}"
                    for k, v in cs.items()
                    if k != "recent_messages" and v.get("value")
                )
                items.append({
                    "kind": "person_facts", "label": p.get("label", ""),
                    "text": facts, "observed": p.get("last_seen_at", ""),
                    "source": "graph",
                })
                arc = (cs.get("recent_messages") or {}).get("value") or ""
                if arc:
                    items.append({
                        "kind": "conversation_sample", "label": p.get("label", ""),
                        "text": arc[:1200], "observed": "", "source": "whatsapp",
                    })
                for m in self.search_messages(p.get("label", ""), longest=True, limit=2):
                    items.append({
                        "kind": "longest_message", "label": p.get("label", ""),
                        "text": f"[{m['sent_at'][:10]}, {'you' if m['from_me'] else 'them'}] {m['text'][:600]}",
                        "observed": m["sent_at"], "source": "whatsapp",
                    })
                for m in self.search_messages(p.get("label", ""), limit=5):
                    items.append({
                        "kind": "recent_message", "label": p.get("label", ""),
                        "text": f"[{m['sent_at'][:10]}, {'you' if m['from_me'] else 'them'}] {m['text'][:280]}",
                        "observed": m["sent_at"], "source": "whatsapp",
                    })
        # content terms → corpus-wide hits (reverse questions)
        stop = {"what", "was", "the", "who", "did", "i", "send", "sent", "message",
                "messages", "with", "where", "are", "is", "my", "to", "in", "or",
                "and", "a", "an", "of", "currently", "right", "now", "located",
                "relationship", "between", "me", "him", "her", "does", "do", "have"}
        terms = [t for t in re.split(r"\W+", question.lower()) if len(t) >= 3 and t not in stop]
        person_words = {w.lower() for n in names for w in n.split()}
        content_terms = [t for t in terms if t not in person_words][:4]
        if content_terms:
            for m in self.search_messages_all(content_terms, limit=6):
                items.append({
                    "kind": "message_hit", "label": m["contact"],
                    "text": f"[{m['sent_at'][:10]}, {'you' if m['from_me'] else m['contact']}] {m['text'][:280]}",
                    "observed": m["sent_at"], "source": "whatsapp",
                })
        # object entities mentioned (glasses, shoes…) — match each term and
        # its singular ('shoes' must find a 'shoe' entity), and match
        # attribute VALUES too ('white' finds the entity with color=white).
        object_ids: set[str] = set()
        with self._connect() as conn:
            variants: list[str] = []
            for t in terms[:6]:
                variants.append(t)
                if t.endswith("es") and len(t) > 4:
                    variants.append(t[:-2])
                if t.endswith("s") and len(t) > 3:
                    variants.append(t[:-1])
            for t in variants:
                rows = conn.execute(
                    """SELECT id, label, last_seen_at FROM graph_entities
                       WHERE status != 'archived' AND kind != 'person'
                         AND label_norm LIKE ? AND last_seen_at >= ? LIMIT 2""",
                    (f"%{t}%", since or ""),
                ).fetchall()
                value_rows = conn.execute(
                    """SELECT DISTINCT e.id, e.label, e.last_seen_at, e.kind
                       FROM graph_attributes a JOIN graph_entities e ON e.id = a.entity_id
                       WHERE e.status != 'archived' AND a.status != 'archived'
                         AND a.attribute_key NOT IN ('recent_messages', 'open_commitments', 'commitments_to_me')
                         AND a.attribute_value LIKE ? AND e.last_seen_at >= ? LIMIT 3""",
                    (f"%{t}%", since or ""),
                ).fetchall()
                for r in list(rows) + list(value_rows):
                    if r["id"] in object_ids or r["id"] in seen_ids:
                        continue
                    object_ids.add(r["id"])
                    attrs = conn.execute(
                        """SELECT attribute_key, attribute_value, last_seen_at
                           FROM graph_attributes
                           WHERE entity_id=? AND status != 'archived' LIMIT 12""",
                        (r["id"],),
                    ).fetchall()
                    # Walk-1 lesson: every visual fact carries its observation
                    # date so the answer can say "as of June 8 at your desk"
                    # instead of presenting stale facts as current.
                    facts = "; ".join(
                        f"{a['attribute_key']}={str(a['attribute_value'])[:120]}"
                        f" [observed {str(a['last_seen_at'])[:10]}]"
                        for a in attrs if a["attribute_key"] != "recent_messages"
                    )
                    is_person = (r["kind"] if "kind" in r.keys() else "") == "person"
                    items.append({
                        "kind": "person_facts" if is_person else "object_facts",
                        "label": r["label"],
                        "text": facts or "seen by camera, not yet studied",
                        "observed": r["last_seen_at"], "source": "vision",
                    })
        return items[:24]

    def distance_covered_km(self, since: str, until: str | None = None) -> tuple[float, int]:
        """Deterministic GPS polyline distance from observation location
        hints in a time window. Returns (km, fix_count). Walk-1 Q25: the
        data was all in the graph; no aggregation existed to answer it."""
        import math
        gps_re = re.compile(r"GPS\s+(-?\d+\.\d+),\s*(-?\d+\.\d+)")
        points: list[tuple[str, float, float]] = []
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT captured_at, metadata_json FROM graph_observations
                   WHERE captured_at >= ? AND captured_at <= ?
                   ORDER BY captured_at""",
                (since, until or "9999"),
            ).fetchall()
        for r in rows:
            m = gps_re.search(str(r["metadata_json"] or ""))
            if m:
                points.append((r["captured_at"], float(m.group(1)), float(m.group(2))))
        if len(points) < 2:
            return 0.0, len(points)
        total = 0.0
        prev = points[0]
        for cur in points[1:]:
            lat1, lon1, lat2, lon2 = map(math.radians, (prev[1], prev[2], cur[1], cur[2]))
            a = (math.sin((lat2 - lat1) / 2) ** 2
                 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
            seg = 6371.0 * 2 * math.asin(math.sqrt(a))
            if seg < 0.5:  # discard GPS teleports (>500m between fixes)
                total += seg
            prev = cur
        return total, len(points)

    def known_object_labels(self, limit: int = 6) -> list[str]:
        """Most recently seen non-person entities — used by honest-miss
        answers ('I haven't seen X; here's what I do know')."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT label FROM graph_entities
                   WHERE status != 'archived' AND kind != 'person'
                   ORDER BY last_seen_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [r["label"] for r in rows]

    def spatial_object_locations(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """Object entities with current spatial_pose attributes matching query."""
        query_norm = normalize_label(query)
        if not query_norm:
            return []

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT e.id AS entity_id, e.label, e.label_norm, e.observation_count,
                       e.last_seen_at AS entity_last_seen, a.attribute_value,
                       a.last_seen_at AS pose_last_seen, a.metadata_json
                FROM graph_entities e
                JOIN graph_attributes a ON a.entity_id = e.id
                WHERE e.kind = 'object'
                  AND e.status != 'archived'
                  AND a.attribute_key = 'spatial_pose'
                  AND a.status != 'archived'
                ORDER BY a.last_seen_at DESC
                LIMIT 500
                """
            ).fetchall()

        matches: list[dict[str, Any]] = []
        for row in rows:
            label = str(row["label"] or "")
            label_norm = str(row["label_norm"] or normalize_label(label))
            match_score = self._label_match_score(query_norm, label_norm)
            if match_score < 0.62:
                continue
            try:
                pose = json.loads(row["attribute_value"] or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                metadata = {}
            if self._trust_value(pose.get("trust") or metadata.get("trust")) == "rejected":
                continue
            sightings = self._int_or_default(
                pose.get("sightings"),
                self._int_or_default(row["observation_count"], 1),
            )
            verified = self._bool_or_false(pose.get("verified"))
            last_seen = str(pose.get("last_seen") or row["pose_last_seen"] or row["entity_last_seen"] or "")
            matches.append(
                {
                    "entity_id": str(row["entity_id"]),
                    "label": label,
                    "x": self._float_or_none(pose.get("x")) or 0,
                    "y": self._float_or_none(pose.get("y")) or 0,
                    "z": self._float_or_none(pose.get("z")) or 0,
                    "w": self._float_or_none(pose.get("w")) or 0,
                    "h": self._float_or_none(pose.get("h")) or 0,
                    "support_plane": self._support_plane_value(pose.get("support_plane")),
                    "verified": verified,
                    "frame": str(pose.get("frame") or "genesis"),
                    "last_seen": last_seen,
                    "sightings": sightings,
                    "match_score": match_score,
                }
            )
        matches.sort(key=lambda item: (item["sightings"], item["match_score"], item["last_seen"]), reverse=True)
        return matches[:limit]

    @staticmethod
    def _label_match_score(query_norm: str, label_norm: str) -> float:
        if not query_norm or not label_norm:
            return 0.0
        if query_norm == label_norm:
            return 1.0
        if query_norm in label_norm or label_norm in query_norm:
            return 0.9

        import difflib
        query_tokens = {token for token in re.split(r"[/\s-]+", query_norm) if token}
        label_tokens = {token for token in re.split(r"[/\s-]+", label_norm) if token}
        token_score = 0.0
        if query_tokens and label_tokens:
            overlap = len(query_tokens & label_tokens)
            token_score = overlap / max(len(query_tokens), 1)
            if query_tokens <= label_tokens:
                token_score = max(token_score, 0.85)
        ratio = difflib.SequenceMatcher(None, query_norm, label_norm).ratio()
        return max(token_score, ratio)

    def resolve_person(self, query: str, limit: int = 3) -> list[dict]:
        """Person lookup that survives real-world queries: exact/substring
        first, then phone-number digit matching ('+1 307 257-6742' vs
        '+1 (307) 257-6742'), then fuzzy spelling ('Amirhossain' →
        'Amirhossein'). A one-character difference must not mean amnesia."""
        query = (query or "").strip()
        if not query:
            return []
        hits = self.profiles(label=query, limit=limit).get("profiles", [])
        if hits:
            return hits

        digits = re.sub(r"\D", "", query)
        if len(digits) >= 7:
            tail = digits[-9:]
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT DISTINCT entity_id FROM graph_attributes
                       WHERE attribute_key='contact_identifier'""").fetchall()
                id_match: list[str] = []
                for r in rows:
                    val = conn.execute(
                        "SELECT attribute_value FROM graph_attributes WHERE entity_id=? AND attribute_key='contact_identifier'",
                        (r["entity_id"],),
                    ).fetchone()
                    if val and tail in re.sub(r"\D", "", str(val[0])):
                        id_match.append(r["entity_id"])
            for p in self.profiles(limit=500).get("profiles", []):
                if p["id"] in id_match or tail in re.sub(r"\D", "", p.get("label") or ""):
                    hits.append(p)
                    if len(hits) >= limit:
                        break
            if hits:
                return hits

        import difflib
        allp = self.profiles(limit=500).get("profiles", [])
        labels = {(p.get("label") or "").lower(): p for p in allp if p.get("kind") == "person"}
        close = difflib.get_close_matches(query.lower(), list(labels), n=limit, cutoff=0.72)
        if not close:
            # try first-token match: "Amirhossain" vs "Amirhossein Kazemi"
            firsts = {(p.get("label") or "").split()[0].lower(): p
                      for p in allp if p.get("kind") == "person" and p.get("label")}
            close_first = difflib.get_close_matches(query.lower(), list(firsts), n=limit, cutoff=0.72)
            return [firsts[c] for c in close_first]
        return [labels[c] for c in close]

    def profiles(self, label: str | None = None, limit: int = 30) -> dict[str, Any]:
        # Archived entities (e.g. superseded duplicate contacts) never
        # surface in recall.
        clauses: list[str] = ["e.status != 'archived'"]
        params: list[Any] = []
        if label:
            clauses.append("e.label_norm LIKE ?")
            params.append(f"%{normalize_label(label)}%")
        where = f"WHERE {' AND '.join(clauses)}"
        params.append(limit)

        with self._connect() as conn:
            entity_rows = [dict(row) for row in conn.execute(
                f"""
                SELECT e.id, e.kind, e.label, e.label_norm, e.first_seen_at, e.last_seen_at,
                       e.confidence, e.observation_count, e.status
                FROM graph_entities e
                {where}
                ORDER BY
                    CASE e.status WHEN 'current' THEN 0 WHEN 'provisional' THEN 1 ELSE 2 END,
                    e.last_seen_at DESC
                LIMIT ?
                """,
                params,
            )]
            entity_ids = [row["id"] for row in entity_rows]
            if not entity_ids:
                return {"profiles": []}

            placeholders = ",".join("?" for _ in entity_ids)
            attribute_rows = [dict(row) for row in conn.execute(
                f"""
                SELECT entity_id, attribute_key, attribute_value, source, last_seen_at,
                       confidence, observation_count, status
                FROM graph_attributes
                WHERE entity_id IN ({placeholders})
                ORDER BY
                    CASE status WHEN 'current' THEN 0 WHEN 'provisional' THEN 1 ELSE 2 END,
                    observation_count DESC,
                    last_seen_at DESC
                """,
                entity_ids,
            )]
            relation_rows = [dict(row) for row in conn.execute(
                f"""
                SELECT r.id, r.subject_entity_id, r.relation_type, s.label AS subject,
                       o.label AS object_label, r.object_text, p.name AS place,
                       r.last_seen_at, r.confidence, r.observation_count, r.status
                FROM graph_relations r
                JOIN graph_entities s ON s.id = r.subject_entity_id
                LEFT JOIN graph_entities o ON o.id = r.object_entity_id
                LEFT JOIN graph_places p ON p.id = r.place_id
                WHERE r.subject_entity_id IN ({placeholders})
                ORDER BY
                    CASE r.status WHEN 'current' THEN 0 WHEN 'provisional' THEN 1 ELSE 2 END,
                    r.observation_count DESC,
                    r.last_seen_at DESC
                """,
                entity_ids,
            )]

        attributes_by_entity: dict[str, list[dict[str, Any]]] = {entity_id: [] for entity_id in entity_ids}
        for row in attribute_rows:
            attributes_by_entity.setdefault(str(row["entity_id"]), []).append(row)

        relations_by_subject: dict[str, list[dict[str, Any]]] = {entity_id: [] for entity_id in entity_ids}
        for row in relation_rows:
            subject_id = str(row.pop("subject_entity_id"))
            relations_by_subject.setdefault(subject_id, []).append(
                {
                    "id": row["id"],
                    "relation_type": row["relation_type"],
                    "subject": row["subject"],
                    "object": row["object_label"] or row["object_text"] or row["place"],
                    "place": row["place"],
                    "last_seen_at": row["last_seen_at"],
                    "confidence": row["confidence"],
                    "observation_count": row["observation_count"],
                    "status": row["status"],
                }
            )

        profiles = []
        for entity in entity_rows:
            entity_id = str(entity["id"])
            slot_rows = attributes_by_entity.get(entity_id, [])
            slots: dict[str, list[dict[str, Any]]] = {}
            for row in slot_rows:
                slot = {
                    "value": row["attribute_value"],
                    "source": row["source"],
                    "confidence": row["confidence"],
                    "observation_count": row["observation_count"],
                    "status": row["status"],
                    "last_seen_at": row["last_seen_at"],
                }
                slots.setdefault(row["attribute_key"], []).append(slot)

            slot_order = self._profile_slot_order(str(entity["kind"]), str(entity["label"]))
            canonical_slots = self._canonical_slots(slots, slot_order)
            profiles.append(
                {
                    "id": entity_id,
                    "kind": entity["kind"],
                    "label": entity["label"],
                    "first_seen_at": entity["first_seen_at"],
                    "last_seen_at": entity["last_seen_at"],
                    "confidence": entity["confidence"],
                    "observation_count": entity["observation_count"],
                    "status": entity["status"],
                    "slots": slots,
                    "canonical_slots": canonical_slots,
                    "canonical_summary": [
                        f"{key}={slot['value']}"
                        for key, slot in canonical_slots.items()
                    ],
                    "slot_order": slot_order,
                    "missing_slots": [
                        slot
                        for slot in slot_order
                        if slot not in slots
                    ],
                    "relations": relations_by_subject.get(entity_id, [])[:20],
                }
            )

        return {"profiles": profiles}

    def delete_all(self) -> int:
        tables = ["graph_observations", "graph_attributes", "graph_relations", "graph_events", "graph_entities", "graph_places"]
        with self._connect() as conn:
            total = sum(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables)
            for table in tables:
                conn.execute(f"DELETE FROM {table}")
        return int(total)

    def _upsert_entity(
        self,
        conn: sqlite3.Connection,
        fact: PerceptionFact,
        captured_at: str,
        metadata: dict[str, Any],
        stability_count: int = 1,
        scene_phase: str = "unknown",
    ) -> str:
        label_norm = self._normalized_label_for_fact(fact)
        kind = label_kind(fact.label)
        row = conn.execute(
            "SELECT id, label_norm, confidence, observation_count, status FROM graph_entities WHERE kind = ? AND label_norm = ?",
            (kind, label_norm),
        ).fetchone()
        if not row and kind == "text_surface":
            row = self._find_text_surface_entity(conn, fact, label_norm)
        if row:
            stored_label_norm = str(row["label_norm"])
            resolved_label_norm = (
                self._resolve_text_surface_label_norm(stored_label_norm, label_norm)
                if kind == "text_surface"
                else stored_label_norm
            )
            confidence = max(float(row["confidence"]), fact.confidence)
            observations = int(row["observation_count"]) + 1
            status = "current" if row["status"] == "current" else self._entity_status(
                fact, observations, stability_count, scene_phase, confidence
            )
            conn.execute(
                """
                UPDATE graph_entities
                SET label_norm = ?, label = ?, last_seen_at = ?, confidence = ?, observation_count = ?,
                    status = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    resolved_label_norm,
                    self._preferred_label(str(fact.label), resolved_label_norm),
                    captured_at,
                    confidence,
                    observations,
                    status,
                    json.dumps(metadata, sort_keys=True),
                    row["id"],
                ),
            )
            return str(row["id"])

        entity_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO graph_entities (
                id, kind, label_norm, label, first_seen_at, last_seen_at, confidence,
                observation_count, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_id,
                kind,
                label_norm,
                self._preferred_label(str(fact.label), label_norm),
                captured_at,
                captured_at,
                fact.confidence,
                1,
                self._entity_status(fact, 1, stability_count, scene_phase, fact.confidence),
                json.dumps(metadata, sort_keys=True),
            ),
        )

        if kind == "person":
            self._upsert_encounter(conn, entity_id, captured_at)

        return entity_id

    def _upsert_encounter(self, conn: sqlite3.Connection, entity_id: str, captured_at: str) -> None:
        from datetime import timedelta
        cutoff = (datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
                  - timedelta(hours=4)).isoformat()
        row = conn.execute(
            "SELECT id, observation_count FROM graph_encounters WHERE entity_id=? AND ended_at IS NULL AND started_at>=?",
            (entity_id, cutoff),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE graph_encounters SET observation_count=? WHERE id=?",
                (int(row["observation_count"]) + 1, row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO graph_encounters (id, entity_id, started_at, observation_count) VALUES (?,?,?,1)",
                (str(uuid4()), entity_id, captured_at),
            )

    def close_stale_encounters(self, older_than_minutes: int = 240) -> None:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(minutes=older_than_minutes)).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE graph_encounters SET ended_at=? WHERE ended_at IS NULL AND started_at<?",
                (now.isoformat(), cutoff),
            )

    def start_stale_encounter_cleaner(self, interval_seconds: int = 1800) -> None:
        import threading
        def _run() -> None:
            self.close_stale_encounters()
            threading.Timer(interval_seconds, _run).start()
        t = threading.Timer(interval_seconds, _run)
        t.daemon = True
        t.start()

    def promote_confident_entities(self, min_observations: int = 3) -> dict[str, int]:
        """Promote provisional entities/relations that have been observed enough times."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE graph_entities SET status='current', confidence=MIN(confidence*1.4, 0.95) "
                "WHERE status='provisional' AND observation_count >= ?",
                (min_observations,),
            )
            entities_promoted = conn.execute("SELECT changes()").fetchone()[0]
            conn.execute(
                "UPDATE graph_relations SET status='current', confidence=MIN(confidence*1.4, 0.95) "
                "WHERE status='provisional' AND observation_count >= ?",
                (min_observations,),
            )
            relations_promoted = conn.execute("SELECT changes()").fetchone()[0]
        return {"entities_promoted": entities_promoted, "relations_promoted": relations_promoted}

    def prune_stale_entities(self, days: int = 7) -> dict[str, int]:
        """Delete single-observation provisional entities older than N days and orphaned relations."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM graph_entities WHERE status='provisional' AND observation_count=1 "
                "AND last_seen_at < datetime('now', '-' || ? || ' days')",
                (days,),
            )
            entities_pruned = conn.execute("SELECT changes()").fetchone()[0]
            conn.execute(
                "DELETE FROM graph_relations WHERE subject_entity_id NOT IN (SELECT id FROM graph_entities) "
                "OR (object_entity_id IS NOT NULL AND object_entity_id NOT IN (SELECT id FROM graph_entities))"
            )
            relations_pruned = conn.execute("SELECT changes()").fetchone()[0]
        return {"entities_pruned": entities_pruned, "relations_pruned": relations_pruned}

    def start_pruner(self, interval_seconds: int = 86400) -> None:
        import threading
        def _run() -> None:
            self.prune_stale_entities()
            threading.Timer(interval_seconds, _run).start()
        t = threading.Timer(interval_seconds, _run)
        t.daemon = True
        t.start()

    def start_confidence_promoter(self, interval_seconds: int = 3600) -> None:
        import threading
        def _run() -> None:
            self.promote_confident_entities()
            threading.Timer(interval_seconds, _run).start()
        t = threading.Timer(interval_seconds, _run)
        t.daemon = True
        t.start()

    def link_person_name(self, encounter_label: str, real_name: str, source: str = "manual") -> dict:
        """Link a real name to a person entity encountered by the camera."""
        from uuid import uuid4
        label_norm = normalize_label(encounter_label)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM graph_entities WHERE kind='person' AND label_norm=?", (label_norm,)
            ).fetchone()
            if not row:
                return {"error": f"No person entity found for label '{encounter_label}'"}
            entity_id = row["id"]
            # Check if a real_name attribute from this source already exists
            existing = conn.execute(
                "SELECT id FROM graph_attributes WHERE entity_id=? AND attribute_key='real_name' AND source=?",
                (entity_id, source),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE graph_attributes SET attribute_value=?, status='current', confidence=1.0, last_seen_at=datetime('now') WHERE id=?",
                    (real_name, existing["id"]),
                )
                attribute_id = existing["id"]
            else:
                attribute_id = str(uuid4())
                conn.execute(
                    """INSERT INTO graph_attributes
                       (id, entity_id, attribute_key, attribute_value, source, status,
                        confidence, observation_count, first_seen_at, last_seen_at, metadata_json)
                       VALUES (?,?,?,?,?,?,?,?,datetime('now'),datetime('now'),?)""",
                    (attribute_id, entity_id, "real_name", real_name, source, "current", 1.0, 1, "{}"),
                )
        return {"entity_id": entity_id, "attribute_id": attribute_id}

    def recent_people(self, hours: int = 24) -> list[dict]:
        """Person entities the camera actually encountered in the last N
        hours. 'Who did I see today' means sightings — an encounter row in
        the window — never imported contacts whose rows were merely touched
        (a daemon repair once made this answer '210 people today')."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT e.id, e.label, e.last_seen_at, e.observation_count "
                "FROM graph_entities e JOIN graph_encounters enc ON enc.entity_id = e.id "
                "WHERE e.kind='person' AND e.status != 'archived' "
                "  AND COALESCE(enc.ended_at, enc.started_at) >= datetime('now', '-' || ? || ' hours') "
                "ORDER BY e.last_seen_at DESC",
                (hours,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_entity_attribute(self, entity_id: str, attribute_key: str) -> str | None:
        """Return the most recent active attribute value for an entity."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT attribute_value FROM graph_attributes
                WHERE entity_id = ? AND attribute_key = ?
                  AND status IN ('current', 'provisional')
                ORDER BY last_seen_at DESC LIMIT 1
                """,
                (entity_id, attribute_key),
            ).fetchone()
        return str(row["attribute_value"]) if row else None

    def _upsert_event_subject(
        self,
        conn: sqlite3.Connection,
        fact: PerceptionFact,
        captured_at: str,
        metadata: dict[str, Any],
        stability_count: int,
        scene_phase: str,
    ) -> str | None:
        label = fact.label
        if not label or label.lower() in {"nearby speech", "speech", "conversation"}:
            return None
        return self._upsert_entity(conn, fact, captured_at, metadata, stability_count, scene_phase)

    def _upsert_event(self, conn: sqlite3.Connection, fact: PerceptionFact, captured_at: str, metadata: dict[str, Any]) -> str:
        event_type = normalize_label(fact.label or "event")
        location_hint = str(metadata.get("location_hint", "") or "")
        confidence = float(fact.confidence) if fact.confidence is not None else 0.0

        # Phase 7 dedup: within 5-minute window, same event_type + location → update only.
        # Prevents observation flood when repeated identical events are detected at same spot.
        dedup_row = conn.execute(
            """
            SELECT id, confidence, observation_count, status
            FROM graph_events
            WHERE event_type = ? AND status IN ('current', 'provisional')
              AND last_seen_at >= datetime('now', '-5 minutes')
              AND json_extract(metadata_json, '$.location_hint') IS ?
            ORDER BY last_seen_at DESC LIMIT 1
            """,
            (event_type, location_hint or None),
        ).fetchone()
        if dedup_row:
            new_confidence = max(float(dedup_row["confidence"]), confidence)
            conn.execute(
                "UPDATE graph_events SET last_seen_at = ?, confidence = ?, observation_count = observation_count + 1 WHERE id = ?",
                (captured_at, new_confidence, dedup_row["id"]),
            )
            return str(dedup_row["id"])

        # Broader 7-day upsert for events seen before (same type, any location)
        row = conn.execute(
            """
            SELECT id, confidence, observation_count, status
            FROM graph_events
            WHERE event_type = ? AND status IN ('current', 'provisional')
              AND last_seen_at >= datetime('now', '-7 days')
            ORDER BY last_seen_at DESC LIMIT 1
            """,
            (event_type,),
        ).fetchone()
        if row:
            observations = int(row["observation_count"]) + 1
            confidence = max(float(row["confidence"]), fact.confidence)
            status = "current" if fact.certainty == "likely" else row["status"]
            summary = " | ".join(part for part in [fact.label, fact.attributes, fact.relation_text] if part)
            conn.execute(
                """
                UPDATE graph_events
                SET summary = ?, last_seen_at = ?, confidence = ?, observation_count = ?,
                    status = ?, metadata_json = ?
                WHERE id = ?
                """,
                (summary, captured_at, confidence, observations, status, json.dumps(metadata, sort_keys=True), row["id"]),
            )
            return str(row["id"])

        event_id = str(uuid4())
        summary = " | ".join(part for part in [fact.label, fact.attributes, fact.relation_text] if part)
        conn.execute(
            """
            INSERT INTO graph_events (
                id, event_type, summary, first_seen_at, last_seen_at, confidence,
                observation_count, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event_type,
                summary,
                captured_at,
                captured_at,
                fact.confidence,
                1,
                "current" if fact.certainty == "likely" else "provisional",
                json.dumps(metadata, sort_keys=True),
            ),
        )
        return event_id

    def _upsert_place(self, conn: sqlite3.Connection, place: PlaceCandidate, captured_at: str) -> str:
        row = conn.execute(
            "SELECT id FROM graph_places WHERE provider = ? AND provider_place_id = ?",
            (place.provider, place.provider_place_id),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE graph_places
                SET name = ?, latitude = ?, longitude = ?, accuracy_m = ?, last_seen_at = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    place.name,
                    place.latitude,
                    place.longitude,
                    place.accuracy_m,
                    captured_at,
                    json.dumps(place.metadata or {}, sort_keys=True),
                    row["id"],
                ),
            )
            return str(row["id"])

        place_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO graph_places (
                id, provider, provider_place_id, name, latitude, longitude,
                accuracy_m, first_seen_at, last_seen_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                place_id,
                place.provider,
                place.provider_place_id,
                place.name,
                place.latitude,
                place.longitude,
                place.accuracy_m,
                captured_at,
                captured_at,
                json.dumps(place.metadata or {}, sort_keys=True),
            ),
        )
        return place_id

    def _upsert_relation(
        self,
        conn: sqlite3.Connection,
        subject_entity_id: str,
        relation: ExtractedRelation,
        place_id: str | None,
        captured_at: str,
        confidence: float,
        metadata: dict[str, Any],
        event_id: str | None = None,
        stability_count: int = 1,
        scene_phase: str = "unknown",
    ) -> str:
        object_entity_id = None
        object_text = relation.object_text
        relation_place_id = place_id if relation.relation_type == "located_at" else None

        if relation.object_label:
            object_fact = PerceptionFact(
                ontology="OBJECT",
                label=relation.object_label,
                attributes="relation target",
                relation_text="",
                certainty="likely",
                raw_text=relation.object_label,
                confidence=confidence,
            )
            object_entity_id = self._upsert_entity(conn, object_fact, captured_at, metadata, stability_count, scene_phase)
            object_text = None

        row = conn.execute(
            """
            SELECT id, confidence, observation_count, status
            FROM graph_relations
            WHERE subject_entity_id = ?
              AND relation_type = ?
              AND COALESCE(object_entity_id, '') = COALESCE(?, '')
              AND COALESCE(object_text, '') = COALESCE(?, '')
              AND COALESCE(event_id, '') = COALESCE(?, '')
              AND COALESCE(place_id, '') = COALESCE(?, '')
            """,
            (subject_entity_id, relation.relation_type, object_entity_id, object_text, event_id, relation_place_id),
        ).fetchone()
        if row:
            observations = int(row["observation_count"]) + 1
            effective_confidence = max(float(row["confidence"]), confidence)
            status = "current" if row["status"] == "current" else self._relation_status(
                effective_confidence, observations, stability_count, scene_phase
            )
            conn.execute(
                """
                UPDATE graph_relations
                SET last_seen_at = ?, confidence = ?, observation_count = ?, status = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    captured_at,
                    effective_confidence,
                    observations,
                    status,
                    json.dumps(metadata, sort_keys=True),
                    row["id"],
                ),
            )
            return str(row["id"])

        relation_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO graph_relations (
                id, subject_entity_id, relation_type, object_entity_id, object_text,
                event_id, place_id, first_seen_at, last_seen_at, confidence,
                observation_count, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                relation_id,
                subject_entity_id,
                relation.relation_type,
                object_entity_id,
                object_text,
                event_id,
                relation_place_id,
                captured_at,
                captured_at,
                confidence,
                1,
                self._relation_status(confidence, 1, stability_count, scene_phase),
                json.dumps(metadata, sort_keys=True),
            ),
        )
        return relation_id

    def _upsert_relation_attributes(
        self,
        conn: sqlite3.Connection,
        subject_entity_id: str,
        fact: PerceptionFact,
        relation: ExtractedRelation,
        captured_at: str,
        confidence: float,
        metadata: dict[str, Any],
        stability_count: int,
        scene_phase: str,
    ) -> None:
        if relation.relation_type == "located_at" and relation.object_text:
            self._upsert_attribute(
                conn,
                subject_entity_id,
                ExtractedAttribute("located_at", relation.object_text, "relation:located_at"),
                captured_at,
                confidence,
                metadata,
                stability_count=stability_count,
                scene_phase=scene_phase,
            )

        if not relation.object_label:
            return

        target_id = self._entity_id_for_label(conn, relation.object_label)
        if not target_id:
            return

        subject_label = normalize_label(fact.label)
        subject_text = f"{fact.label} {fact.attributes}".lower()
        attributes: list[ExtractedAttribute] = []

        if relation.relation_type == "worn_by":
            if subject_label == "headphones":
                attributes.append(ExtractedAttribute("accessory.head", self._descriptive_value(fact), "relation:worn_by"))
            elif subject_label in {"eyeglasses", "glasses"} or "glasses" in subject_text:
                attributes.append(ExtractedAttribute("eyewear", self._descriptive_value(fact), "relation:worn_by"))
            elif any(word in subject_label for word in ("shirt", "jacket", "hoodie", "coat", "sweater")):
                attributes.append(ExtractedAttribute("clothing.upper", self._descriptive_value(fact), "relation:worn_by"))
            elif any(word in subject_label for word in ("pants", "trousers", "jeans", "shorts")):
                attributes.append(ExtractedAttribute("clothing.lower", self._descriptive_value(fact), "relation:worn_by"))
            elif any(word in subject_label for word in ("shoe", "shoes", "sneaker", "boot")):
                attributes.append(ExtractedAttribute("clothing.feet", self._descriptive_value(fact), "relation:worn_by"))
            elif any(word in subject_label for word in ("hat", "cap", "helmet")):
                attributes.append(ExtractedAttribute("clothing.head", self._descriptive_value(fact), "relation:worn_by"))
        elif relation.relation_type == "held_by":
            self._upsert_attribute(
                conn,
                subject_entity_id,
                ExtractedAttribute("carried_by", relation.object_label, "relation:held_by"),
                captured_at,
                confidence,
                metadata,
                stability_count=stability_count,
                scene_phase=scene_phase,
            )
            attributes.append(ExtractedAttribute("carried_object", self._descriptive_value(fact), "relation:held_by"))
        elif relation.relation_type == "near" and subject_label in {"eyeglasses", "glasses"}:
            attributes.append(ExtractedAttribute("eyewear", self._descriptive_value(fact), "relation:near"))

        for attribute in attributes:
            self._upsert_attribute(
                conn,
                target_id,
                attribute,
                captured_at,
                confidence,
                metadata,
                stability_count=stability_count,
                scene_phase=scene_phase,
            )

    def _spatial_words_from_metadata(self, metadata: dict[str, Any]) -> list[dict[str, Any]]:
        if not self._accepts_spatial_words(metadata):
            return []
        raw_words = metadata.get("spatial_words")
        if not isinstance(raw_words, list):
            return []
        return [word for word in raw_words if isinstance(word, dict)]

    @staticmethod
    def _accepts_spatial_words(metadata: dict[str, Any]) -> bool:
        mode = str(metadata.get("capture_mode") or "")
        if mode in {"spatial_word_map", "offline_walk"}:
            return True
        source = str(metadata.get("source") or metadata.get("provider") or "")
        return source == "offline_walk" and isinstance(metadata.get("spatial_words"), list)

    @staticmethod
    def _spatial_pose_source(metadata: dict[str, Any]) -> str:
        if str(metadata.get("capture_mode") or "") == "offline_walk":
            return "offline_walk"
        if str(metadata.get("source") or metadata.get("provider") or "") == "offline_walk":
            return "offline_walk"
        return "spatial_word_map"

    @staticmethod
    def _trust_value(value: Any) -> str:
        trust = str(value or "trusted").strip().lower()
        return "rejected" if trust == "rejected" else "trusted"

    def _upsert_spatial_word_map(
        self,
        conn: sqlite3.Connection,
        metadata: dict[str, Any],
        spatial_words: list[dict[str, Any]],
        captured_at: str,
        confidence: float,
        object_entity_ids_by_label: dict[str, str],
    ) -> list[str]:
        if not self._accepts_spatial_words(metadata):
            return []

        attribute_ids: list[str] = []
        for word in spatial_words:
            trust = self._trust_value(word.get("trust") or metadata.get("trust"))
            if trust == "rejected":
                continue
            label = " ".join(str(word.get("label") or "").split())
            if not label:
                continue
            x = self._float_or_none(word.get("x"))
            y = self._float_or_none(word.get("y"))
            z = self._float_or_none(word.get("z"))
            if x is None or y is None or z is None:
                continue

            label_norm = normalize_label(label)
            if not label_norm:
                continue
            word_kind = str(word.get("kind") or "object")
            entity_id = object_entity_ids_by_label.get(label_norm)
            if entity_id and word_kind == "object":
                kind_row = conn.execute("SELECT kind FROM graph_entities WHERE id = ?", (entity_id,)).fetchone()
                if not kind_row or str(kind_row["kind"]) != "object":
                    entity_id = None
            if entity_id:
                self._touch_spatial_entity(conn, entity_id, label, label_norm, captured_at, confidence, metadata, increment=False)
            else:
                entity_id = self._upsert_spatial_entity(conn, label, label_norm, captured_at, confidence, metadata)
                object_entity_ids_by_label[label_norm] = entity_id

            pose = {
                "x": x,
                "y": y,
                "z": z,
                "w": self._float_or_none(word.get("w")) or self._float_or_none(word.get("width")) or 0,
                "h": self._float_or_none(word.get("h")) or self._float_or_none(word.get("height")) or 0,
                "support_plane": self._support_plane_value(word.get("support_plane")),
                "footprint": self._footprint_value(word.get("footprint")),
                "heightM": max(0, self._float_or_none(word.get("heightM")) or self._float_or_none(word.get("height_m")) or 0),
                "sightings": self._int_or_default(word.get("sightings"), self._int_or_default(word.get("strength"), 1)),
                "verified": self._bool_or_false(word.get("verified")),
                "relabeled_from": word.get("relabeled_from") if isinstance(word.get("relabeled_from"), list) else [],
                "position_spread": self._float_or_none(word.get("position_spread")) or 0,
                "position_confidence": str(word.get("position_confidence") or "low"),
                "depth_mode": str(word.get("depth_mode") or metadata.get("depth_mode") or ""),
                "source": self._spatial_pose_source(metadata),
                "trust": trust,
                "name_source": str(word.get("name_source") or metadata.get("name_source") or ""),
                "frame": "genesis",
                "last_seen": captured_at,
                "build": str(metadata.get("build") or ""),
            }
            attribute_ids.append(
                self._upsert_spatial_pose_attribute(
                    conn,
                    entity_id,
                    pose,
                    captured_at,
                    confidence,
                    metadata,
                )
            )
        return attribute_ids

    @staticmethod
    def _support_plane_value(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _footprint_value(value: Any) -> list[list[float]]:
        if not isinstance(value, list):
            return []
        footprint: list[list[float]] = []
        for point in value[:24]:
            if not isinstance(point, list) or len(point) < 2:
                continue
            try:
                x = float(point[0])
                z = float(point[1])
            except (TypeError, ValueError):
                continue
            if math.isfinite(x) and math.isfinite(z):
                footprint.append([x, z])
        return footprint

    @staticmethod
    def _bool_or_false(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        return False

    def _upsert_spatial_entity(
        self,
        conn: sqlite3.Connection,
        label: str,
        label_norm: str,
        captured_at: str,
        confidence: float,
        metadata: dict[str, Any],
    ) -> str:
        row = conn.execute(
            """
            SELECT id FROM graph_entities
            WHERE kind = ? AND label_norm = ?
            """,
            ("object", label_norm),
        ).fetchone()
        if row:
            entity_id = str(row["id"])
            self._touch_spatial_entity(conn, entity_id, label, label_norm, captured_at, confidence, metadata, increment=True)
            return entity_id

        entity_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO graph_entities (
                id, kind, label_norm, label, first_seen_at, last_seen_at, confidence,
                observation_count, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_id,
                "object",
                label_norm,
                self._preferred_label(label, label_norm),
                captured_at,
                captured_at,
                confidence,
                1,
                "current",
                json.dumps(metadata, sort_keys=True),
            ),
        )
        return entity_id

    def _touch_spatial_entity(
        self,
        conn: sqlite3.Connection,
        entity_id: str,
        label: str,
        label_norm: str,
        captured_at: str,
        confidence: float,
        metadata: dict[str, Any],
        increment: bool,
    ) -> None:
        count_expr = "observation_count + 1" if increment else "observation_count"
        # Renaming on touch upgrades placeholder labels ("text surface" ->
        # "keyboard"), but the entity id can come from the facts-path label
        # map while a DIFFERENT row already owns UNIQUE(kind, label_norm).
        # Rename only when the label is free (or already ours); otherwise
        # update liveness alone.
        owner = conn.execute(
            """
            SELECT id FROM graph_entities
            WHERE kind = (SELECT kind FROM graph_entities WHERE id = ?)
              AND label_norm = ? AND id != ?
            """,
            (entity_id, label_norm, entity_id),
        ).fetchone()
        if owner is None:
            conn.execute(
                f"""
                UPDATE graph_entities
                SET label_norm = ?, label = ?, last_seen_at = ?,
                    confidence = MAX(confidence, ?), observation_count = {count_expr},
                    status = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    label_norm,
                    self._preferred_label(label, label_norm),
                    captured_at,
                    confidence,
                    "current",
                    json.dumps(metadata, sort_keys=True),
                    entity_id,
                ),
            )
        else:
            conn.execute(
                f"""
                UPDATE graph_entities
                SET last_seen_at = ?,
                    confidence = MAX(confidence, ?), observation_count = {count_expr},
                    status = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    captured_at,
                    confidence,
                    "current",
                    json.dumps(metadata, sort_keys=True),
                    entity_id,
                ),
            )

    def _upsert_spatial_pose_attribute(
        self,
        conn: sqlite3.Connection,
        entity_id: str,
        pose: dict[str, Any],
        captured_at: str,
        confidence: float,
        metadata: dict[str, Any],
    ) -> str:
        value = json.dumps(pose, sort_keys=True, separators=(",", ":"))
        source = self._spatial_pose_source(metadata)
        row = conn.execute(
            """
            SELECT id, confidence, observation_count
            FROM graph_attributes
            WHERE entity_id = ? AND attribute_key = ?
            ORDER BY last_seen_at DESC LIMIT 1
            """,
            (entity_id, "spatial_pose"),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE graph_attributes
                SET attribute_value = ?, source = ?, last_seen_at = ?,
                    confidence = ?, observation_count = ?, status = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    value,
                    source,
                    captured_at,
                    max(float(row["confidence"]), confidence),
                    int(row["observation_count"]) + 1,
                    "current",
                    json.dumps(metadata, sort_keys=True),
                    row["id"],
                ),
            )
            return str(row["id"])

        attribute_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO graph_attributes (
                id, entity_id, attribute_key, attribute_value, source, first_seen_at,
                last_seen_at, confidence, observation_count, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attribute_id,
                entity_id,
                "spatial_pose",
                value,
                source,
                captured_at,
                captured_at,
                confidence,
                1,
                "current",
                json.dumps(metadata, sort_keys=True),
            ),
        )
        return attribute_id

    def _upsert_attribute(
        self,
        conn: sqlite3.Connection,
        entity_id: str,
        attribute: ExtractedAttribute,
        captured_at: str,
        confidence: float,
        metadata: dict[str, Any],
        stability_count: int,
        scene_phase: str,
    ) -> str:
        value = " ".join(attribute.value.split()).strip()
        if not value:
            raise ValueError("attribute value is required")

        if attribute.key in {"object_type", "entity_type"}:
            conn.execute(
                """
                UPDATE graph_attributes
                SET status = ?, last_seen_at = ?, metadata_json = ?
                WHERE entity_id = ? AND attribute_key = ? AND attribute_value != ? AND status != ?
                """,
                ("stale", captured_at, json.dumps(metadata, sort_keys=True), entity_id, attribute.key, value, "stale"),
            )

        row = conn.execute(
            """
            SELECT id, confidence, observation_count, status
            FROM graph_attributes
            WHERE entity_id = ? AND attribute_key = ? AND attribute_value = ?
            """,
            (entity_id, attribute.key, value),
        ).fetchone()
        if row:
            observations = int(row["observation_count"]) + 1
            effective_confidence = max(float(row["confidence"]), confidence)
            status = "current" if row["status"] == "current" else self._relation_status(
                effective_confidence, observations, stability_count, scene_phase
            )
            conn.execute(
                """
                UPDATE graph_attributes
                SET last_seen_at = ?, confidence = ?, observation_count = ?,
                    status = ?, source = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    captured_at,
                    effective_confidence,
                    observations,
                    status,
                    attribute.source,
                    json.dumps(metadata, sort_keys=True),
                    row["id"],
                ),
            )
            return str(row["id"])

        attribute_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO graph_attributes (
                id, entity_id, attribute_key, attribute_value, source, first_seen_at,
                last_seen_at, confidence, observation_count, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attribute_id,
                entity_id,
                attribute.key,
                value,
                attribute.source,
                captured_at,
                captured_at,
                confidence,
                1,
                self._relation_status(confidence, 1, stability_count, scene_phase),
                json.dumps(metadata, sort_keys=True),
            ),
        )
        return attribute_id

    def _entity_id_for_label(self, conn: sqlite3.Connection, label: str) -> str | None:
        label_norm = normalize_label(label)
        kind = label_kind(label)
        row = conn.execute(
            "SELECT id FROM graph_entities WHERE kind = ? AND label_norm = ?",
            (kind, label_norm),
        ).fetchone()
        return str(row["id"]) if row else None

    def _find_text_surface_entity(
        self,
        conn: sqlite3.Connection,
        fact: PerceptionFact,
        desired_label_norm: str,
    ) -> sqlite3.Row | None:
        visible_text = self._visible_text_for_fact(fact)
        if not visible_text:
            return None

        candidates = conn.execute(
            """
            SELECT e.id, e.label_norm, e.confidence, e.observation_count, e.status,
                   a.attribute_value AS visible_text
            FROM graph_entities e
            LEFT JOIN graph_attributes a
              ON a.entity_id = e.id
             AND a.attribute_key = 'text.visible'
            WHERE e.kind = 'text_surface'
            ORDER BY
                CASE e.status WHEN 'current' THEN 0 WHEN 'provisional' THEN 1 ELSE 2 END,
                e.last_seen_at DESC
            """
        ).fetchall()

        best_row: sqlite3.Row | None = None
        best_score = 0.0
        for row in candidates:
            candidate_text = str(row["visible_text"] or "")
            score = self._text_surface_match_score(
                desired_label_norm,
                str(row["label_norm"]),
                visible_text,
                candidate_text,
            )
            if score > best_score:
                best_row = row
                best_score = score

        return best_row if best_score >= 2.2 else None

    def _visible_text_for_fact(self, fact: PerceptionFact) -> str:
        return self.parser._clean_visible_text(
            self.parser._quoted_text(fact.raw_text) or fact.attributes
        )

    def _resolve_text_surface_label_norm(self, existing_label_norm: str, incoming_label_norm: str) -> str:
        specialized = {"display screen", "transit sign", "document"}
        if incoming_label_norm in specialized:
            return incoming_label_norm
        if existing_label_norm in specialized:
            return existing_label_norm
        return incoming_label_norm or existing_label_norm

    def _text_surface_match_score(
        self,
        desired_label_norm: str,
        existing_label_norm: str,
        visible_text: str,
        candidate_text: str,
    ) -> float:
        if not candidate_text:
            return 0.0

        score = 0.0
        if desired_label_norm == existing_label_norm:
            score += 1.4
        elif "text surface" in {desired_label_norm, existing_label_norm}:
            score += 0.9

        similarity = self._visible_text_similarity(visible_text, candidate_text)
        score += similarity * 3.0
        if similarity >= 0.88:
            score += 0.6
        return score

    def _visible_text_similarity(self, left: str, right: str) -> float:
        left_key = self._visible_text_key(left)
        right_key = self._visible_text_key(right)
        if not left_key or not right_key:
            return 0.0
        if left_key == right_key:
            return 1.0

        left_tokens = set(left_key.split())
        right_tokens = set(right_key.split())
        if not left_tokens or not right_tokens:
            return 0.0

        overlap = left_tokens & right_tokens
        union = left_tokens | right_tokens
        score = len(overlap) / len(union)
        if left_key in right_key or right_key in left_key:
            score = max(score, 0.9)
        return score

    def _visible_text_key(self, value: str) -> str:
        lowered = unicodedata.normalize("NFKD", value.lower())
        lowered = "".join(char for char in lowered if not unicodedata.combining(char))
        lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
        tokens = [
            token
            for token in lowered.split()
            if len(token) >= 3 and token not in {"the", "and", "for", "with", "from"}
        ]
        return " ".join(tokens)

    def _descriptive_value(self, fact: PerceptionFact) -> str:
        label = self._preferred_label(fact.label, self._normalized_label_for_fact(fact))
        attrs = fact.attributes.lower()
        color = self.parser._first_color(f"{fact.label} {fact.attributes}")
        compact = re.sub(r";.*$", "", fact.attributes).strip()
        label_words = label.lower().split()
        compact_words = compact.lower().split()
        if color and compact_words and label_words and compact_words[-1] == label_words[-1] and color not in compact.lower():
            return f"{color} {compact}".strip()
        if color and color not in label.lower():
            return f"{color} {label}".strip()
        generic_attributes = {
            "relation target",
            "visible object",
            "image-level visual classification",
            "provisional visual classification",
            "provisional visual classification while camera moving",
        }
        if attrs and attrs not in generic_attributes:
            if compact and compact.lower() not in label.lower() and len(compact) <= 60:
                return f"{compact} {label}".strip()
        return label

    def _entity_status(
        self,
        fact: PerceptionFact,
        observation_count: int,
        stability_count: int,
        scene_phase: str,
        confidence: float,
    ) -> str:
        if scene_phase == "moving" and fact.certainty != "likely":
            return "provisional"
        if fact.certainty == "likely" and confidence >= CURRENT_CONFIDENCE_THRESHOLD:
            return "current"
        if observation_count >= PROMOTE_OBSERVATION_COUNT and stability_count >= PROMOTE_STABILITY_COUNT:
            return "current"
        return "provisional"

    def _relation_status(
        self,
        confidence: float,
        observation_count: int,
        stability_count: int,
        scene_phase: str,
    ) -> str:
        if scene_phase == "moving" and confidence < CURRENT_CONFIDENCE_THRESHOLD:
            return "provisional"
        if confidence >= CURRENT_CONFIDENCE_THRESHOLD:
            return "current"
        if observation_count >= PROMOTE_OBSERVATION_COUNT and stability_count >= PROMOTE_STABILITY_COUNT:
            return "current"
        return "provisional"

    def _insert_observation(
        self,
        conn: sqlite3.Connection,
        captured_at: str,
        source_type: str,
        provider: str,
        confidence: float,
        stability_count: int,
        scene_phase: str,
        motion_score: float | None,
        evidence_text: str,
        metadata: dict[str, Any],
        entity_id: str | None = None,
        event_id: str | None = None,
        place_id: str | None = None,
    ) -> str:
        # Bug 2 fix: 60-second dedup window — prevent observation flood
        dedup_row = conn.execute(
            """
            SELECT id FROM graph_observations
            WHERE entity_id IS ? AND event_id IS ? AND place_id IS ?
              AND scene_phase = ? AND captured_at >= datetime('now', '-60 seconds')
            LIMIT 1
            """,
            (entity_id, event_id, place_id, scene_phase),
        ).fetchone()
        if dedup_row:
            # Duplicate within window — reuse existing observation ID (no schema update needed)
            return dedup_row["id"]

        observation_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO graph_observations (
                id, captured_at, source_type, provider, entity_id, event_id, place_id,
                confidence, stability_count, scene_phase, motion_score, evidence_cipher,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                captured_at,
                source_type,
                provider,
                entity_id,
                event_id,
                place_id,
                confidence,
                stability_count,
                scene_phase,
                motion_score,
                self.codec.encrypt(evidence_text),
                json.dumps(metadata, sort_keys=True),
            ),
        )
        return observation_id

    def _mark_inactive_entities_stale(
        self,
        conn: sqlite3.Connection,
        active_norms: set[str],
        captured_at: str,
        metadata: dict[str, Any],
    ) -> None:
        # Vision liveness applies ONLY to vision-derived entities. Imported
        # relationship memory (WhatsApp/iMessage/calendar contacts, marked by
        # relationship_source) is not "stale" because it left the camera
        # frame — staling it silently corroded contact recall (2026-06-11).
        rows = conn.execute(
            """SELECT id, label_norm, status FROM graph_entities
               WHERE status IN ('current', 'provisional')
                 AND id NOT IN (SELECT entity_id FROM graph_attributes
                                WHERE attribute_key='relationship_source')"""
        ).fetchall()
        for row in rows:
            if row["label_norm"] in active_norms:
                continue
            conn.execute(
                "UPDATE graph_entities SET status = ?, last_seen_at = ?, metadata_json = ? WHERE id = ?",
                ("stale", captured_at, json.dumps(metadata, sort_keys=True), row["id"]),
            )
            conn.execute(
                """
                UPDATE graph_relations
                SET status = ?, last_seen_at = ?, metadata_json = ?
                WHERE subject_entity_id = ? OR object_entity_id = ?
                """,
                ("stale", captured_at, json.dumps(metadata, sort_keys=True), row["id"], row["id"]),
            )
            conn.execute(
                """
                UPDATE graph_attributes
                SET status = ?, last_seen_at = ?, metadata_json = ?
                WHERE entity_id = ?
                """,
                ("stale", captured_at, json.dumps(metadata, sort_keys=True), row["id"]),
            )

    def _relation_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "relation_type": row["relation_type"],
            "subject": row["subject"],
            "object": row["object_label"] or row["object_text"] or row["place"],
            "place": row["place"],
            "last_seen_at": row["last_seen_at"],
            "confidence": row["confidence"],
            "observation_count": row["observation_count"],
            "status": row["status"],
        }

    def _preferred_label(self, label: str, label_norm: str) -> str:
        if label_norm == "visible person":
            return "visible person"
        if label_norm == "visible people":
            return "visible people"
        if label_norm == "background person":
            return "background person"
        if label_norm == "transit sign":
            return "transit sign"
        if label_norm == "display screen":
            return "display screen"
        if label_norm == "document":
            return "document"
        if label_norm == "text surface":
            return "text surface"
        if label_norm == "headphones":
            return "headphones"
        if label_norm == "shirt":
            return "shirt"
        return label.strip()

    def _normalized_label_for_fact(self, fact: PerceptionFact) -> str:
        label_norm = normalize_label(fact.label)
        if label_kind(fact.label) != "text_surface":
            return label_norm

        visible_text = self.parser._clean_visible_text(
            self.parser._quoted_text(fact.raw_text) or fact.attributes
        )
        return infer_text_surface_label(visible_text) or label_norm

    def _canonical_slots(
        self,
        slots: dict[str, list[dict[str, Any]]],
        slot_order: list[str],
    ) -> dict[str, dict[str, Any]]:
        ordered_keys = [key for key in slot_order if key in slots]
        ordered_keys.extend(key for key in slots if key not in ordered_keys)
        return {
            key: self._best_text_visible_slot(values) if key == "text.visible" else self._best_slot_value(values)
            for key in ordered_keys
            if (values := slots.get(key))
        }

    def _best_slot_value(self, values: list[dict[str, Any]]) -> dict[str, Any]:
        status_rank = {"current": 3, "provisional": 2, "stale": 1}

        def rank(value: dict[str, Any]) -> tuple[int, int, float, str]:
            return (
                status_rank.get(str(value.get("status")), 0),
                int(value.get("observation_count") or 0),
                float(value.get("confidence") or 0),
                str(value.get("last_seen_at") or ""),
            )

        return max(values, key=rank)

    def _best_text_visible_slot(self, values: list[dict[str, Any]]) -> dict[str, Any]:
        grouped: dict[str, dict[str, Any]] = {}
        order = 0
        for value in values:
            for piece in str(value.get("value") or "").split(" / "):
                order += 1
                cleaned = piece.strip()
                if not cleaned:
                    continue
                key = self._ocr_consensus_key(cleaned)
                if len(key) < 10 and not self._is_known_visible_text(cleaned):
                    continue
                group = grouped.setdefault(
                    key,
                    {
                        "best_text": cleaned,
                        "count": 0,
                        "confidence": 0.0,
                        "status": "stale",
                        "last_seen_at": "",
                        "first_order": order,
                    },
                )
                group["count"] = int(group["count"]) + max(1, int(value.get("observation_count") or 1))
                group["confidence"] = max(float(group["confidence"]), float(value.get("confidence") or 0))
                group["status"] = self._stronger_status(str(group["status"]), str(value.get("status") or "stale"))
                group["last_seen_at"] = max(str(group["last_seen_at"]), str(value.get("last_seen_at") or ""))
                if self._ocr_text_quality(cleaned) > self._ocr_text_quality(str(group["best_text"])):
                    group["best_text"] = cleaned

        if not grouped:
            return self._best_slot_value(values)

        stable_groups = [
            group for group in grouped.values()
            if int(group["count"]) >= 2 or self._is_known_visible_text(str(group["best_text"]))
        ]
        if not stable_groups:
            stable_groups = sorted(
                grouped.values(),
                key=lambda group: (
                    int(group["count"]),
                    float(group["confidence"]),
                    self._ocr_text_quality(str(group["best_text"])),
                ),
                reverse=True,
            )[:3]

        selected = sorted(
            stable_groups,
            key=lambda group: int(group["first_order"]),
        )[:8]
        selected_text = " / ".join(str(group["best_text"]) for group in selected)
        best = self._best_slot_value(values)
        return {
            **best,
            "value": selected_text,
            "observation_count": max(int(group["count"]) for group in selected),
            "confidence": max(float(group["confidence"]) for group in selected),
            "status": "current" if any(group["status"] == "current" for group in selected) else "provisional",
            "source": "ocr_consensus",
        }

    def _stronger_status(self, first: str, second: str) -> str:
        rank = {"current": 3, "provisional": 2, "stale": 1}
        return first if rank.get(first, 0) >= rank.get(second, 0) else second

    def _ocr_consensus_key(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value.lower())
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        normalized = re.sub(r"[^a-z0-9äöüß]+", " ", normalized)
        tokens = normalized.split()
        return " ".join(tokens[:10])

    def _ocr_text_quality(self, value: str) -> int:
        letters = sum(1 for char in value if char.isalpha())
        penalties = value.count("...") * 20 + len(re.findall(r"\b[a-zA-Z]{1,2}\b", value))
        return max(0, letters - penalties)

    def _is_known_visible_text(self, value: str) -> bool:
        normalized = value.lower()
        return any(
            fragment in normalized
            for fragment in (
                "garching-forschungszentrum",
                "max-planck-campus",
                "walther-meißner",
                "lichtenbergstr",
                "anna-boyksen",
                "isarstr",
                "boltzmannstr",
                "verhalten bei betriebsstörungen",
                "bus",
                "p+r",
            )
        )

    def _profile_slot_order(self, kind: str, label: str) -> list[str]:
        label_norm = normalize_label(label)
        if kind == "person":
            return [
                "entity_type",
                "face.visible",
                "body.visible",
                "age_visible",
                "age.approx",
                "stature",
                "build",
                "hair.color",
                "hair.length",
                "hair.style",
                "eyes.visible",
                "eyewear",
                "facial_hair",
                "mark.visible",
                "clothing.head",
                "clothing.upper",
                "clothing.lower",
                "clothing.feet",
                "accessory.head",
                "handedness",
                "gait",
                "carried_object",
            ]
        if any(word in label_norm for word in ("bag", "backpack", "tote", "pouch")):
            return [
                "object_type",
                "color",
                "size",
                "material",
                "closure",
                "strap",
                "pocket",
                "pattern",
                "wear",
                "carried_by",
                "located_at",
            ]
        if kind == "text_surface":
            return [
                "object_type",
                "text.visible",
                "located_at",
            ]
        return [
            "object_type",
            "color",
            "material",
            "wear",
            "located_at",
        ]

    def _float_or_none(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _int_or_default(self, value: Any, default: int) -> int:
        if value is None or value == "":
            return default
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default
