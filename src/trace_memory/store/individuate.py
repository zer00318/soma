"""Semantic object individuation for the world-grounded binder.

The live capture path only writes ``scene_frustum`` spatial anchors, whose orientation
is the *camera* pose, not the object's position. That makes spatial overlap useless for
deciding "are these two observations the same physical thing" — every object in a frame
shares the camera's bearing, so anchor-based linking collapses the whole room into a few
giant blobs (measured: 696 observations -> components of 420/234/42 nodes), which the
binder's size guard then rejects, authoring **zero** memories.

This module individuates on what the helpers actually saw — the canonical *label* of each
observation (subject hint + head noun) plus lexical/embedding similarity — instead of on
camera bearing. The output is per-object (and per-affordance-group) clusters that the
authoring pass turns into cited, reconsiderable state memories.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

# Two same-label observations whose world coordinates are within this many metres are the SAME
# physical instance; beyond it, distinct instances (so 5 nutella jars at 5 coords -> 5 instances).
_INSTANCE_RADIUS_M = 0.25


def _node_xyz(node: Any) -> tuple[float, float, float] | None:
    anchor = getattr(node, "spatial_anchor", None)
    coords = getattr(anchor, "coordinates", None) if anchor is not None else None
    if coords:
        xyz = coords.get("xyz") or coords.get("center_xyz")
        if isinstance(xyz, (list, tuple)) and len(xyz) == 3:
            return (float(xyz[0]), float(xyz[1]), float(xyz[2]))
    meta = getattr(node, "metadata", {}) or {}
    xyz = meta.get("world_xyz")
    if isinstance(xyz, (list, tuple)) and len(xyz) == 3:
        return (float(xyz[0]), float(xyz[1]), float(xyz[2]))
    return None


def _node_track_id(node: Any) -> str | None:
    """The on-device object tracker's persistent per-object identity. This is the coordinate-free
    individuation anchor: two observations sharing a track_id are the SAME physical object (the
    tracker followed it across frames); different track_ids are different objects. On a non-LiDAR
    phone ARKit world coordinates are unavailable, so this temporal identity replaces xyz as the
    thing the binder fuses helper aspects on."""
    meta = getattr(node, "metadata", {}) or {}
    tid = meta.get("track_id")
    if tid in (None, ""):
        return None
    return str(tid)


def _helper_name(node: Any) -> str:
    """Resolve which helper produced a node. Live phone rows carry no coordinate_frame, so they
    can't set the canonical ``helper_type`` COLUMN (it trips validation) — the per-helper identity
    lives in ``metadata['helper']`` instead. Prefer the column, fall back to metadata (mirrors
    ``agent._helper_of``) so live captures are individuated, not silently dropped."""
    col = str(getattr(node, "helper_type", None) or "")
    if col:
        return col.lower()
    meta = getattr(node, "metadata", {}) or {}
    return str(meta.get("helper") or meta.get("helper_prompt") or "").lower()


def _split_by_instance(
    members: list[Any],
) -> list[tuple[list[Any], tuple[float, float, float] | None, str | None]]:
    """Split same-label members into per-INSTANCE groups. Primary anchor = the on-device
    ``track_id`` (temporal object identity); world coordinate is the FALLBACK when no track is
    present. Returns (members, centroid, anchor_key) per instance. Same label + same track = one
    physical object; different tracks = different objects (5 tracked jars -> 5 instances), with no
    coordinates required."""
    by_track: dict[str, list[Any]] = {}
    order: list[str] = []
    untracked: list[Any] = []
    for n in members:
        tid = _node_track_id(n)
        if tid is None:
            untracked.append(n)
            continue
        if tid not in by_track:
            by_track[tid] = []
            order.append(tid)
        by_track[tid].append(n)
    if by_track:
        groups: list[tuple[list[Any], tuple[float, float, float] | None, str | None]] = [
            (by_track[t], None, t) for t in order
        ]
        # Untracked frame-level reads (e.g. a whole-scene VLM caption) fold into the first track
        # group, mirroring how xyz-unpositioned members fold into the nearest positioned instance.
        if untracked:
            first_members, _, first_key = groups[0]
            groups[0] = (first_members + untracked, None, first_key)
        return groups
    # No track anchors anywhere -> fall back to the world-coordinate split.
    return [
        (mem, centroid, (str(tuple(round(v, 3) for v in centroid)) if centroid else None))
        for mem, centroid in _split_by_xyz(members)
    ]


def _split_by_xyz(members: list[Any]) -> list[tuple[list[Any], tuple[float, float, float] | None]]:
    """Greedily split same-label members into per-INSTANCE groups by world-coordinate proximity.
    Members without coordinates fold into the nearest positioned instance (or one unknown group)."""
    positioned = [(n, _node_xyz(n)) for n in members]
    groups: list[dict[str, Any]] = []
    for node, xyz in positioned:
        if xyz is None:
            continue
        placed = False
        for g in groups:
            if math.dist(xyz, g["centroid"]) < _INSTANCE_RADIUS_M:
                g["members"].append(node)
                g["xyzs"].append(xyz)
                g["centroid"] = tuple(sum(c) / len(c) for c in zip(*g["xyzs"]))
                placed = True
                break
        if not placed:
            groups.append({"members": [node], "xyzs": [xyz], "centroid": xyz})
    unpositioned = [n for n, xyz in positioned if xyz is None]
    if unpositioned:
        if groups:
            groups[0]["members"].extend(unpositioned)
        else:
            groups.append({"members": unpositioned, "centroid": None, "xyzs": []})
    return [(g["members"], g.get("centroid")) for g in groups]

# Qualifiers that describe an *instance's* pose/state/size but are not part of its identity.
# Stripping them collapses "Large Nutella jar" / "Second Nutella jar below" -> "nutella jar".
_QUALIFIERS = {
    "a", "an", "the", "one", "two", "three", "four", "five", "first", "second", "third",
    "fourth", "fifth", "another", "other", "next", "same", "large", "small", "big",
    "little", "tall", "short", "tiny", "huge", "partially", "fully", "used", "unused",
    "closed", "open", "opened", "empty", "full", "visible", "partial", "single", "double",
    "stacked", "back", "front", "left", "right", "top", "bottom", "upper", "lower", "row",
    "middle", "centre", "center", "near", "far", "side", "main", "extra", "additional",
    "approximately", "roughly", "about", "some", "several", "few", "many", "this", "that",
    "these", "those", "my", "his", "her", "its", "their",
}
# Where a free-text observation stops describing the object and starts describing context.
_CUT_MARKERS = re.compile(
    r"\b(below|above|beneath|underneath|stacked|on top|next to|beside|behind|"
    r"in front of|to the|leaning|resting|draped|lying|placed|sitting|located|"
    r"with the|same label|same |partially|appears|seems)\b",
    re.IGNORECASE,
)
_PUNCT_CUT = re.compile(r"[,;:(—\-]| - ")
_WORD = re.compile(r"[a-z0-9]+")
# Helper types that describe individual physical objects. Bare "vlm" is excluded on purpose:
# those are multi-object scene dumps ("## Physical Objects ...") that make junk header clusters;
# their per-object split ("vlm_object") is the clean seed. Screen-text sections are excluded
# separately (they are laptop UI content, not room objects).
PHYSICAL_HELPERS = {
    "vlm_object", "ocr", "spatial_relation", "relation_helper",
    "colour", "color", "texture", "material", "whisper", "audio", "speech",
    "detector",  # on-device YOLO tracker: carries the track_id anchor (COCO-class labels)
}
# Lightweight affordance lexicon: groups distinct entities that jointly answer an
# affordance/option question ("how can I drink water?" -> bottle + thermal + glass).
AFFORDANCE_GROUPS: dict[str, tuple[str, ...]] = {
    "drink water": ("bottle", "thermal", "thermos", "flask", "glass", "cup", "tumbler", "mug", "water"),
    "sit": ("chair", "stool", "sofa", "couch", "bench"),
    "write": ("pen", "pencil", "marker", "notebook", "diary", "notepad"),
}
# False friends that share a singularized token with a lexicon term but are unrelated
# (e.g. "glasses"/"eyeglasses" -> "glass", but eyewear is not a drinking vessel).
_AFFORDANCE_EXCLUDE = {"glasses", "eyeglasses", "eyewear", "spectacles", "sunglasses"}


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _strip_qualifiers(words: Iterable[str]) -> list[str]:
    return [w for w in words if w not in _QUALIFIERS]


def canonical_label(node: Any) -> str:
    """Derive a normalized identity label for an observation.

    Prefers an explicit subject/label hint; otherwise extracts the head noun phrase from
    the free text, cutting at the first contextual marker. Returns ``""`` when nothing
    usable is present (caller skips such nodes for entity authoring)."""
    meta = getattr(node, "metadata", {}) or {}
    raw = ""
    for key in ("subject_hint", "subject", "entity_label", "label", "canonical_label"):
        value = meta.get(key)
        if value and str(value).strip():
            raw = str(value)
            break
    if not raw:
        raw = getattr(node, "text", "") or ""

    # Cut at the first punctuation or contextual marker, then keep a short head phrase.
    cut = _PUNCT_CUT.split(raw, maxsplit=1)[0]
    marker = _CUT_MARKERS.search(cut)
    if marker:
        cut = cut[: marker.start()]
    words = _strip_qualifiers(_words(cut))
    # Drop pure colour words at the head ("brown glass jar" keeps glass/jar; identity not colour).
    label = " ".join(words[:4]).strip()
    return label


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("ses"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _content_words(label: str) -> set[str]:
    return {_singular(w) for w in _words(label) if len(w) > 2}


@dataclass
class ObjectCluster:
    """A candidate physical object (or affordance group) the binder will author about."""

    label: str
    kind: str  # "entity" | "group"
    member_ids: list[str] = field(default_factory=list)
    members: list[Any] = field(default_factory=list)
    affordance: str | None = None
    centroid: tuple[float, float, float] | None = None  # world coord of this physical instance
    anchor_key: str | None = None  # stable instance anchor: track_id (preferred) or world coord
    instance_index: int = 0       # 1-based index among instances sharing this label
    instance_count: int = 1       # how many distinct instances of this label were individuated

    @property
    def latest(self) -> Any:
        return max(self.members, key=lambda n: (n.t_ms, n.id))

    @property
    def earliest(self) -> Any:
        return min(self.members, key=lambda n: (n.t_ms, n.id))

    @property
    def places(self) -> list[str]:
        seen: list[str] = []
        for n in self.members:
            p = getattr(n, "place", None)
            if p and p not in seen:
                seen.append(p)
        return seen

    @property
    def helper_types(self) -> list[str]:
        return sorted({str(getattr(n, "helper_type", None) or "unknown") for n in self.members})


def _head_noun(label: str) -> str | None:
    words = [_singular(w) for w in _words(label) if len(w) > 2]
    return words[-1] if words else None


def _labels_merge(a: str, b: str) -> bool:
    """Two labels denote the same entity type when they share a (singularized) head noun
    AND share at least one content word.

    The head-noun gate is essential: without it a generic hub word ("nutella", "jar")
    transitively chains unrelated clusters into one mega-blob (measured: a 322-member
    "nutella" cluster). Requiring the same head noun keeps "large nutella jar" /
    "second nutella jar" / "jars" together (head=jar) and merges "blanket throw" /
    "grey bedsheet blanket" (head=blanket), while keeping the bare brand read "nutella"
    (head=nutella) as its own corroborating cluster. Pure string logic -> deterministic and
    robust to the stub embedder used in tests."""
    wa, wb = _content_words(a), _content_words(b)
    if not wa or not wb:
        return False
    head = _head_noun(a)
    if head != _head_noun(b):
        return False
    # Distinguish on the MODIFIERS, not the shared head noun: "nutella jar" and "pesto jar"
    # must NOT merge just because both end in "jar". Merge only when one is a qualifier-only
    # variant of the other (containment with a real modifier) or they share a modifier word.
    nonhead_a, nonhead_b = wa - {head}, wb - {head}
    if (wa <= wb or wb <= wa) and (nonhead_a if len(wa) <= len(wb) else nonhead_b):
        return True
    return bool(nonhead_a & nonhead_b)


_SIZE_TOKEN_RE = re.compile(
    r"^\d+(?:\.\d+)?(?:g|kg|mg|ml|cl|l|oz|lb|cm|mm|m|in|ft|gb|tb|mb|w|k)?$"
)
# When several helpers describe one tracked object, choose its identity label from an
# object-describing helper (vlm/colour/material), never from text/audio helpers whose "text"
# is content, not the object's name.
_LABEL_HELPER_PRIORITY = {
    "vlm_object": 0, "colour": 1, "color": 1, "material": 1, "texture": 1,
    "detector": 2, "spatial_relation": 2, "relation_helper": 2,
    "ocr": 5, "whisper": 6, "audio": 6, "speech": 6,
}
_NON_OBJECT_LABEL_WORDS = {"text", "surface", "ocr", "transcript", "speech", "audio"}


def _object_label_field(text: str) -> str:
    """The app emits ``OBJECT | <label> | <attributes>`` (and ``EVENT | ...``). The IDENTITY is the
    middle field, not the attribute tail — return it when present, else the whole text."""
    parts = [p.strip() for p in str(text).split("|")]
    if len(parts) >= 2 and parts[0].strip().upper() in ("OBJECT", "EVENT"):
        return parts[1]
    return text


def _identity_label(members: list[Any]) -> str:
    """One normalized identity label for a physical object seen by several helpers. Reads the
    OBJECT|label|attrs middle field from the highest-priority (object-describing) helper and strips
    size/qualifier tokens, so '500g nutella jar' and '825g nutella jar' share identity 'nutella jar'
    (=> counted as two instances of the SAME thing, not two different things)."""
    for n in sorted(members, key=lambda m: _LABEL_HELPER_PRIORITY.get(_helper_name(m), 3)):
        field = _object_label_field(getattr(n, "text", "") or "")
        words = [
            w for w in _strip_qualifiers(_words(field))
            if w != "object" and not _SIZE_TOKEN_RE.match(w)
        ]
        if words and not (_NON_OBJECT_LABEL_WORDS & set(words)):
            return " ".join(words[:4]).strip()
    return ""


def _track_first_clusters(tracked: list[Any], *, min_label_len: int) -> list[ObjectCluster]:
    """PRIMARY individuation for coordinate-free (live phone) data: fuse EVERY helper aspect of one
    tracked object into a single instance anchored on its track_id, then count instances that share
    a normalized identity label. This is what makes '5 nutella tracks -> 5 jars, each carrying its
    fused colour/OCR/VLM attributes' work without world coordinates."""
    by_track: dict[str, list[Any]] = defaultdict(list)
    order: list[str] = []
    for n in tracked:
        tid = _node_track_id(n)
        if tid not in by_track:
            order.append(tid)
        by_track[tid].append(n)
    instances: list[tuple[str, str, list[Any]]] = []
    for tid in order:
        members = by_track[tid]
        label = _identity_label(members)
        if len(label) >= min_label_len and _content_words(label):
            instances.append((tid, label, members))
    counts: dict[str, int] = defaultdict(int)
    for _tid, label, _m in instances:
        counts[label] += 1
    seen: dict[str, int] = defaultdict(int)
    clusters: list[ObjectCluster] = []
    for tid, label, members in instances:
        seen[label] += 1
        clusters.append(ObjectCluster(
            label=label, kind="entity",
            member_ids=[n.id for n in members], members=members,
            centroid=None, anchor_key=tid,
            instance_index=seen[label], instance_count=counts[label],
        ))
    return clusters


