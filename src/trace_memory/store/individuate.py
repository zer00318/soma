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

# Genesis-frame split distances for per-track world coordinates (P10 `track_world`, raycast
# through each track's own box centre on-device), applied to per-track MEDIANS of tracks that
# were never co-visible. Cross-time absolute positions carry per-pose raycast noise (measured
# 2026-07-04 walk 2: one static jar's tracks put their MEDIANS up to 0.147 m apart across
# viewing angles), so the never-covisible split is two-tiered like the grid-cell heuristic:
# LIBERAL splits above the measured same-object median noise (0.15), STRICT only at double
# it (0.30). Two never-covisible tracks 0.15-0.30 m apart therefore widen the honest count
# RANGE instead of minting a firm second object — a firm split must be WITNESSED
# (simultaneous stamps below), never inferred from mid-zone medians.
_WORLD_SPLIT_M = 0.30
_WORLD_SPLIT_LIBERAL_M = 0.15

# Metric co-visibility. The DUP direction is regime-proof (measured on choreographed walk 2
# AND the natural-motion burst): two simultaneous stamps ≤0.05 m apart share the bearing by
# construction — depth junk moves both along the same ray — so coincidence means one visual
# target, even when the absolute depth is wrong. The SPLIT direction is NOT depth-proof:
# under natural motion one jar's duplicate boxes raycast to different depths along nearly
# the same bearing (jar vs wall behind), pushing 3D distance past any threshold — a
# 3D-only simultaneous split mints phantom objects (measured: natural burst read 3 jars as
# [5,8]). A simultaneous split therefore requires BOTH bearing divergence (two directions =
# two silhouettes; dups measured 0.09-0.15 deg, distinct objects 7-46 deg) AND locally
# STABLE stamps on both sides (see _STAMP_STABLE_M) so scatter never testifies.
_COVIS_DUP_M = 0.05
_COVIS_SPLIT_M = 0.10
_COVIS_SPLIT_DEG = 3.0
# Strict (count-LOW) bearing split: must exceed any plausible duplicate-box separation on
# ONE close object. Measured: dup boxes on one jar reached ~8-18 deg at ~0.5 m; genuinely
# different jars 20-46 deg. 20 deg is the metric analog of M2's battle-tested
# non-adjacent-grid-cell strict rule (>1/3 of FOV).
_COVIS_SPLIT_STRICT_DEG = 20.0
# A stamp is STABLE when a neighbouring stamp of the SAME track agrees within this distance
# (stationary-viewing moment — people naturally pause on things they care about). Measured:
# stable-regime stamps agree to ≤0.10 m; sweeping-regime stamps scatter 0.2-1.3 m along the
# ray. Only stable stamps may testify for splits or median positions; scattered tracks
# assert nothing and leave the count an honest range.
_STAMP_STABLE_M = 0.10

# Grades whose poses share a stable genesis frame. "track" (Limited/relocalizing) coordinates
# may live in a shifted frame — measured on the jar walk: the one relocalizing-grade track's
# raycast landed ~0.7 m from where trusted frames put the same jars. Never split on those.
_TRUSTED_WORLD_GRADES = {"world", "session"}


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


# 2-char words are admitted (a "tv" is a real object the detector emits; len>2 made every tv
# invisible to the binder) — minus function-word junk that would create phantom merges.
_SHORT_JUNK = {"of", "on", "in", "at", "to", "an", "is", "it", "my", "me", "we", "up", "no",
               "by", "or", "as", "if", "so", "do", "am", "be", "he", "us", "go"}


def _content_words(label: str) -> set[str]:
    return {_singular(w) for w in _words(label) if len(w) > 1 and w not in _SHORT_JUNK}


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
    count_low: int | None = None  # conservative instance count (strict co-visibility reading);
                                  # None -> equals instance_count (no ambiguity)

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
    if len(parts) >= 2 and parts[0].strip().upper() in ("OBJECT", "EVENT", "TRACK"):
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


