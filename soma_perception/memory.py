from __future__ import annotations

from soma_perception.models import MemoryEvent, TrackState, utc_now_iso


class MemoryEmitter:
    def __init__(self) -> None:
        self._last_track_signatures: dict[int, str] = {}

    def events_from_tracks(self, tracks: list[TrackState]) -> list[MemoryEvent]:
        events: list[MemoryEvent] = []
        for track in tracks:
            summary = self._summary_for_track(track)
            if not summary:
                continue

            signature = self._signature_for_track(track)
            previous = self._last_track_signatures.get(track.track_id)
            if previous == signature:
                continue

            self._last_track_signatures[track.track_id] = signature
            events.append(
                MemoryEvent(
                    event_type="OBSERVE",
                    timestamp_utc=utc_now_iso(),
                    summary_text=summary,
                    confidence=track.confidence,
                    category="visual_observation",
                    data={
                        "track_id": track.track_id,
                        "label": track.label,
                        "color": track.color,
                        "seen_count": track.seen_count,
                    },
                )
            )
        return events

    def _summary_for_track(self, track: TrackState) -> str | None:
        if track.seen_count < 3:
            return None

        position = track.frame_position or "visible frame"
        dominance = self._dominance(track.area_ratio)
        relation = f"{position}; {dominance}; detector stream"

        if track.label == "person":
            color_hint = "" if track.color == "unknown" else f"; mostly {track.color} upper-body clothing"
            return f"OBJECT | visible person | detector-tracked person{color_hint} | {relation} | likely"

        if track.color == "unknown":
            return f"OBJECT | {track.label} | detector-tracked object | {relation} | likely"

        return f"OBJECT | {track.label} | {track.color} detector-tracked object | {relation} | likely"

    def _signature_for_track(self, track: TrackState) -> str:
        return "|".join(
            [
                track.label,
                track.color,
                track.frame_position or "visible frame",
                self._dominance(track.area_ratio),
            ]
        )

    def _dominance(self, area_ratio: float) -> str:
        if area_ratio >= 0.35:
            return "dominant foreground object"
        if area_ratio >= 0.12:
            return "large visible object"
        if area_ratio >= 0.03:
            return "medium visible object"
        return "small visible object"
