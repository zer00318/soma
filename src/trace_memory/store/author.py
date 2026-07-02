"""Authoring layer for the world-grounded binder.

Turns an :class:`~trace_memory.store.individuate.ObjectCluster` into a single cited,
answer-ready state record. The local LLM (gemma3:27b) is the *builder* here — it reads only
the cluster's own observations and composes an extractive record; it may not add outside
knowledge, and every claim carries the observation ids that support it. A deterministic
fallback runs when the LLM is unavailable (tests, ollama down) so the store always gets
authored memories.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Any

_LOCATION_RE = re.compile(
    r"\b(?:on top of|on|in|inside|under(?:neath)?|next to|beside|behind|"
    r"draped over|leaning against|near|by|atop)\b\s+(?P<where>[^.;,)]{3,60})",
    re.IGNORECASE,
)
_COLOUR_RE = re.compile(
    r"\b(black|white|grey|gray|silver|brown|cream|red|blue|green|yellow|"
    r"pink|magenta|violet|purple|orange|beige|tan)\b",
    re.IGNORECASE,
)
_STATE_RE = re.compile(r"\b(open|closed|empty|full|partially used|used|sealed|on|off)\b", re.IGNORECASE)


@dataclass
class AuthoredRecord:
    label: str
    kind: str
    summary: str
    support_ids: list[str]
    current_location: str | None = None
    count: int | None = None
    count_reasoning: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)
    contradictions: list[str] = field(default_factory=list)
    authored_by: str = "deterministic"

    def node_text(self) -> str:
        """Compose the retrieval- and answer-friendly text the reasoner will read."""
        parts = [self.summary.strip().rstrip(".")] if self.summary.strip() else [self.label]
        if self.current_location:
            parts.append(f"Current/most-recent location: {self.current_location}")
        if self.count is not None:
            note = f"Distinct {self.label} count: {self.count}"
            if self.count_reasoning:
                note += f" ({self.count_reasoning})"
            parts.append(note)
        attr_bits = [f"{k}: {v}" for k, v in self.attributes.items() if v]
        if attr_bits:
            parts.append("; ".join(attr_bits))
        if self.contradictions:
            parts.append("Conflicting evidence over time: " + "; ".join(self.contradictions[:3]))
        return ". ".join(p for p in parts if p) + "."


def _members_evidence(cluster: Any, *, limit: int = 24) -> list[dict[str, Any]]:
    members = sorted(cluster.members, key=lambda n: (n.t_ms, n.id))
    if len(members) > limit:
        # Keep a temporal spread: earliest, latest, and an even sample between.
        step = len(members) / limit
        members = [members[int(i * step)] for i in range(limit)]
    rows = []
    for n in members:
        rows.append({
            "id": n.id,
            "t_ms": n.t_ms,
            "helper": str(getattr(n, "helper_type", None) or ""),
            "text": (n.text or "").strip()[:300],
        })
    return rows


def deterministic_author(cluster: Any) -> AuthoredRecord:
    """Rule-based, no-LLM authoring. Conservative: never guesses a count (relation cues are
    too noisy for a rule), extracts location/colour/state from the most recent observation."""
    members = sorted(cluster.members, key=lambda n: (n.t_ms, n.id))
    latest = members[-1]
    support_ids = [n.id for n in members]
    text = (latest.text or "").strip()

    location = None
    for n in reversed(members):
        m = _LOCATION_RE.search(n.text or "")
        if m:
            location = m.group("where").strip()
            break

    attributes: dict[str, str] = {}
    colours: list[str] = []
    for n in members:
        for c in _COLOUR_RE.findall(n.text or ""):
            cl = c.lower()
            if cl not in colours:
                colours.append(cl)
    if colours:
        attributes["colour"] = ", ".join(colours[:3])
    st = _STATE_RE.search(text)
    if st:
        attributes["state"] = st.group(1).lower()

    if cluster.kind == "group" and cluster.affordance:
        distinct = []
        for n in members:
            head = (n.text or "").strip()[:48]
            if head and head not in distinct:
                distinct.append(head)
        summary = f"Ways to {cluster.affordance}: " + "; ".join(distinct[:6])
    else:
        summary = f"{cluster.label}: {text[:140]}"

    return AuthoredRecord(
        label=cluster.label,
        kind=cluster.kind,
        summary=summary,
        support_ids=support_ids,
        current_location=location,
        attributes=attributes,
        authored_by="deterministic",
    )


_ENTITY_PROMPT = (
    "You are a memory binder. Below are raw observations of ONE kind of object seen across a "
    "single room capture. Each has an id, a timestamp t_ms (higher = later), and text.\n"
    "Compose ONE factual record using ONLY these observations — no outside knowledge, no "
    "guessing. Cite observation ids for every claim.\n\n"
    "RULES:\n"
    "- current_location: the location stated in the MOST RECENT (highest t_ms) observations. "
    "If earlier observations place it elsewhere, list those in contradictions.\n"
    "- count: the number of DISTINCT physical instances. Read multiplicity cues like "
    "'stacked on another', 'second jar', '2 stacked + 1 separate', counts across different "
    "surfaces/times. Do NOT just count observations. If genuinely unknowable, use null.\n"
    "- attributes: only colour/state/material explicitly seen. Omit if unsure.\n"
    "- summary: <=40 words, answer-ready, concrete.\n"
    "- Output STRICT JSON only, no prose, no markdown fence.\n\n"
    "OBJECT LABEL: {label}\n"
    "OBSERVATIONS:\n{evidence}\n\n"
    "JSON SHAPE:\n"
    '{{"summary": str, "current_location": {{"where": str|null, "support_ids": [str]}}, '
    '"count": {{"value": int|null, "support_ids": [str], "reasoning": str}}, '
    '"attributes": {{"colour": str|null, "state": str|null, "material": str|null}}, '
    '"contradictions": [str], "support_ids": [str]}}'
)

_GROUP_PROMPT = (
    "You are a memory binder. Below are observations of several DISTINCT objects that could "
    "each answer the affordance '{label}'. Using ONLY these observations, list every distinct "
    "option actually seen. No outside knowledge.\n"
    "Output STRICT JSON only:\n"
    '{{"summary": str (start with "Ways to ...", enumerate every distinct option), '
    '"options": [str], "support_ids": [str]}}\n\n'
    "AFFORDANCE: {label}\nOBSERVATIONS:\n{evidence}"
)


def _ollama_json(prompt: str, *, model: str, host: str, timeout: int) -> dict[str, Any] | None:
    body = {"model": model, "prompt": prompt, "stream": False,
            "format": "json", "options": {"temperature": 0}}
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        raw = json.load(urllib.request.urlopen(req, timeout=timeout)).get("response", "")
    except Exception:
        return None
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None


class LocalLLMAuthor:
    """Callable that authors a record per cluster with a local gemma model, falling back to
    :func:`deterministic_author` on any failure (so the binder never silently produces nothing)."""

    def __init__(
        self,
        *,
        model: str = "gemma3:12b-it-qat",
        host: str = "http://127.0.0.1:11434",
        timeout: int = 240,
    ) -> None:
        self.model = model
        self.host = host
        self.timeout = timeout

    def __call__(self, cluster: Any) -> AuthoredRecord:
        evidence = _members_evidence(cluster)
        valid_ids = {row["id"] for row in evidence}
        ev_text = "\n".join(
            f'- id={r["id"]} t_ms={r["t_ms"]} [{r["helper"]}] {r["text"]}' for r in evidence
        )
        base = deterministic_author(cluster)

        if cluster.kind == "group":
            data = _ollama_json(
                _GROUP_PROMPT.format(label=cluster.label, evidence=ev_text),
                model=self.model, host=self.host, timeout=self.timeout,
            )
            if not data or not str(data.get("summary") or "").strip():
                return base
            base.summary = str(data["summary"]).strip()
            base.support_ids = [i for i in (data.get("support_ids") or base.support_ids) if i in valid_ids] or base.support_ids
            base.authored_by = "local_llm"
            return base

        data = _ollama_json(
            _ENTITY_PROMPT.format(label=cluster.label, evidence=ev_text),
            model=self.model, host=self.host, timeout=self.timeout,
        )
        if not data or not str(data.get("summary") or "").strip():
            return base

        def _clean_ids(raw: Any) -> list[str]:
            return [i for i in (raw or []) if isinstance(i, str) and i in valid_ids]

        summary = str(data.get("summary") or "").strip()
        loc = data.get("current_location") or {}
        where = loc.get("where") if isinstance(loc, dict) else None
        cnt = data.get("count") or {}
        count_val = cnt.get("value") if isinstance(cnt, dict) else None
        if not isinstance(count_val, int):
            count_val = None
        def _flatten_attr(v: Any) -> str:
            if isinstance(v, (list, tuple)):
                return ", ".join(str(x).strip() for x in v if str(x).strip())
            return str(v).strip()

        attrs_raw = data.get("attributes") or {}
        attributes = {
            k: _flatten_attr(v)
            for k, v in attrs_raw.items()
            if v and _flatten_attr(v).lower() not in {"null", "none", "unknown", ""}
        } if isinstance(attrs_raw, dict) else {}
        contradictions = [str(c).strip() for c in (data.get("contradictions") or []) if str(c).strip()]
        support = _clean_ids(data.get("support_ids")) or base.support_ids

        return AuthoredRecord(
            label=cluster.label,
            kind=cluster.kind,
            summary=summary,
            support_ids=support,
            current_location=str(where).strip() if where and str(where).strip().lower() not in {"null", "none"} else None,
            count=count_val,
            count_reasoning=str(cnt.get("reasoning")).strip() if isinstance(cnt, dict) and cnt.get("reasoning") else None,
            attributes=attributes,
            contradictions=contradictions,
            authored_by="local_llm",
        )