# ---- M2: cross-track re-ID (co-visibility + attribute identity) ---------------------------
#
# A track is NOT an instance. Real capture fragments one object into many tracks (measured:
# 1 keyboard -> 12 tracks), so counting tracks over-counts. Two tracks of the same label are
# DISTINCT physical objects only when the evidence says so:
#   - CO-VISIBILITY: near-simultaneous observations in different frame grid cells means two
#     objects were in view at once (same-cell simultaneity is a duplicate detector box);
#   - ATTRIBUTE IDENTITY: contradictory size tokens (500g vs 825g) or conflicting colour
#     families are different objects even when never co-visible.
# Everything else merges (pan-away-and-back re-acquisition). Adjacent-cell co-visibility is
# ambiguous (one object can straddle a cell boundary), so instances are resolved twice —
# liberal (any different cell splits) and strict (only non-adjacent cells split) — and the
# spread is authored as an honest count RANGE instead of a confident guess.

_GRID_RE = re.compile(r"\b(upper|middle|lower)-(left|center|right) of frame\b", re.IGNORECASE)
_GRID_ROW = {"upper": 0, "middle": 1, "lower": 2}
_GRID_COL = {"left": 0, "center": 1, "right": 2}
# Same-FRAME tolerance. A wider window (700ms tested) reads camera pans as
# co-visibility: two sightings 200ms apart in different cells split one mouse
# into two "resolved" objects on the live desk store. Only near-identical
# timestamps prove two objects were in view at once.
_COVIS_WINDOW_MS = 150


def _node_grid_cell(node: Any) -> tuple[int, int] | None:
    m = _GRID_RE.search(getattr(node, "text", "") or "")
    if not m:
        return None
    return (_GRID_ROW[m.group(1).lower()], _GRID_COL[m.group(2).lower()])


# Generic perceptual colour vocabulary + drift families shared with the count resolver.
from trace_memory.store.permanence import _COLOURS as _COLOUR_VOCAB  # noqa: E402
from trace_memory.store.permanence import _colours_conflict  # noqa: E402


# Identity sizes are WEIGHT/VOLUME only ('500g', '1kg', '330ml'). Geometric measures (m, cm,
# mm, in, ft) are viewpoint-dependent — the device writes '~0.9m from camera', and treating
# '9m' vs '3m' as identity split ONE mouse into two "resolved" objects on the live desk store.
_IDENTITY_SIZE_RE = re.compile(r"^\d+(?:\.\d+)?(?:g|kg|mg|ml|cl|l|oz|lb)$")


def _track_signature(members: list[Any]) -> tuple[set[str], set[str]]:
    """Identity attributes of one track, fused across its helper members: weight/volume size
    tokens ('500g', '1kg') and colour words. Used to keep genuinely different objects apart
    even when they were never co-visible."""
    sizes: set[str] = set()
    colours: set[str] = set()
    for n in members:
        for w in _words(getattr(n, "text", "") or ""):
            if _IDENTITY_SIZE_RE.match(w):
                sizes.add(w)
            elif w in _COLOUR_VOCAB:
                colours.add(w)
    return sizes, colours


from typing import TYPE_CHECKING  # noqa: E402

if TYPE_CHECKING:  # annotation-only alias (never evaluated at runtime on 3.9)
    _Ray = tuple[int, tuple[float, float, float], tuple[float, float, float] | None]


def _track_rays(members: list[Any]) -> list[_Ray]:
    """Timestamped trusted `track_world` stamps of one track (P10 per-track raycast), each
    with the camera origin when the row carries it — origin + point give the exact BEARING
    even when the raycast depth is junk. Trusted-grade gating because a relocalizing pose
    stamps coordinates in a shifted frame (see _TRUSTED_WORLD_GRADES). Time-sorted."""
    out: list[_Ray] = []
    for n in members:
        meta = getattr(n, "metadata", {}) or {}
        w = meta.get("track_world")
        if not (isinstance(w, (list, tuple)) and len(w) == 3):
            continue
        grade = str(meta.get("grade") or "").lower()
        if grade and grade not in _TRUSTED_WORLD_GRADES:
            continue
        cam = (meta.get("arkit_camera") or {}).get("position")
        origin = None
        if isinstance(cam, (list, tuple)) and len(cam) == 3:
            origin = (float(cam[0]), float(cam[1]), float(cam[2]))
        try:
            out.append((int(n.t_ms), (float(w[0]), float(w[1]), float(w[2])), origin))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda r: r[0])
    return out


