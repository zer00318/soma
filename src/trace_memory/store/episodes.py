"""Episode segmentation — the memory you can SEE (P30 Stage A).

Sleep-time organ: reads raw capture (derived=0), authors derived `episode`
nodes under builder="episodes" (reconsiderable via reconsider_derived — the
never-delete law protects raw capture, not this builder's own output).

Honest gaps are first-class: a stretch of no capture between two episodes is
itself an episode row (kind="gap"), so the timeline can never paper over
blindness.

Thresholds are MEASURED, not spec'd (real store, 3736 raw obs, 10 capture
days, 2026-07-05): within-capture gaps are <60s in 3014/3104 cases; all 61
gaps >=5min were true session boundaries; the 29 gaps in the 1-5min band are
ambiguous — split only when corroborated by a place change. Re-measure when
multi-hour natural carries exist (today's data is dev-session-shaped).

Members are not per-node linked (an episode can span thousands of rows);
consumers resolve members by time_range window over raw nodes — same
discipline the window-browse owner already uses.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

HARD_GAP_MS = 300_000  # >=5min: unconditional episode boundary (measured)
SOFT_GAP_MS = 60_000   # 1-5min: boundary only if the place moved (measured)

_GPS_RE = re.compile(r"GPS\s+(-?\d+\.\d+),\s*(-?\d+\.\d+)")

_BUILDER = "episodes"


def _place_key(node: Any) -> str | None:
    """Coarse location identity: ~110m GPS cell, else the street name."""
    if node.place:
        return str(node.place)
    hint = str(node.provenance.get("location_hint", "") or "")
    m = _GPS_RE.search(hint)
    if m:
        return f"{round(float(m.group(1)), 3)},{round(float(m.group(2)), 3)}"
    if "|" in hint:
        street = hint.split("|", 1)[1].split(",", 1)[0].strip()
        return street or None
    return None


def _street(node: Any) -> str | None:
    hint = str(node.provenance.get("location_hint", "") or "")
    if "|" in hint:
        street = hint.split("|", 1)[1].split(",", 1)[0].strip()
        return street or None
    return None


def _channel(node: Any) -> str:
    """Display channel from the record's own text prefix (OBJECT/TEXT/SPEECH/...)."""
    head = node.text.split("|", 1)[0].strip().lower()
    return head if head and len(head) <= 24 else "other"


def _time_of_day(t_ms: int) -> str:
    hour = datetime.fromtimestamp(t_ms / 1000).hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 23:
        return "evening"
    return "night"


def _human_duration(ms: int) -> str:
    minutes = int(ms // 60_000)
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h {minutes % 60:02d}m"


def _stable_id(start_ms: int, end_ms: int, kind: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"trace-episode:{kind}:{start_ms}:{end_ms}"))


@dataclass(frozen=True)
class EpisodeRunSummary:
    reconsidered: int
    episode_count: int
    gap_count: int
    day_count: int


class EpisodeBuilder:
    """Segments raw capture into episodes + honest gap episodes."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def build(self) -> EpisodeRunSummary:
        removed = self._store.reconsider_derived(_BUILDER)
        raw = [n for n in self._store.nodes() if not n.derived]
        raw.sort(key=lambda n: n.t_ms)
        segments = self._segment(raw)
        gap_count = 0
        for i, seg in enumerate(segments):
            self._write_episode(seg)
            if i + 1 < len(segments):
                gap_ms = segments[i + 1][0].t_ms - seg[-1].t_ms
                if gap_ms >= HARD_GAP_MS:
                    self._write_gap(seg[-1].t_ms, segments[i + 1][0].t_ms)
                    gap_count += 1
        days = {datetime.fromtimestamp(s[0].t_ms / 1000).date() for s in segments}
        return EpisodeRunSummary(
            reconsidered=removed,
            episode_count=len(segments),
            gap_count=gap_count,
            day_count=len(days),
        )

    def _segment(self, raw: list[Any]) -> list[list[Any]]:
        segments: list[list[Any]] = []
        current: list[Any] = []
        prev = None
        prev_place = None
        for node in raw:
            if prev is not None:
                gap = node.t_ms - prev.t_ms
                place = _place_key(node)
                hard = gap >= HARD_GAP_MS
                soft = (
                    SOFT_GAP_MS <= gap < HARD_GAP_MS
                    and place is not None
                    and prev_place is not None
                    and place != prev_place
                )
                if hard or soft:
                    segments.append(current)
                    current = []
            current.append(node)
            prev = node
            place_now = _place_key(node)
            if place_now is not None:
                prev_place = place_now
        if current:
            segments.append(current)
        return segments

    def _write_episode(self, members: list[Any]) -> None:
        from trace_memory.store.containers import container_head

        start, end = members[0].t_ms, members[-1].t_ms
        channels = Counter(_channel(n) for n in members)
        streets = Counter(s for n in members if (s := _street(n)))
        place = streets.most_common(1)[0][0] if streets else None
        # P34: containers make the label read like LIFE, not telemetry. A
        # digital episode is named by its dominant site/app ("youtube.com,
        # evening"); physical episodes keep their place name.
        heads = Counter(container_head(n) for n in members)
        top_head, top_count = heads.most_common(1)[0] if heads else (None, 0)
        digital = top_head and not top_head.startswith(("unplaced", "unknown")) \
            and top_head != place and top_count >= len(members) * 0.5 \
            and any((getattr(n, "provenance", None) or {}).get("app") for n in members)
        label_head = top_head if digital else (place or "unknown place")
        label = f"{label_head}, {_time_of_day(start)}"
        chan_text = ",".join(k for k, _ in channels.most_common(4))
        span = datetime.fromtimestamp(start / 1000).strftime("%H:%M")
        span += "-" + datetime.fromtimestamp(end / 1000).strftime("%H:%M")
        self._store.write_observation(
            text=(
                f"EPISODE | {label} | {span} | {len(members)} observations"
                f" | channels: {chan_text}"
            ),
            t_ms=start,
            source="sleep_binder",
            time_range={"start_ms": start, "end_ms": end},
            provenance={"builder": _BUILDER, "authored_by": "gap_segmentation_v1"},
            metadata={
                "builder": _BUILDER,
                "kind": "episode",
                "label": label,
                "day": datetime.fromtimestamp(start / 1000).date().isoformat(),
                "observation_count": len(members),
                "channels": dict(channels),
                "place": place,
                "containers": dict(heads.most_common(3)),
            },
            node_type="episode",
            derived=True,
            node_id=_stable_id(start, end, "episode"),
        )

    def _write_gap(self, start_ms: int, end_ms: int) -> None:
        duration = _human_duration(end_ms - start_ms)
        self._store.write_observation(
            text=f"GAP | no capture | {duration}",
            t_ms=start_ms,
            source="sleep_binder",
            time_range={"start_ms": start_ms, "end_ms": end_ms},
            provenance={"builder": _BUILDER, "authored_by": "gap_segmentation_v1"},
            metadata={
                "builder": _BUILDER,
                "kind": "gap",
                "day": datetime.fromtimestamp(start_ms / 1000).date().isoformat(),
                "duration_ms": end_ms - start_ms,
            },
            node_type="episode",
            derived=True,
            node_id=_stable_id(start_ms, end_ms, "gap"),
        )