def individuate(nodes: Iterable[Any], *, min_label_len: int = 3) -> list[ObjectCluster]:
    """Cluster observations into per-object entity clusters by canonical label, then add
    affordance groups. Camera-pose anchors are intentionally ignored here."""
    physical = [
        n for n in nodes
        if _helper_name(n) in PHYSICAL_HELPERS
        and str((getattr(n, "metadata", {}) or {}).get("section_kind") or "") != "screen_text"
    ]
    # Track-anchored nodes are individuated TRACK-FIRST (all helper aspects of one object fuse into
    # one instance). Only nodes without a track fall back to label-first + world-coordinate split.
    tracked = [n for n in physical if _node_track_id(n) is not None]
    untracked = [n for n in physical if _node_track_id(n) is None]

    clusters: list[ObjectCluster] = _track_first_clusters(tracked, min_label_len=min_label_len)

    labelled: list[tuple[str, Any]] = []
    for n in untracked:
        label = canonical_label(n)
        if len(label) >= min_label_len and _content_words(label):
            labelled.append((label, n))

    # Union-find over distinct labels using the merge rule.
    distinct = sorted({lab for lab, _ in labelled})
    parent = {lab: lab for lab in distinct}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    for i, la in enumerate(distinct):
        for lb in distinct[i + 1:]:
            if _labels_merge(la, lb):
                union(la, lb)

    grouped: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    for lab, n in labelled:
        grouped[find(lab)].append((lab, n))

    for root, items in grouped.items():
        # Canonical label = most common (shortest on tie) member label in the cluster.
        counts: dict[str, int] = defaultdict(int)
        for lab, _ in items:
            counts[lab] += 1
        best_label = sorted(counts.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0][0]
        members = [n for _, n in items]
        # Split this label group into distinct PHYSICAL INSTANCES by object identity: the on-device
        # track_id if present (coordinate-free), else world coordinate. The count of a label = the
        # number of these instances (the brain never guesses it).
        instances = _split_by_instance(members)
        for idx, (inst_members, centroid, anchor_key) in enumerate(instances, start=1):
            clusters.append(
                ObjectCluster(
                    label=best_label,
                    kind="entity",
                    member_ids=[n.id for n in inst_members],
                    members=inst_members,
                    centroid=centroid,
                    anchor_key=anchor_key,
                    instance_index=idx,
                    instance_count=len(instances),
                )
            )

    clusters.sort(key=lambda c: (-len(c.members), c.label, c.instance_index))
    clusters.extend(_affordance_groups(clusters))
    return clusters


def _affordance_groups(entity_clusters: list[ObjectCluster]) -> list[ObjectCluster]:
    """Build cross-entity groups that jointly answer an affordance question. Honest by
    construction: a group only ever aggregates entities that were actually observed."""
    groups: list[ObjectCluster] = []
    for affordance, lexicon in AFFORDANCE_GROUPS.items():
        matched: list[Any] = []
        member_ids: list[str] = []
        for cluster in entity_clusters:
            raw_words = set(_words(cluster.label))
            if raw_words & _AFFORDANCE_EXCLUDE:
                continue
            cl_words = _content_words(cluster.label)
            if cl_words & set(lexicon):
                matched.extend(cluster.members)
                member_ids.extend(cluster.member_ids)
        # Only worth a group memory if >=2 distinct entity options were seen.
        distinct_labels = {canonical_label(m) for m in matched}
        if len(distinct_labels) >= 2:
            groups.append(
                ObjectCluster(
                    label=f"ways to {affordance}",
                    kind="group",
                    member_ids=member_ids,
                    members=matched,
                    affordance=affordance,
                )
            )
    return groups
