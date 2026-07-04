from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_SPATIAL_ANCHOR_KINDS = {
    "scene_frustum",
    "world_point",
    "world_region",
    "projected_crop",
    "audio_origin",
}


def _clean_text(value: str, *, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty")
    return cleaned


def _normalize_vector3(value: Any, *, field_name: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{field_name} must be a 3-item list/tuple")
    return tuple(float(item) for item in value)


@dataclass(frozen=True)
class CoordinateFrame:
    session_id: str
    origin_id: str
    frame_type: str = "session_local"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _clean_text(self.session_id, field_name="session_id"))
        object.__setattr__(self, "origin_id", _clean_text(self.origin_id, field_name="origin_id"))
        object.__setattr__(self, "frame_type", _clean_text(self.frame_type, field_name="frame_type"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "origin_id": self.origin_id,
            "frame_type": self.frame_type,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_value(cls, value: "CoordinateFrame | dict[str, Any]") -> "CoordinateFrame":
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise ValueError("coordinate_frame must be a dict")
        return cls(
            session_id=str(value.get("session_id") or ""),
            origin_id=str(value.get("origin_id") or ""),
            frame_type=str(value.get("frame_type") or "session_local"),
            metadata=dict(value.get("metadata") or {}),
        )


@dataclass(frozen=True)
class TimeRange:
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms < 0:
            raise ValueError("time range must not be negative")
        if self.end_ms < self.start_ms:
            raise ValueError("time range end must be >= start")

    def to_dict(self) -> dict[str, Any]:
        return {"start_ms": int(self.start_ms), "end_ms": int(self.end_ms)}

    @classmethod
    def from_value(cls, value: "TimeRange | dict[str, Any] | None", *, default_t_ms: int) -> "TimeRange":
        if value is None:
            return cls(start_ms=default_t_ms, end_ms=default_t_ms)
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise ValueError("time_range must be a dict")
        start_ms = int(value.get("start_ms", default_t_ms))
        end_ms = int(value.get("end_ms", start_ms))
        return cls(start_ms=start_ms, end_ms=end_ms)


@dataclass(frozen=True)
class SpatialAnchor:
    kind: str
    coordinates: dict[str, Any] = field(default_factory=dict)
    orientation: dict[str, Any] = field(default_factory=dict)
    bounds: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _clean_text(self.kind, field_name="spatial_anchor.kind"))
        if self.kind not in _SPATIAL_ANCHOR_KINDS:
            raise ValueError(f"unsupported spatial anchor kind: {self.kind}")
        self._validate_kind_payload()

    def _validate_kind_payload(self) -> None:
        coords = self.coordinates
        bounds = self.bounds
        if self.kind in {"world_point", "audio_origin"}:
            _normalize_vector3(coords.get("xyz"), field_name="spatial_anchor.coordinates.xyz")
        elif self.kind == "world_region":
            _normalize_vector3(coords.get("center_xyz"), field_name="spatial_anchor.coordinates.center_xyz")
            _normalize_vector3(bounds.get("size_xyz"), field_name="spatial_anchor.bounds.size_xyz")
        elif self.kind == "projected_crop":
            bbox = bounds.get("bbox_norm")
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                raise ValueError("projected_crop requires bounds.bbox_norm")
            [float(item) for item in bbox]
        elif self.kind == "scene_frustum":
            if not self.orientation:
                raise ValueError("scene_frustum requires orientation data")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "coordinates": dict(self.coordinates),
            "orientation": dict(self.orientation),
            "bounds": dict(self.bounds),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_value(cls, value: "SpatialAnchor | dict[str, Any]") -> "SpatialAnchor":
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise ValueError("spatial_anchor must be a dict")
        return cls(
            kind=str(value.get("kind") or ""),
            coordinates=dict(value.get("coordinates") or {}),
            orientation=dict(value.get("orientation") or {}),
            bounds=dict(value.get("bounds") or {}),
            metadata=dict(value.get("metadata") or {}),
        )


@dataclass(frozen=True)
class MemoryNode:
    id: str
    t_ms: int
    node_type: str
    source: str
    text: str
    provenance: dict[str, Any]
    helper_type: str | None = None
    coordinate_frame: CoordinateFrame | None = None
    time_range: TimeRange | None = None
    spatial_anchor: SpatialAnchor | None = None
    source_support: dict[str, Any] = field(default_factory=dict)
    place: str | None = None
    pose: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    derived: bool = False
    immutable_raw: bool = False
    embedding: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("node id must not be empty")
        if not self.node_type.strip():
            raise ValueError("node_type must not be empty")
        if not self.source.strip():
            raise ValueError("source must not be empty")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        if self.t_ms < 0:
            raise ValueError("t_ms must not be negative")
        if self.helper_type is not None and not self.helper_type.strip():
            raise ValueError("helper_type must not be empty when provided")

        normalized_time = TimeRange.from_value(self.time_range, default_t_ms=self.t_ms)
        object.__setattr__(self, "time_range", normalized_time)

        if self.coordinate_frame is not None:
            object.__setattr__(
                self,
                "coordinate_frame",
                CoordinateFrame.from_value(self.coordinate_frame),
            )
        if self.spatial_anchor is not None:
            object.__setattr__(
                self,
                "spatial_anchor",
                SpatialAnchor.from_value(self.spatial_anchor),
            )

        is_canonical = self.helper_type is not None or self.coordinate_frame is not None or self.spatial_anchor is not None
        if is_canonical:
            if self.coordinate_frame is None:
                raise ValueError("canonical observation requires coordinate_frame")
            if self.spatial_anchor is None:
                raise ValueError("canonical observation requires spatial_anchor")
            if self.time_range is None:
                raise ValueError("canonical observation requires time_range")


@dataclass(frozen=True)
class AnchorRecord:
    """P10: a place-anchor's life across sessions. Coordinates pin the world; this row is
    the world's memory of a single pinned spot — when it was first pinned, when last seen,
    how many distinct sessions have re-localized against it, and the best fidelity it ever
    earned. Movable things pin to identities instead (P11 fingerprints)."""

    anchor_id: str
    grade: str
    room: str | None
    first_session: str | None
    last_session: str | None
    first_seen_ms: int
    last_seen_ms: int
    session_count: int
    sightings: int
    pose: dict[str, Any] = field(default_factory=dict)

    @property
    def relocalized(self) -> bool:
        """True once this anchor has been re-entered in more than one session — the signal
        that the world map, not just a per-session track, is carrying its identity."""
        return self.session_count > 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "grade": self.grade,
            "room": self.room,
            "first_session": self.first_session,
            "last_session": self.last_session,
            "first_seen_ms": int(self.first_seen_ms),
            "last_seen_ms": int(self.last_seen_ms),
            "session_count": int(self.session_count),
            "sightings": int(self.sightings),
            "relocalized": self.relocalized,
            "pose": dict(self.pose),
        }


@dataclass(frozen=True)
class LinkRecord:
    id: str
    from_id: str
    to_id: str
    link_type: str
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("link id must not be empty")
        if not self.from_id.strip() or not self.to_id.strip():
            raise ValueError("link endpoints must not be empty")
        if not self.link_type.strip():
            raise ValueError("link_type must not be empty")


@dataclass(frozen=True)
class SearchHit:
    node: MemoryNode
    score: float


@dataclass(frozen=True)
class SearchSlice:
    query: str
    hits: tuple[SearchHit, ...]
    links: tuple[LinkRecord, ...]
    retrieval_mode: str = "semantic"
    degraded: bool = False


@dataclass(frozen=True)
class NeighborRecord:
    edge: LinkRecord
    node: MemoryNode
    direction: str


StoredObservation = MemoryNode
GraphLink = LinkRecord


@dataclass(frozen=True)
class AbstractionRecord:
    node: MemoryNode
