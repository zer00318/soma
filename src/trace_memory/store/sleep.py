"""World-grounded sleep binder.

Raw helper observations stay immutable. This layer individuates them into per-object (and
per-affordance) clusters — on what the helpers *saw* (canonical label + lexical identity),
NOT on the camera-pose ``scene_frustum`` anchor, which collapses every object in a frame
together — and authors one cited, reconsiderable state memory per cluster. Authoring uses a
local LLM (the builder) with a deterministic fallback, so the store always gains authored
``entity_memory`` / ``group_memory`` nodes backed by ``supports_memory`` citation links.

Background: with the old anchor-overlap binder, 696 observations collapsed into 3 components
of 420/234/42 nodes, all rejected by a size guard -> **zero** authored memories. This binder
authors ~100+ object memories instead.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

import re

from trace_memory.store.author import AuthoredRecord, LocalLLMAuthor, deterministic_author
from trace_memory.store.individuate import ObjectCluster, _node_track_id, individuate
from trace_memory.store.sqlite_store import TraceMemoryStore

# M6 landmark expansion — verbatim text captured on objects ("MICHIGAN STATE", "DEWALT")
# often answers questions in words the raw capture never contains ("which UNIVERSITY...").
# At sleep time (unbounded compute) the local model writes ONE clearly-flagged world-
# knowledge sentence per distinct verbatim, cited to the observations that read it. The
# note is explicitly "not observed" so the reasoner can use it without claiming sight.
_VERBATIM_TEXT_RE = re.compile(r'(?:label|ocr|provisional ocr) text: "([^"]{6,90})"', re.IGNORECASE)
_LANDMARK_PROMPT = (
    "Text was read off a physical object by a camera: \"{verbatim}\".\n"
    "In ONE short sentence, state what this text most likely refers to in the world "
    "(a brand, institution, product, place). Be concrete. If you cannot tell, output "
    "exactly UNKNOWN."
)
_MAX_LANDMARKS_PER_RUN = 8


def _landmark_context(verbatim: str, *, model: str, host: str, timeout: int = 60) -> str | None:
    """One world-knowledge sentence for a verbatim read, or None. Separated for testability."""
    data_prompt = _LANDMARK_PROMPT.format(verbatim=verbatim)
    import json as _json
    import urllib.request as _rq
    body = {"model": model, "prompt": data_prompt, "stream": False,
            "options": {"temperature": 0}}
    try:
        req = _rq.Request(f"{host.rstrip('/')}/api/generate",
                          data=_json.dumps(body).encode(),
                          headers={"content-type": "application/json"})
        raw = _json.load(_rq.urlopen(req, timeout=timeout)).get("response", "").strip()
    except Exception:  # noqa: BLE001  no LLM -> no expansion, never a crash
        return None
    if not raw or "unknown" in raw.lower()[:20]:
        return None
    return raw.splitlines()[0].strip()[:220]

# SPEECH STITCHER (P05) — the ASR channel commits sentence FRAGMENTS ("Everything I", then
# "do I do it just for you"...). Each lands as its own raw observation, so retrieval surfaces
# one shred without its sentence. At sleep time we JOIN adjacent fragments of the same session
# into ONE readable utterance memory, cited to every fragment. L2/L3: fragments are NEVER
# rewritten or deleted — we only concatenate their verbatim transcripts in time order, and the
# raw rows stay immutable. The verbatim used matches how the live brain reads these rows.
_SPEECH_HELPERS = {"asr", "apple_speech", "native_speech", "speech"}
# Transcript payload sits inside 'EVENT | nearby speech | transcript: "<verbatim>"'. Same regex
# the brain uses so what we stitch is exactly what a speech question would otherwise surface.
_STITCH_TRANSCRIPT_RE = re.compile(r'transcript:\s*"([^"]+)"')
# Two speech fragments < this gap apart, same session, are one continuous utterance. Wider gaps
# are a real pause between separate remarks and stay separate memories.
# MEASURED on the founder's real walks (2026-07-04): the OLD fixed-cadence commit path sliced
# continuous narration every 5-7s, so 3000ms never joined a single real fragment (0 utterances
# authored from 71 speech rows). Real pauses between remarks measured 22s/47s/63s. 8s joins
# every sliced narration and breaks at every real pause in the data.
_STITCH_GAP_MS = 8000


def _is_speech_node(node: Any) -> bool:
    """A raw speech/ASR observation, by the same signal the brain's ranker uses."""
    md = getattr(node, "metadata", None) or {}
    helper = str(md.get("helper") or md.get("helper_prompt") or "").lower()
    if helper in _SPEECH_HELPERS:
        return True
    return str(getattr(node, "text", "") or "").lower().startswith("event | nearby speech")


