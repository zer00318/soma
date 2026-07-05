"""Day digest — "what happened today" in 3-6 cited bullets (P31 Stage B).

Sleep-time organ: reads the EpisodeBuilder's episode rows (never raw capture
directly — the digest pyramid climbs, it does not free-associate), authors one
derived `digest_day` node per capture day under builder="digest".

Receipts discipline: every bullet carries the episode ids it summarizes —
same law as /ask citations. Prose comes from local gemma writing FROM the
structured episode facts only, with a deterministic fallback so a dead ollama
never silently produces nothing (the LocalLLMAuthor pattern). Thin days are
refusal-honest: mostly-blind days say so instead of confabulating richness.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from trace_memory.store.author import _ollama_json

_BUILDER = "digest"

# A day whose episodes total under this many observations is "mostly uncaptured"
THIN_DAY_OBSERVATIONS = 30


def _stable_id(day: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"trace-digest:{day}"))


def _span(node: Any) -> str:
    import datetime as _dt

    start = _dt.datetime.fromtimestamp(node.time_range.start_ms / 1000)
    end = _dt.datetime.fromtimestamp(node.time_range.end_ms / 1000)
    return f"{start:%H:%M}-{end:%H:%M}"


@dataclass(frozen=True)
class DigestRunSummary:
    reconsidered: int
    day_count: int
    thin_day_count: int


def deterministic_bullets(episodes: list[Any]) -> list[dict[str, Any]]:
    """Fallback prose: the biggest episodes, stated plainly with receipts."""
    ranked = sorted(
        episodes, key=lambda n: n.metadata.get("observation_count", 0), reverse=True
    )
    bullets = []
    for ep in ranked[:5]:
        label = ep.metadata.get("label", "capture")
        count = ep.metadata.get("observation_count", 0)
        chans = ",".join(ep.metadata.get("channels", {}))
        bullets.append({
            "text": f"{_span(ep)} at {label}: {count} observations ({chans})",
            "episode_ids": [ep.id],
        })
    return bullets


class DigestBuilder:
    """One cited digest_day node per capture day, from episode facts only."""

    def __init__(
        self,
        store: Any,
        *,
        use_llm: bool = True,
        model: str = "gemma3:12b-it-qat",
        host: str = "http://127.0.0.1:11434",
        timeout: int = 120,
    ) -> None:
        self._store = store
        self._use_llm = use_llm
        self._model = model
        self._host = host
        self._timeout = timeout

    def build(self) -> DigestRunSummary:
        removed = self._store.reconsider_derived(_BUILDER)
        episode_nodes = [
            n for n in self._store.nodes(node_types=["episode"])
            if n.metadata.get("builder") == "episodes"
        ]
        days: dict[str, dict[str, list[Any]]] = {}
        for n in episode_nodes:
            day = n.metadata.get("day")
            if not day:
                continue
            bucket = days.setdefault(day, {"episodes": [], "gaps": []})
            key = "gap" if n.metadata.get("kind") == "gap" else "episode"
            bucket["episodes" if key == "episode" else "gaps"].append(n)

        thin = 0
        for day, bucket in sorted(days.items()):
            thin += int(self._write_day(day, bucket["episodes"], bucket["gaps"]))
        return DigestRunSummary(
            reconsidered=removed, day_count=len(days), thin_day_count=thin
        )

    def _llm_bullets(
        self, episodes: list[Any]
    ) -> list[dict[str, Any]] | None:
        facts = "\n".join(
            f'- id={ep.id} span={_span(ep)} place={ep.metadata.get("label")} '
            f'observations={ep.metadata.get("observation_count")} '
            f'channels={",".join(ep.metadata.get("channels", {}))}'
            for ep in episodes
        )
        prompt = (
            "You summarize one day of a personal capture log. Below are the ONLY "
            "facts you may use — episode rows with ids. Write 3-6 short bullets "
            "describing the day. Every bullet MUST cite the episode ids it uses. "
            "Do not invent activities, objects, or places not present in the "
            "facts. Reply as JSON: "
            '{"bullets": [{"text": "...", "episode_ids": ["..."]}]}\n\n'
            f"FACTS:\n{facts}"
        )
        data = _ollama_json(
            prompt, model=self._model, host=self._host, timeout=self._timeout
        )
        if not data or not isinstance(data.get("bullets"), list):
            return None
        valid = {ep.id for ep in episodes}
        bullets = []
        for b in data["bullets"][:6]:
            ids = [i for i in (b.get("episode_ids") or []) if i in valid]
            text = str(b.get("text", "")).strip()
            if text and ids:  # uncited prose is dropped, not published
                bullets.append({"text": text, "episode_ids": ids})
        return bullets or None

    def _write_day(self, day: str, episodes: list[Any], gaps: list[Any]) -> bool:
        """Author one digest_day node; returns True when the day was thin."""
        total_obs = sum(e.metadata.get("observation_count", 0) for e in episodes)
        thin = total_obs < THIN_DAY_OBSERVATIONS
        bullets: list[dict[str, Any]] | None = None
        if not thin and self._use_llm:
            bullets = self._llm_bullets(episodes)
        if bullets is None:
            bullets = deterministic_bullets(episodes)
        if thin:
            bullets = [{
                "text": f"Mostly uncaptured: only {total_obs} observations all day.",
                "episode_ids": [e.id for e in episodes],
            }] + bullets[:2]

        start = min(e.time_range.start_ms for e in episodes)
        end = max(e.time_range.end_ms for e in episodes)
        gap_note = ""
        if gaps:
            from trace_memory.store.episodes import _human_duration

            blind_ms = sum(
                g.time_range.end_ms - g.time_range.start_ms for g in gaps
                if g.metadata.get("day") == day
            )
            if blind_ms:
                gap_note = f" | blind: {_human_duration(blind_ms)}"
        text = f"DIGEST | {day} | " + " • ".join(b["text"] for b in bullets) + gap_note
        self._store.write_observation(
            text=text,
            t_ms=start,
            source="sleep_binder",
            time_range={"start_ms": start, "end_ms": end},
            provenance={
                "builder": _BUILDER,
                "authored_by": "llm" if not thin and self._use_llm else "deterministic",
            },
            metadata={
                "builder": _BUILDER,
                "kind": "digest_day",
                "day": day,
                "bullets": bullets,
                "episode_count": len(episodes),
                "total_observations": total_obs,
                "thin_day": thin,
            },
            node_type="digest_day",
            derived=True,
            node_id=_stable_id(day),
        )
        return thin
