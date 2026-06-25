from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any


CRITICAL_RELATIONS = {
    "contains_text",
    "foreground_status",
    "located_at",
    "seen_in_frame_region",
}


@dataclass(frozen=True)
class GraphAuditResult:
    score: int
    grade: str
    issues: list[str]
    strengths: list[str]
    counts: dict[str, int]
    relation_types: dict[str, int]
    current_entities: list[dict[str, Any]]
    stale_entities: list[dict[str, Any]]
    recent_relations: list[dict[str, Any]]
    profile_quality: list[dict[str, Any]]


class GraphAuditor:
    def audit(
        self,
        graph: dict[str, Any],
        relations: list[dict[str, Any]] | None = None,
        profiles: list[dict[str, Any]] | None = None,
    ) -> GraphAuditResult:
        relations = relations if relations is not None else list(graph.get("recent_relations", []))
        profiles = profiles if profiles is not None else list(graph.get("profiles", []))
        entities = list(graph.get("recent_entities", []))
        active_entities = [entity for entity in entities if entity.get("status") in {"current", "provisional"}]
        current_entities = [entity for entity in entities if entity.get("status") == "current"]
        provisional_entities = [entity for entity in entities if entity.get("status") == "provisional"]
        stale_entities = [entity for entity in entities if entity.get("status") == "stale"]
        relation_counts = Counter(str(row.get("relation_type", "")) for row in relations if row.get("relation_type"))
        active_relations = [row for row in relations if row.get("status") in {"current", "provisional"}]
        current_relations = [row for row in relations if row.get("status") == "current"]
        profile_quality = self._profile_quality(profiles)
        text_profiles = [
            row for row in profile_quality
            if row["kind"] == "text_surface" and "text.visible" in row["present_slots"]
        ]

        issues: list[str] = []
        strengths: list[str] = []

        if not entities:
            issues.append("No graph entities yet. Run the native POV app with the hub active.")
        if graph.get("observations", 0) == 0:
            issues.append("No observations stored. Perception packets are not reaching the hub.")
        if graph.get("attributes", 0) == 0:
            issues.append("No entity attribute slots yet. Perception is not enriching object/person profiles.")
        else:
            strengths.append("Entity attribute slots are accumulating.")
        if graph.get("places", 0) == 0:
            issues.append("No place/GPS candidate attached yet.")
        else:
            strengths.append("Place/GPS candidates are present.")
        if not active_entities and entities:
            issues.append("All recent entities are stale; the camera may not be seeing reliable current objects.")
        if relation_counts.get("seen_in_frame_region", 0) == 0:
            issues.append("No frame-region relations. Detector spatial grounding is missing or not firing.")
        else:
            strengths.append("Detector spatial grounding is present.")
        if relation_counts.get("foreground_status", 0) == 0:
            issues.append("No foreground/dominance relations. Perception packets may lack size grounding.")
        else:
            strengths.append("Foreground/dominance relations are present.")
        if relation_counts.get("contains_text", 0) == 0 and text_profiles:
            strengths.append("Text/sign profiles retain readable OCR text from earlier frames.")
        elif relation_counts.get("contains_text", 0) == 0:
            issues.append("No OCR text relations. Point at a sign/board/package and hold steady.")
        else:
            strengths.append("OCR text is entering the graph.")
        if relation_counts.get("located_at", 0) == 0:
            issues.append("No located_at relations. Location hints are missing or unresolved.")
        else:
            strengths.append("Objects/events are linked to place.")
        if active_relations and not active_entities:
            issues.append("Active relations exist without active entities; stale cleanup may be inconsistent.")

        rich_profiles = [row for row in profile_quality if row["present_count"] >= 3]
        shallow_current_people = [
            row for row in profile_quality
            if row["kind"] == "person" and row["status"] == "current" and row["present_count"] < 3
        ]
        if rich_profiles:
            strengths.append("Profiles are accumulating multi-slot detail.")
        if text_profiles:
            strengths.append("Text/sign profiles retain readable OCR text.")
        if shallow_current_people:
            issues.append("Current person profile is still shallow; hold the subject steady to enrich visible slots.")

        score = 100
        score -= min(80, len(issues) * 12)
        score += min(10, len(strengths) * 2)
        score = max(0, min(100, score))
        grade = "excellent" if score >= 85 else "usable" if score >= 70 else "weak" if score >= 45 else "not-ready"

        counts = {
            "entities": int(graph.get("entities", 0)),
            "events": int(graph.get("events", 0)),
            "relations": int(graph.get("relations", 0)),
            "attributes": int(graph.get("attributes", 0)),
            "observations": int(graph.get("observations", 0)),
            "places": int(graph.get("places", 0)),
            "active_entities": len(active_entities),
            "current_entities": len(current_entities),
            "provisional_entities": len(provisional_entities),
            "stale_entities": len(stale_entities),
            "active_relations": len(active_relations),
            "current_relations": len(current_relations),
        }
        return GraphAuditResult(
            score=score,
            grade=grade,
            issues=issues,
            strengths=strengths,
            counts=counts,
            relation_types=dict(sorted(relation_counts.items())),
            current_entities=current_entities[:12],
            stale_entities=stale_entities[:12],
            recent_relations=relations[:20],
            profile_quality=profile_quality[:20],
        )

    def _profile_quality(self, profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        quality: list[dict[str, Any]] = []
        generic_slots = {"entity_type", "object_type", "located_at"}
        for profile in profiles:
            slots = profile.get("slots") or {}
            present_slots = sorted(str(key) for key, values in slots.items() if values)
            slot_order = list(profile.get("slot_order") or [])
            missing_slots = list(profile.get("missing_slots") or [])
            meaningful_slots = [slot for slot in present_slots if slot not in generic_slots]
            denominator = max(1, len(slot_order) or len(present_slots))
            quality.append(
                {
                    "label": profile.get("label"),
                    "kind": profile.get("kind"),
                    "status": profile.get("status"),
                    "present_slots": present_slots,
                    "meaningful_slots": meaningful_slots,
                    "missing_slots": missing_slots,
                    "present_count": len(present_slots),
                    "meaningful_count": len(meaningful_slots),
                    "coverage": round(len(present_slots) / denominator, 3),
                }
            )
        return quality


def audit_to_dict(result: GraphAuditResult) -> dict[str, Any]:
    return {
        "score": result.score,
        "grade": result.grade,
        "issues": result.issues,
        "strengths": result.strengths,
        "counts": result.counts,
        "relation_types": result.relation_types,
        "current_entities": result.current_entities,
        "stale_entities": result.stale_entities,
        "recent_relations": result.recent_relations,
        "profile_quality": result.profile_quality,
    }
