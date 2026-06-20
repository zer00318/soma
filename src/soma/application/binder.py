"""The binder: project the append-only observation stream into bound memory.

This is the moat the North Star names -- "at night, bind scattered facts by when
they co-occurred; weak links are refused, not hardened." The binding decision is
deliberately *mechanical* (consensus over typed observations), never a model
call: that is what makes it auditable and keeps a fluent-but-wrong caption from
hardening into a confident memory.

Three refusals encode "refuse weak links":
  - insufficient_support : seen too few times to assert it exists at all;
  - ambiguous_conflict   : competing values with no clear winner (the bag was
                           called blue twice and black twice -> bind neither);
  - low_confidence       : repeated, but every sighting was itself unsure.

Refusals are returned, not dropped, so the gap is inspectable instead of silent.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from soma.domain.binding import Binding
from soma.domain.confidence import Confidence
from soma.domain.entity import Entity
from soma.domain.observation import Observation
from soma.domain.provenance import Provenance
from soma.ports.memory_store import MemoryStore


@dataclass(frozen=True)
class RefusedLink:
    subject: str
    attribute: str
    reason: str


@dataclass(frozen=True)
class BindResult:
    entities: tuple[Entity, ...]
    bindings: tuple[Binding, ...]
    refused: tuple[RefusedLink, ...]


def _normalize(subject: str) -> str:
    return " ".join(subject.lower().split())


def _stable_id(*parts: str) -> str:
    # sha1 is a stable content id here, not a security primitive
    digest = hashlib.sha1(" ".join(parts).encode("utf-8"))
    return digest.hexdigest()[:12]


def _noisy_or(confidences: Iterable[float]) -> float:
    """Aggregate independent supports: repeated weak reads compound into trust."""
    product = 1.0
    for value in confidences:
        product *= 1.0 - value
    return 1.0 - product


class Binder:
    """Consensus projection over typed observations. Pure; no I/O, no model."""

    def __init__(self, min_support: int = 2, min_confidence: float = 0.5, margin: int = 1) -> None:
        self._min_support = min_support
        self._min_confidence = min_confidence
        self._margin = margin

    def project(self, store: MemoryStore) -> BindResult:
        return self.bind(store.observations())

    def bind(self, observations: Iterable[Observation]) -> BindResult:
        groups: dict[str, list[Observation]] = defaultdict(list)
        for obs in observations:
            groups[_normalize(obs.subject)].append(obs)

        entities: list[Entity] = []
        bindings: list[Binding] = []
        refused: list[RefusedLink] = []
        for key, group in groups.items():
            if len(group) < self._min_support:
                refused.append(RefusedLink(group[0].subject, "<entity>", "insufficient_support"))
                continue
            entity = self._entity_for(key, group)
            entities.append(entity)
            self._bind_attributes(entity, group, bindings, refused)

        return BindResult(tuple(entities), tuple(bindings), tuple(refused))

    def _entity_for(self, key: str, group: list[Observation]) -> Entity:
        kind = Counter(obs.kind for obs in group).most_common(1)[0][0]
        label = Counter(obs.subject for obs in group).most_common(1)[0][0]
        return Entity(entity_id=_stable_id(key), kind=kind, label=label)

    def _bind_attributes(
        self,
        entity: Entity,
        group: list[Observation],
        bindings: list[Binding],
        refused: list[RefusedLink],
    ) -> None:
        by_attr: dict[str, dict[str, list[tuple[float, Provenance]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for obs in group:
            for attr in obs.attributes:
                by_attr[attr.name][attr.value].append((obs.confidence.value, obs.provenance))

        for attr_name, value_support in by_attr.items():
            outcome = self._resolve_attribute(entity, attr_name, value_support)
            if isinstance(outcome, Binding):
                bindings.append(outcome)
            else:
                refused.append(outcome)

    def _resolve_attribute(
        self,
        entity: Entity,
        attr_name: str,
        value_support: dict[str, list[tuple[float, Provenance]]],
    ) -> Binding | RefusedLink:
        ranked = sorted(value_support.items(), key=lambda kv: len(kv[1]), reverse=True)
        value, support = ranked[0]
        if len(support) < self._min_support:
            return RefusedLink(entity.label, attr_name, "insufficient_support")
        if len(ranked) > 1 and len(support) - len(ranked[1][1]) < self._margin:
            return RefusedLink(entity.label, attr_name, "ambiguous_conflict")
        aggregate = _noisy_or(conf for conf, _ in support)
        if aggregate < self._min_confidence:
            return RefusedLink(entity.label, attr_name, "low_confidence")
        return Binding(
            binding_id=_stable_id(entity.entity_id, attr_name, value),
            subject_id=entity.entity_id,
            predicate=attr_name,
            object_id=None,
            object_text=value,
            confidence=Confidence(min(aggregate, 1.0)),
            evidence=tuple(prov for _, prov in support),
        )