def _speech_verbatim(node: Any) -> str:
    """The verbatim words in a speech row: the quoted transcript if present, else the raw text.
    Never cleaned or rewritten (L2) — only extracted."""
    text = str(getattr(node, "text", "") or "")
    match = _STITCH_TRANSCRIPT_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _speech_session(node: Any) -> str:
    """Session key for grouping. Explicit session_id wins; else fall back to the row's source so
    fragments from one capture stream group together and don't cross unrelated captures."""
    md = getattr(node, "metadata", None) or {}
    session = md.get("session_id") or md.get("session")
    if session:
        return str(session)
    if getattr(node, "coordinate_frame", None) is not None:
        return f"cf:{node.coordinate_frame.session_id}"
    return f"src:{getattr(node, 'source', 'unknown')}"


# Author at most this many clusters with the (GPU-serial) local LLM; the rest get the cheap
# deterministic record. Clusters are ranked by evidence size so the richest objects get the LLM.
_MAX_LLM_CLUSTERS = 60
# A cluster needs at least this much evidence to be worth an LLM call (else deterministic).
_MIN_LLM_MEMBERS = 2


@dataclass(frozen=True)
class SleepRunSummary:
    grouped_observation_count: int
    abstraction_count: int
    composed_memory_count: int
    link_count: int
    retrieval_mode: str


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


