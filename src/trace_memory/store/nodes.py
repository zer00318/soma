"""N1 — the NODES brain: entity-centric memory (the brain before the brain).

Founder re-founding 2026-07-06: the LLM is the token-limited MOUTH; the actual
brain is the structure that feeds it. This builder converges the existing
organs (individuation clusters, containers, places) into PERSISTENT ENTITY
NODES: one node per THING — object instance, place, site, app — accruing
attributes with provenance grade, sighting stats, and time, plus containment
links (object located_at place). Row-centric observations stay immutable; the
entity layer is derived and reconsiderable (builder="nodes").

Every node carries `open_questions` — the seed of N2's mining ledger: what a
depth pass should extract next for this entity (colour unknown? brand unread?).

Node kinds v1:
  object — one per individuated instance (anchor_key identity, M2 machinery)
  place  — one per street/GPS-cell seen (world container heads)
  site   — one per web domain (digital container heads)
  app    — one per Mac/phone app observed
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any

from trace_memory.store.containers import container_head
from trace_memory.store.individuate import individuate, _node_track_id
from trace_memory.store.permanence import _COLOURS as _COLOUR_VOCAB

_BUILDER = "nodes"
_GRID_RE = re.compile(r"\b(upper|middle|lower)-(left|center|right) of frame\b", re.IGNORECASE)


def _stable_id(kind: str, key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"trace-entity:{kind}:{key}"))


def _street_of(node: Any) -> str | None:
    hint = str((getattr(node, "provenance", None) or {}).get("location_hint", "") or "")
    if "|" in hint:
        street = hint.split("|", 1)[1].split(",", 1)[0].strip()
        return street or None
    return None


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


@dataclass(frozen=True)
class NodesRunSummary:
    reconsidered: int
    object_nodes: int
    place_nodes: int
    site_nodes: int
    app_nodes: int
    links: int
    aggregates: int = 0


class NodesBuilder:
    """Sleep-time entity authoring. Reconsiderable; raw capture untouched."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def build(self) -> NodesRunSummary:
        removed = self._store.reconsider_derived(_BUILDER)
        raw = [n for n in self._store.nodes(node_types=("observation", "entity"))
               if not n.derived]

        object_nodes = self._build_objects(raw)
        place_nodes = self._build_places(raw)
        site_nodes, app_nodes = self._build_sites_and_apps(raw)

        aggregates = self._build_aggregates(object_nodes)

        # containment links: object located_at its dominant place
        links = 0
        place_ids = {p["key"]: p["id"] for p in place_nodes}
        for on in object_nodes:
            place_key = on.get("dominant_place")
            if place_key and place_key in place_ids:
                self._store.link(on["id"], place_ids[place_key], "located_at",
                                 metadata={"builder": _BUILDER})
                links += 1
        return NodesRunSummary(
            reconsidered=removed, object_nodes=len(object_nodes),
            place_nodes=len(place_nodes), site_nodes=len(site_nodes),
            app_nodes=len(app_nodes), links=links, aggregates=aggregates,
        )

    def _build_aggregates(self, object_nodes: list[dict]) -> int:
        """Fragment honesty (N1's first live finding: 30+ 'person' instance
        nodes = per-session track fragmentation). Heavily fragmented
        (label, place) groups get ONE aggregate node stating the fragment
        count plainly — identity resolution (P32) owns actually merging them;
        until then the surface shows one honest card, not thirty junk ones.
        Fragment nodes get aggregate_id so consumers can collapse them."""
        groups: dict[tuple, list[dict]] = {}
        for on in object_nodes:
            groups.setdefault((on["label"], on.get("dominant_place")), []).append(on)
        made = 0
        for (label, place), members in groups.items():
            if len(members) <= 5:
                continue
            agg_id = _stable_id("aggregate", f"{label}:{place}")
            total_sightings = sum(m.get("sightings", 0) for m in members)
            self._store.write_observation(
                text=(f"NODE | {label} @ {place or 'unplaced'} (aggregate) | "
                      f"{len(members)} track-fragments, {total_sightings} sightings"
                      f" | distinct-count unresolved (identity resolution pending)"),
                t_ms=max(m.get("t_hi", 0) for m in members),
                source="sleep_binder",
                provenance={"builder": _BUILDER, "authored_by": "nodes_v1"},
                metadata={"builder": _BUILDER, "kind": "entity",
                          "entity_type": "aggregate", "label": label,
                          "dominant_place": place, "fragments": len(members),
                          "sightings": total_sightings,
                          "fragment_ids": [m["id"] for m in members[:40]]},
                node_type="entity_node", derived=True, node_id=agg_id,
            )
            made += 1
        return made

    # ------------------------------------------------------------- objects

    def _build_objects(self, raw: list[Any]) -> list[dict]:
        trackable = [n for n in raw if _node_track_id(n) is not None
                     or getattr(n, "coordinate_frame", None) is not None]
        out: list[dict] = []
        for cluster in individuate(trackable):
            if not cluster.members or cluster.kind != "entity":
                continue
            members = cluster.members
            t_lo = min(m.t_ms for m in members)
            t_hi = max(m.t_ms for m in members)
            # anchor_key alone collides across sessions (per-session track ids —
            # the M2 lesson, re-taught by the live store on N1's first run);
            # first-sighting time disambiguates and is stable across rebuilds.
            key = f"{cluster.label}:{cluster.anchor_key or cluster.instance_index}:{t_lo}"
            attributes = self._mine_attributes(members)
            open_questions = self._open_questions(cluster.label, attributes)
            places = Counter(s for m in members if (s := _street_of(m)))
            dominant_place = places.most_common(1)[0][0] if places else None
            suffix = (f" #{cluster.instance_index}"
                      if cluster.instance_count > 1 else "")
            attr_text = "; ".join(
                f"{k}={v['value']}" for k, v in sorted(attributes.items()))
            node_id = _stable_id("object", key)
            self._store.write_observation(
                text=(f"NODE | {cluster.label}{suffix} | "
                      f"{len(members)} sightings | "
                      + (f"at {dominant_place} | " if dominant_place else "")
                      + (attr_text or "no attributes mined yet")),
                t_ms=t_hi,
                source="sleep_binder",
                time_range={"start_ms": t_lo, "end_ms": t_hi},
                provenance={"builder": _BUILDER, "authored_by": "nodes_v1"},
                metadata={
                    "builder": _BUILDER, "kind": "entity", "entity_type": "object",
                    "label": cluster.label, "anchor_key": cluster.anchor_key,
                    "instance_index": cluster.instance_index,
                    "instance_count": cluster.instance_count,
                    "sightings": len(members),
                    "attributes": attributes,
                    "open_questions": open_questions,
                    "dominant_place": dominant_place,
                    "member_sample": [m.id for m in members[:5]],
                },
                node_type="entity_node",
                derived=True,
                node_id=node_id,
            )
            out.append({"id": node_id, "key": key, "label": cluster.label,
                        "dominant_place": dominant_place,
                        "sightings": len(members), "t_hi": t_hi})
        return out

    def _mine_attributes(self, members: list[Any]) -> dict[str, dict]:
        """v1 attribute accrual from what capture already carries. Each
        attribute records value + evidence count + grade — the shape N2's
        depth passes will keep filling."""
        colours: Counter = Counter()
        brands: Counter = Counter()
        cells: Counter = Counter()
        for m in members:
            text = str(getattr(m, "text", ""))
            for w in _words(text):
                if w in _COLOUR_VOCAB:
                    colours[w] += 1
            bound = (getattr(m, "metadata", {}) or {}).get("bound_text")
            if bound:
                brands[str(bound)[:60]] += 1
            g = _GRID_RE.search(text)
            if g:
                cells[f"{g.group(1).lower()}-{g.group(2).lower()}"] += 1
        attrs: dict[str, dict] = {}
        if colours:
            v, c = colours.most_common(1)[0]
            attrs["colour"] = {"value": v, "evidence": c, "grade": "inferred"}
        if brands:
            v, c = brands.most_common(1)[0]
            attrs["brand_text"] = {"value": v, "evidence": c, "grade": "authoritative"}
        if cells:
            v, c = cells.most_common(1)[0]
            attrs["typical_position"] = {"value": v, "evidence": c, "grade": "inferred"}
        return attrs

    @staticmethod
    def _open_questions(label: str, attributes: dict) -> list[str]:
        """The mining ledger seed: what a targeted depth pass should extract
        next for this entity. N2 consumes and extends this list."""
        open_q = []
        if "colour" not in attributes:
            open_q.append("colour")
        if "brand_text" not in attributes:
            open_q.append("brand or written text")
        open_q.append("distinguishing marks or accessories")
        return open_q

    # -------------------------------------------------------------- places

    def _build_places(self, raw: list[Any]) -> list[dict]:
        by_place: dict[str, list[Any]] = {}
        for n in raw:
            street = _street_of(n)
            if street:
                by_place.setdefault(street, []).append(n)
        out = []
        for street, members in by_place.items():
            t_lo = min(m.t_ms for m in members)
            t_hi = max(m.t_ms for m in members)
            labels = Counter(
                (getattr(m, "metadata", {}) or {}).get("detector_label")
                for m in members)
            labels.pop(None, None)
            node_id = _stable_id("place", street)
            self._store.write_observation(
                text=(f"NODE | place: {street} | {len(members)} observations | "
                      f"things seen: {', '.join(k for k, _ in labels.most_common(5)) or '—'}"),
                t_ms=t_hi, source="sleep_binder",
                time_range={"start_ms": t_lo, "end_ms": t_hi},
                provenance={"builder": _BUILDER, "authored_by": "nodes_v1"},
                metadata={"builder": _BUILDER, "kind": "entity",
                          "entity_type": "place", "label": street,
                          "sightings": len(members),
                          "things_seen": dict(labels.most_common(10))},
                node_type="entity_node", derived=True, node_id=node_id,
            )
            out.append({"id": node_id, "key": street})
        return out

    # --------------------------------------------------------- sites, apps

    def _build_sites_and_apps(self, raw: list[Any]) -> tuple[list[dict], list[dict]]:
        sites: dict[str, list[Any]] = {}
        apps: dict[str, list[Any]] = {}
        for n in raw:
            prov = getattr(n, "provenance", None) or {}
            if prov.get("url"):
                sites.setdefault(container_head(n), []).append(n)
            elif prov.get("app"):
                apps.setdefault(str(prov["app"]), []).append(n)
        site_rows, app_rows = [], []
        for kind, bucket, rows in (("site", sites, site_rows), ("app", apps, app_rows)):
            for key, members in bucket.items():
                t_lo = min(m.t_ms for m in members)
                t_hi = max(m.t_ms for m in members)
                node_id = _stable_id(kind, key)
                minutes = max(1, int((t_hi - t_lo) / 60_000))
                self._store.write_observation(
                    text=(f"NODE | {kind}: {key} | {len(members)} observations "
                          f"across ~{minutes}m"),
                    t_ms=t_hi, source="sleep_binder",
                    time_range={"start_ms": t_lo, "end_ms": t_hi},
                    provenance={"builder": _BUILDER, "authored_by": "nodes_v1"},
                    metadata={"builder": _BUILDER, "kind": "entity",
                              "entity_type": kind, "label": key,
                              "sightings": len(members)},
                    node_type="entity_node", derived=True, node_id=node_id,
                )
                rows.append({"id": node_id, "key": key})
        return site_rows, app_rows