def _stable_points(rays: list[_Ray]) -> list[tuple[float, float, float]]:
    """Stamps from stationary-viewing moments: a time-adjacent stamp of the SAME track agrees
    within _STAMP_STABLE_M. Sweeping-regime stamps scatter 0.2-1.3 m along the ray (measured)
    and never qualify — scatter must not testify."""
    pts = [p for _, p, _ in rays]
    out = []
    for i, p in enumerate(pts):
        if (i > 0 and math.dist(p, pts[i - 1]) <= _STAMP_STABLE_M) or (
            i + 1 < len(pts) and math.dist(p, pts[i + 1]) <= _STAMP_STABLE_M
        ):
            out.append(p)
    return out


def _median_and_sigma(
    pts: list[tuple[float, float, float]],
) -> tuple[tuple[float, float, float], float] | None:
    """Per-axis median + a self-noise estimate (half the max pairwise spread, floored) —
    the track's own demonstrated uncertainty, so split thresholds scale with measured noise
    instead of a scene-independent constant."""
    if not pts:
        return None
    mid = len(pts) // 2
    med = tuple(sorted(p[axis] for p in pts)[mid] for axis in range(3))
    sigma = max(
        (math.dist(a, b) for i, a in enumerate(pts) for b in pts[i + 1:]), default=0.0
    ) / 2.0
    return med, max(sigma, 0.02)  # type: ignore[return-value]


def _bearing_angle_deg(pa, oa, pb, ob) -> float | None:
    """Angle between two rays' bearings when both origins exist and coincide (same frame).
    Bearings are exact regardless of raycast depth — the depth-junk-proof quantity."""
    if oa is None or ob is None or math.dist(oa, ob) > 0.10:
        return None
    va = tuple(pa[i] - oa[i] for i in range(3))
    vb = tuple(pb[i] - ob[i] for i in range(3))
    na, nb = math.sqrt(sum(x * x for x in va)), math.sqrt(sum(x * x for x in vb))
    if na < 0.05 or nb < 0.05:
        return None
    cos = max(-1.0, min(1.0, sum(a * b for a, b in zip(va, vb)) / (na * nb)))
    return math.degrees(math.acos(cos))


def _covis_verdict(rays_a: list[_Ray], rays_b: list[_Ray], *, liberal: bool) -> bool | None:
    """Simultaneous-stamp verdict: coincident 3D = one target (depth-junk-proof — dup boxes
    share the bearing, junk moves both along the same ray); diverging BEARINGS = two
    silhouettes at one instant (liberal 3 deg, strict 20 deg — see constants). Rows without
    camera origins fall back to the original 3D split rule."""
    sim = [
        (pa, oa, pb, ob)
        for ta, pa, oa in rays_a
        for tb, pb, ob in rays_b
        if abs(ta - tb) <= _COVIS_WINDOW_MS
    ]
    if not sim:
        return None
    dists = [math.dist(pa, pb) for pa, _, pb, _ in sim]
    if max(dists) <= _COVIS_DUP_M:
        return False
    angles = [
        ang for pa, oa, pb, ob in sim
        if (ang := _bearing_angle_deg(pa, oa, pb, ob)) is not None
    ]
    if angles:
        if max(angles) >= (_COVIS_SPLIT_DEG if liberal else _COVIS_SPLIT_STRICT_DEG):
            return True
    elif min(dists) >= _COVIS_SPLIT_M:
        return True  # no bearings recorded -> original 3D rule
    return None