class SleepConsolidator:
    """Individuate raw observations into object clusters and author cited state memories."""

    def __init__(
        self,
        store: TraceMemoryStore,
        *,
        author: Callable[[ObjectCluster], AuthoredRecord] | None = None,
        max_llm_clusters: int = _MAX_LLM_CLUSTERS,
        landmark_expansion: bool = True,
        landmark_context: Callable[..., str | None] = _landmark_context,
    ) -> None:
        self._store = store
        self._author = author if author is not None else LocalLLMAuthor()
        self._max_llm_clusters = max_llm_clusters
        self._landmark_expansion = landmark_expansion
        self._landmark_context = landmark_context
        llm = self._author if isinstance(self._author, LocalLLMAuthor) else None
        self._llm_model = llm.model if llm else "gemma3:12b-it-qat"
        self._llm_host = llm.host if llm else "http://127.0.0.1:11434"

    def consolidate(self) -> SleepRunSummary:
        # RECONSOLIDATION: the binder's own previous derived output is removed and re-derived
        # from immutable raw every run. Without this, a re-run accretes stale count/state
        # memories next to fresh ones (measured: a superseded per-track "3 keyboards" claim
        # kept outranking the co-visibility-resolved range). Raw capture is never touched.
        self._store.reconsider_derived("sleep")
        # A node is bindable when it is a RAW observation (not the binder's own derived output)
        # AND it carries an instance anchor. Two anchor kinds are accepted: a world coordinate
        # frame (the ARKit/LiDAR path) OR an on-device track_id (the coordinate-free path used by
        # live phone captures, which have no coordinate_frame). Without either, there is nothing to
        # fuse on, so the node is left as a raw observation.
        raw_nodes = [
            node
            for node in self._store.nodes(node_types=("observation", "entity"))
            if (node.immutable_raw and node.coordinate_frame is not None)
            or (not node.derived and _node_track_id(node) is not None)
        ]
        node_by_id = {node.id: node for node in raw_nodes}

        clusters = individuate(raw_nodes)
        # Rank clusters: bigger evidence first, so the LLM budget lands on the richest objects.
        clusters.sort(key=lambda c: (-len(c.members), c.kind != "group", c.label))

        existing_links = {
            (link.from_id, link.to_id, link.link_type) for link in self._store.links()
        }

        authored_count = 0
        grouped_ids: set[str] = set()
        created_links = 0
        llm_used = 0
        # Track distinct physical instances per label so we can author a DETERMINISTIC count
        # memory (count = number of coordinate-individuated instances; never an LLM guess).
        label_instances: dict[str, dict[str, Any]] = {}

        for cluster in clusters:
            if not cluster.members:
                continue
            use_llm = (
                self._author is not None
                and llm_used < self._max_llm_clusters
                and len(cluster.members) >= _MIN_LLM_MEMBERS
            )
            if use_llm:
                record = self._author(cluster)
                if record.authored_by == "local_llm":
                    llm_used += 1
            else:
                record = deterministic_author(cluster)

            support_ids = [sid for sid in record.support_ids if sid in node_by_id]
            if not support_ids:
                continue
            # Only author memories that COMPOSE something raw retrieval can't already answer:
            # Author only when the memory adds something raw retrieval can't trivially give AND it is
            # CONSENSUS-BACKED: a count, a resolved current location, a temporal contradiction, an
            # affordance group, or >=2 corroborating observations. A single-observation object is NOT
            # authored — one-off reads are often misreads (S3 consensus principle), and authoring them
            # both adds noise and risks displacing the raw obs in the answer window.
            composes = (
                cluster.kind == "group"
                or record.count is not None
                or bool(record.contradictions)
                or len(support_ids) >= 2
            )
            if not composes:
                continue
            anchor_node = max(
                (node_by_id[sid] for sid in support_ids),
                key=lambda n: (n.t_ms, n.id),
            )
            node_type = "group_memory" if cluster.kind == "group" else "entity_memory"
            session = (
                anchor_node.coordinate_frame.session_id
                if anchor_node.coordinate_frame is not None
                else "unknown"
            )
            member_signature = "|".join(sorted(support_ids))
            node_id = _stable_id("mem", session, cluster.kind, cluster.label, member_signature)
            if self._store.read_observation(node_id) is not None:
                continue

            memory_node = self._store.write_observation(
                text=record.node_text(),
                t_ms=anchor_node.t_ms,
                source=anchor_node.source,
                # Track-anchored memories carry no coordinate_frame, so the canonical helper_type
                # COLUMN would trip validation — tag them via metadata['helper'] instead (the same
                # convention live phone rows use). Coordinate-anchored memories keep the column.
                helper_type="sleep_binder" if anchor_node.coordinate_frame is not None else None,
                coordinate_frame=anchor_node.coordinate_frame.to_dict()
                if anchor_node.coordinate_frame
                else None,
                time_range=anchor_node.time_range.to_dict() if anchor_node.time_range else None,
                spatial_anchor=anchor_node.spatial_anchor.to_dict()
                if anchor_node.spatial_anchor
                else None,
                source_support={"support_ids": support_ids},
                place=anchor_node.place,
                pose=anchor_node.pose,
                provenance={"builder": "sleep", "authored_by": record.authored_by},
                metadata={
                    "helper": "sleep_binder",
                    "subject_hint": cluster.label,
                    "memory_kind": node_type,
                    "support_ids": support_ids,
                    "authored_by": record.authored_by,
                    "current_location": record.current_location,
                    "count": record.count,
                    "count_reasoning": record.count_reasoning,
                    "attributes": record.attributes,
                    "contradictions": record.contradictions,
                    "affordance": cluster.affordance,
                    "world_xyz": list(cluster.centroid) if cluster.centroid else None,
                    "instance_index": cluster.instance_index,
                    "instance_count": cluster.instance_count,
                },
                node_type=node_type,
                derived=True,
                immutable_raw=False,
                node_id=node_id,
            )
            authored_count += 1
            grouped_ids.update(support_ids)
            anchor = cluster.anchor_key or (
                str(tuple(round(v, 2) for v in cluster.centroid)) if cluster.centroid else None
            )
            if cluster.kind == "entity" and anchor is not None:
                info = label_instances.setdefault(
                    cluster.label,
                    {"count": cluster.instance_count, "low": cluster.count_low,
                     "anchors": [], "coords": [], "support": []},
                )
                info["count"] = max(info["count"], cluster.instance_count)
                if cluster.count_low is not None:
                    info["low"] = cluster.count_low if info["low"] is None else max(
                        info["low"], cluster.count_low)
                info["anchors"].append(anchor)
                if cluster.centroid is not None:
                    info["coords"].append([round(v, 2) for v in cluster.centroid])
                info["support"].extend(support_ids)

            for support_id in support_ids:
                link_key = (support_id, memory_node.id, "supports_memory")
                if link_key in existing_links:
                    continue
                self._store.link(
                    support_id,
                    memory_node.id,
                    "supports_memory",
                    metadata={"builder": "sleep"},
                    link_id=_stable_id("lnk-support", support_id, memory_node.id),
                )
                existing_links.add(link_key)
                created_links += 1

            # supersedes: the authored "current" state outranks earlier observations of the
            # same object that recorded a different moment, so "where is X currently" prefers it.
            if record.current_location:
                for support_id in support_ids:
                    member = node_by_id[support_id]
                    if member.t_ms >= anchor_node.t_ms:
                        continue
                    link_key = (memory_node.id, support_id, "supersedes")
                    if link_key in existing_links:
                        continue
                    self._store.link(
                        memory_node.id,
                        support_id,
                        "supersedes",
                        metadata={"builder": "sleep"},
                        link_id=_stable_id("lnk-supersedes", memory_node.id, support_id),
                    )
                    existing_links.add(link_key)
                    created_links += 1

        # COUNT MEMORIES: for every label whose evidence supports >=2 instances, author a memory
        # that states the count outright. This is the deterministic answer to "how many X" — the
        # brain reads a fact, it does not estimate from scattered observations. M2: instances are
        # co-visibility/attribute-resolved (a track is a sighting, not an object); when the strict
        # and liberal readings differ, the memory states an honest RANGE, never a confident guess.
        # binder_run_t versions the memory so a re-run's count supersedes a stale one at read time.
        binder_run_t = max((n.t_ms for n in raw_nodes), default=0)
        for label, info in label_instances.items():
            high = max(len(set(info["anchors"])), int(info["count"] or 0))
            low = int(info["low"]) if info.get("low") is not None else high
            low = min(low, high)
            if high < 2:
                continue
            support_ids = sorted(set(info["support"]))
            anchor_node = max((node_by_id[sid] for sid in support_ids), key=lambda n: (n.t_ms, n.id))
            node_id = _stable_id("count", anchor_node.coordinate_frame.session_id
                                 if anchor_node.coordinate_frame else "unknown", label,
                                 f"{low}-{high}")
            if self._store.read_observation(node_id) is not None:
                continue
            # Word the count by anchor kind: world coordinates when we have them (ARKit/LiDAR path),
            # else "distinct tracked instances" (the coordinate-free on-device track_id path) — never
            # claim coordinates we don't have.
            if info["coords"]:
                coords_txt = "; ".join(str(tuple(c)) for c in info["coords"][:8])
                text = (f"Counted {high} distinct {label} instances at separate locations "
                        f"(coordinates: {coords_txt}).")
            elif low != high:
                text = (f"Counted between {low} and {high} distinct {label} instances "
                        f"(co-visibility ambiguity across tracked sightings).")
            else:
                text = (f"Counted {high} distinct {label} instances, resolved from tracked "
                        f"sightings by co-visibility and attribute identity.")
            count_node = self._store.write_observation(
                text=text,
                t_ms=anchor_node.t_ms,
                source=anchor_node.source,
                helper_type="sleep_binder" if anchor_node.coordinate_frame is not None else None,
                coordinate_frame=anchor_node.coordinate_frame.to_dict() if anchor_node.coordinate_frame else None,
                time_range=anchor_node.time_range.to_dict() if anchor_node.time_range else None,
                spatial_anchor=anchor_node.spatial_anchor.to_dict() if anchor_node.spatial_anchor else None,
                source_support={"support_ids": support_ids},
                place=anchor_node.place,
                pose=anchor_node.pose,
                provenance={"builder": "sleep", "authored_by": "deterministic_count"},
                metadata={
                    "helper": "sleep_binder",
                    "subject_hint": label,
                    "memory_kind": "group_memory",
                    "support_ids": support_ids,
                    "count": high,
                    "count_low": low,
                    "count_high": high,
                    "covis_resolved": True,
                    "binder_run_t": binder_run_t,
                    "authored_by": "deterministic_count",
                },
                node_type="group_memory",
                derived=True,
                immutable_raw=False,
                node_id=node_id,
            )
            authored_count += 1
            for support_id in support_ids:
                link_key = (support_id, count_node.id, "supports_memory")
                if link_key in existing_links:
                    continue
                self._store.link(support_id, count_node.id, "supports_memory",
                                 metadata={"builder": "sleep"},
                                 link_id=_stable_id("lnk-count", support_id, count_node.id))
                existing_links.add(link_key)
                created_links += 1

        # LANDMARK EXPANSION (M6): one flagged world-knowledge sentence per distinct verbatim
        # text read off an object, cited to the reading observations. Fills the vocabulary gap
        # between what the camera read ("MICHIGAN STATE") and how questions are asked ("which
        # university..."). Skipped silently when no LLM is reachable — enrichment, never a
        # dependency.
        if self._landmark_expansion:
            expanded = 0
            seen_verbatims: set[str] = set()
            for cluster in clusters:
                if expanded >= _MAX_LANDMARKS_PER_RUN:
                    break
                if cluster.kind != "entity":
                    continue
                for member in cluster.members:
                    for verbatim in _VERBATIM_TEXT_RE.findall(getattr(member, "text", "") or ""):
                        key = verbatim.strip().lower()
                        if key in seen_verbatims or expanded >= _MAX_LANDMARKS_PER_RUN:
                            continue
                        seen_verbatims.add(key)
                        context = self._landmark_context(
                            verbatim, model=self._llm_model, host=self._llm_host)
                        if not context:
                            continue
                        support_ids = [n.id for n in cluster.members
                                       if verbatim in (getattr(n, "text", "") or "")]
                        if not support_ids:
                            continue
                        anchor_node = node_by_id.get(support_ids[0])
                        if anchor_node is None:
                            continue
                        node_id = _stable_id("landmark", cluster.label, key)
                        if self._store.read_observation(node_id) is not None:
                            continue
                        note = (f'World-knowledge note (not observed, derived from text read on '
                                f'the {cluster.label}): "{verbatim}" — {context}')
                        landmark_node = self._store.write_observation(
                            text=note,
                            t_ms=anchor_node.t_ms,
                            source=anchor_node.source,
                            source_support={"support_ids": support_ids},
                            place=anchor_node.place,
                            provenance={"builder": "sleep", "authored_by": "landmark_expansion"},
                            metadata={
                                "helper": "sleep_binder",
                                "subject_hint": cluster.label,
                                "memory_kind": "abstraction",
                                "support_ids": support_ids,
                                "verbatim": verbatim,
                                "world_knowledge": True,
                            },
                            node_type="abstraction",
                            derived=True,
                            immutable_raw=False,
                            node_id=node_id,
                        )
                        expanded += 1
                        authored_count += 1
                        for support_id in support_ids:
                            link_key = (support_id, landmark_node.id, "supports_memory")
                            if link_key in existing_links:
                                continue
                            self._store.link(support_id, landmark_node.id, "supports_memory",
                                             metadata={"builder": "sleep"},
                                             link_id=_stable_id("lnk-landmark", support_id,
                                                                landmark_node.id))
                            existing_links.add(link_key)
                            created_links += 1

        # SPEECH STITCHING (P05): heal shredded ASR capture into readable utterances. Uses the
        # SAME raw pool the binder skipped (speech rows carry no track anchor, so they were never
        # clustered above). Retroactive — old walks' fragments become one sentence, and future
        # captures stitch too. Reconsiderable: authored under builder=sleep, so reconsider_derived
        # wipes them next run and they re-derive from immutable raw.
        stitched, stitch_links = self._stitch_speech(existing_links)
        authored_count += stitched
        created_links += stitch_links

        return SleepRunSummary(
            grouped_observation_count=len(grouped_ids),
            abstraction_count=authored_count,
            composed_memory_count=authored_count,
            link_count=created_links,
            retrieval_mode=self._store.retrieval_mode,
        )

    def _stitch_speech(self, existing_links: set[tuple[str, str, str]]) -> tuple[int, int]:
        """Join adjacent same-session speech fragments (gap < _STITCH_GAP_MS) into one authored
        utterance memory citing every fragment. Raw fragments are never modified or deleted (L3);
        verbatim transcripts are only concatenated in time order, never rewritten (L2)."""
        speech_nodes = [
            node
            for node in self._store.nodes(node_types=("observation", "entity"))
            if not node.derived and _is_speech_node(node)
        ]
        if len(speech_nodes) < 2:
            return 0, 0

        # Group by session, ordered in time; within a session, break runs at gaps >= threshold.
        by_session: dict[str, list[Any]] = defaultdict(list)
        for node in speech_nodes:
            by_session[_speech_session(node)].append(node)

        authored = 0
        created_links = 0
        for session, nodes in by_session.items():
            nodes.sort(key=lambda n: (n.t_ms, n.id))
            run: list[Any] = []

            def flush(run_nodes: list[Any]) -> None:
                nonlocal authored, created_links
                if len(run_nodes) < 2:
                    return
                fragments = [(_speech_verbatim(n), n) for n in run_nodes]
                fragments = [(v, n) for v, n in fragments if v]
                if len(fragments) < 2:
                    return
                # JOIN verbatim in time order with a single space. No cleaning, no dedup of words —
                # the fragments' own words, concatenated. (Live capture already dedups cumulative
                # partials via the Swift delta baseline, so these are non-overlapping deltas.)
                utterance = " ".join(v for v, _ in fragments)
                support_ids = [n.id for _, n in fragments]
                first = fragments[0][1]
                last = fragments[-1][1]
                member_signature = "|".join(sorted(support_ids))
                node_id = _stable_id("utterance", session, member_signature)
                if self._store.read_observation(node_id) is not None:
                    return
                text = f'EVENT | speech utterance | transcript: "{utterance}"'
                metadata = {
                    "helper": "speech_stitcher",
                    "memory_kind": "event_memory",
                    "subject_hint": "speech",
                    "support_ids": support_ids,
                    "session": session,
                    "fragment_count": len(support_ids),
                    "t_ms_start": first.t_ms,
                    "t_ms_end": last.t_ms,
                    "authored_by": "speech_stitcher",
                    "stitched_verbatim": True,
                }
                mem = self._store.write_observation(
                    text=text,
                    t_ms=first.t_ms,
                    source=first.source,
                    time_range=first.time_range.to_dict() if first.time_range else None,
                    source_support={"support_ids": support_ids},
                    place=first.place,
                    provenance={"builder": "sleep", "authored_by": "speech_stitcher"},
                    metadata=metadata,
                    node_type="event_memory",
                    derived=True,
                    immutable_raw=False,
                    node_id=node_id,
                )
                authored += 1
                for support_id in support_ids:
                    link_key = (support_id, mem.id, "supports_memory")
                    if link_key in existing_links:
                        continue
                    self._store.link(
                        support_id, mem.id, "supports_memory",
                        metadata={"builder": "sleep"},
                        link_id=_stable_id("lnk-utterance", support_id, mem.id))
                    existing_links.add(link_key)
                    created_links += 1

            for node in nodes:
                if run and node.t_ms - run[-1].t_ms >= _STITCH_GAP_MS:
                    flush(run)
                    run = []
                run.append(node)
            flush(run)

        return authored, created_links