def _world_verdict(
    rays_a: list[_Ray],
    rays_b: list[_Ray],
    *,
    liberal: bool = False,
) -> bool | None:
    """P10/P12 fusion, honesty-asymmetric by design. LIBERAL (feeds the count's HIGH) splits
    eagerly — any plausible distinctness widens the range, which can only make the answer
    vaguer, never wrong. STRICT (feeds the LOW) splits only on regime-proof evidence:
    simultaneous bearings ≥20° apart (the metric analog of M2's non-adjacent-cell rule; a
    duplicate box on one close object measured up to ~18°, genuinely different objects
    20-46°) or stable-stamp medians separated beyond the tracks' own demonstrated noise.
    DUP (must-merge) is regime-proof in all data: simultaneous stamps that coincide share
    the bearing by construction. Rows without camera origins (pre-P10 stores, synthetic
    fixtures) fall back to the original 3D rules — those stores carry no sweep scatter."""
    if not rays_a or not rays_b:
        return None
    covis = _covis_verdict(rays_a, rays_b, liberal=liberal)
    if covis is not None:
        return covis
    has_bearings = any(o for _, _, o in rays_a) and any(o for _, _, o in rays_b)
    if not has_bearings:
        med_a = _median_and_sigma([p for _, p, _ in rays_a])
        med_b = _median_and_sigma([p for _, p, _ in rays_b])
        split_m = _WORLD_SPLIT_LIBERAL_M if liberal else _WORLD_SPLIT_M
        if med_a and med_b and math.dist(med_a[0], med_b[0]) >= split_m:
            return True
        return None
    if liberal:
        med_a = _median_and_sigma([p for _, p, _ in rays_a])
        med_b = _median_and_sigma([p for _, p, _ in rays_b])
        if med_a and med_b and math.dist(med_a[0], med_b[0]) >= _WORLD_SPLIT_LIBERAL_M:
            return True
        return None
    stab_a = _median_and_sigma(_stable_points(rays_a))
    stab_b = _median_and_sigma(_stable_points(rays_b))
    if stab_a and stab_b:
        (ma, sa), (mb, sb) = stab_a, stab_b
        if math.dist(ma, mb) >= max(_WORLD_SPLIT_M, 4.0 * (sa + sb)):
            return True
    return None


def _tracks_conflict(
    obs_a: list[tuple[int, tuple[int, int] | None]],
    obs_b: list[tuple[int, tuple[int, int] | None]],
    sig_a: tuple[set[str], set[str]],
    sig_b: tuple[set[str], set[str]],
    *,
    min_cell_dist: int,
    world_a: list[_Ray] | None = None,
    world_b: list[_Ray] | None = None,
) -> bool:
    sizes_a, cols_a = sig_a
    sizes_b, cols_b = sig_b
    if sizes_a and sizes_b and not (sizes_a & sizes_b):
        return True
    if _colours_conflict(cols_a, cols_b):
        return True
    world = _world_verdict(world_a or [], world_b or [], liberal=min_cell_dist == 1)
    if world is not None:
        return world
    for ta, ca in obs_a:
        if ca is None:
            continue
        for tb, cb in obs_b:
            if cb is None or abs(ta - tb) > _COVIS_WINDOW_MS:
                continue
            if max(abs(ca[0] - cb[0]), abs(ca[1] - cb[1])) >= min_cell_dist:
                return True
    return False


def _resolve_instances(
    track_members: list[list[Any]], *, min_cell_dist: int
) -> list[list[int]]:
    """Greedy conflict-respecting grouping of same-label tracks into physical instances.
    A track joins the first instance none of whose member tracks conflict with it."""
    obs = [
        sorted((int(n.t_ms), _node_grid_cell(n)) for n in members)
        for members in track_members
    ]
    sigs = [_track_signature(members) for members in track_members]
    worlds = [_track_rays(members) for members in track_members]
    order = sorted(range(len(track_members)), key=lambda i: obs[i][0][0] if obs[i] else 0)
    groups: list[list[int]] = []
    for i in order:
        placed = False
        for g in groups:
            if all(
                not _tracks_conflict(obs[i], obs[j], sigs[i], sigs[j],
                                     min_cell_dist=min_cell_dist,
                                     world_a=worlds[i], world_b=worlds[j])
                for j in g
            ):
                g.append(i)
                placed = True
                break
        if not placed:
            groups.append([i])
    return groups


def _union_groups(n: int, linked: Any) -> list[list[int]]:
    """Union-find over range(n) with `linked(i, j) -> bool`; returns groups in first-seen order."""
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if find(i) != find(j) and linked(i, j):
                parent[find(j)] = find(i)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _mustlink_components(
    per_track: list[tuple[str, str, str, list[Any]]],
) -> list[tuple[list[str], set[str], str, list[Any]]]:
    """P12 (Mac core), stage 1 — MUST-LINK union ACROSS labels. Two tracks whose world stamps
    coincide at the same instant are ONE object twice: a duplicate detector box or a COCO
    label flip (measured walk 2: cup-trk-16 = bottle-trk-17 at 0.000 m — per-label buckets
    could never see it). Union only when every simultaneous pair agrees (max ≤ dup); mixed
    evidence never links. No track_world anywhere → every track is its own component and the
    pre-P10 behaviour follows exactly. Returns (tids, det_labels, identity label, fused
    members) per physical component; identity from the largest track's label (deterministic;
    VLM-priority already applied per track)."""
    wobs = [_track_rays(members) for _, _, _, members in per_track]

    def linked(i: int, j: int) -> bool:
        if not wobs[i] or not wobs[j]:
            return False
        sim = [
            math.dist(wa, wb)
            for ta, wa, _oa in wobs[i]
            for tb, wb, _ob in wobs[j]
            if abs(ta - tb) <= _COVIS_WINDOW_MS
        ]
        return bool(sim) and max(sim) <= _COVIS_DUP_M

    components = []
    for idxs in _union_groups(len(per_track), linked):
        biggest = max(idxs, key=lambda k: len(per_track[k][3]))
        components.append((
            [per_track[k][0] for k in idxs],
            {per_track[k][1] for k in idxs},
            per_track[biggest][2],
            [n for k in idxs for n in per_track[k][3]],
        ))
    return components


def _counting_families(
    components: list[tuple[list[str], set[str], str, list[Any]]],
) -> list[list[int]]:
    """Stage 2 — counting FAMILIES: components compare for same-vs-distinct when they are the
    same KIND. Same identity label (the pre-P10 bucket rule) OR overlapping detector-label
    sets (a label-flipped component spans several COCO words; sharing any one means the
    detector called both by the same name at least once). Coordinate-free stores have
    singleton det-label sets and unchanged identity labels → families == today's buckets."""
    return _union_groups(
        len(components),
        lambda i, j: components[i][2] == components[j][2]
        or bool(components[i][1] & components[j][1]),
    )


def _track_first_clusters(tracked: list[Any], *, min_label_len: int) -> list[ObjectCluster]:
    """PRIMARY individuation for coordinate-free (live phone) data: fuse EVERY helper aspect of
    one tracked object per track, then RE-ID MERGE same-label tracks into physical instances via
    co-visibility + attribute identity (a track is a sighting, not an object). Counts carry an
    honest low/high: strict (non-adjacent-cell splits only) vs liberal (any different cell)."""
    # Track ids restart per app SESSION ('trk-5' today is a mouse, tomorrow a keyboard), so a
    # bare tid key fuses cross-label observations into one phantom track (measured: mouse
    # split 2 ways because its group had swallowed keyboard sightings). Key by (label, tid).
    by_track: dict[tuple[str, str], list[Any]] = defaultdict(list)
    order: list[tuple[str, str]] = []
    for n in tracked:
        tid = _node_track_id(n)
        meta = getattr(n, "metadata", {}) or {}
        det_label = str(meta.get("detector_label") or _object_label_field(
            getattr(n, "text", "") or "")).strip().lower()
        key = (det_label, tid)
        if key not in by_track:
            order.append(key)
        by_track[key].append(n)
    per_track: list[tuple[str, str, str, list[Any]]] = []  # (tid, det_label, identity, members)
    for key in order:
        members = by_track[key]
        label = _identity_label(members)
        if len(label) >= min_label_len and _content_words(label):
            per_track.append((key[1], key[0], label, members))

    components = _mustlink_components(per_track)

    clusters: list[ObjectCluster] = []
    for fam in _counting_families(components):
        comps = [components[k] for k in fam]
        member_lists = [m for _, _, _, m in comps]
        label = max(comps, key=lambda c: len(c[3]))[2]
        liberal = _resolve_instances(member_lists, min_cell_dist=1)
        strict = _resolve_instances(member_lists, min_cell_dist=2)
        low, high = min(len(strict), len(liberal)), len(liberal)
        for idx, group in enumerate(liberal, start=1):
            members = [n for c_idx in group for n in member_lists[c_idx]]
            anchor = "+".join(t for c_idx in group for t in comps[c_idx][0])
            clusters.append(ObjectCluster(
                label=label, kind="entity",
                member_ids=[n.id for n in members], members=members,
                centroid=None, anchor_key=anchor,
                instance_index=idx, instance_count=high,
                count_low=low,
            ))
    return clusters


def individuate(nodes: Iterable[Any], *, min_label_len: int = 2) -> list[ObjectCluster]:
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
