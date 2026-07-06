"""P34 Stage A — context slices: the reasoner gets a SCENE, not row soup.

The brainstorm law: relations are the product. A slice groups retrieved
observations by their CONTAINER (digital: display/app/tab(url)/region or the
AX container_path; physical: world/place) and aggregates repeats into one
line with a count and time range. The reasoner then sees

    ▸ display:main/app:Brave Browser/tab:https://youtube.com/watch?v=…/region:main
      • "Rao Bahadur (2026) Telugu DVDS" ×6 (17:08–17:53)  [inferred]
    ▸ world/Robert-Bosch-Straße 19
      • OBJECT | laptop ×14 (08:52–14:17)

instead of forty interleaved prose rows — "which container is this text in"
stops being the reasoner's job and becomes the prompt's shape. Grades ride
along (authoritative AX vs inferred OCR), so honesty can weight them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

MAX_CONTAINERS = 10
MAX_LINES_PER_CONTAINER = 8


def container_of(node: Any) -> str:
    """One container path per observation — the digital twin of the anchor
    hierarchy. Precedence: explicit AX container_path > daemon app/url/region
    > physical place from the location hint > unplaced."""
    prov = getattr(node, "provenance", None) or {}
    explicit = prov.get("container_path")
    if explicit:
        return str(explicit)
    app = prov.get("app")
    if app:
        parts = ["display:main", f"app:{app}"]
        if prov.get("url"):
            parts.append(f"tab:{prov['url']}")
        if prov.get("region"):
            parts.append(f"region:{prov['region']}")
        return "/".join(parts)
    hint = str(prov.get("location_hint", "") or "")
    if "|" in hint:
        street = hint.split("|", 1)[1].split(",", 1)[0].strip()
        if street:
            return f"world/{street}"
    place = getattr(node, "place", None)
    return f"world/{place}" if place else "world/unplaced"


def _content_text(node: Any) -> str:
    """The displayable content of a row — text after the last '| text:' marker
    if present (daemon rows), else the full row text."""
    text = str(getattr(node, "text", ""))
    if "| text:" in text:
        return text.rsplit("| text:", 1)[1].strip()
    return text.strip()


def _grade(node: Any) -> str:
    return str((getattr(node, "provenance", None) or {}).get("grade") or "inferred")


def _hhmm(t_ms: int) -> str:
    return datetime.fromtimestamp(t_ms / 1000).strftime("%H:%M")


@dataclass(frozen=True)
class SceneSlice:
    containers: tuple[tuple[str, tuple[dict, ...]], ...]
    rendered: str
    node_count: int


def build_slice(nodes: list[Any]) -> SceneSlice:
    """Group nodes by container, aggregate identical content, render a scene.
    Pure over its inputs; bounded output."""
    by_container: dict[str, dict[str, dict]] = {}
    for node in nodes:
        c = container_of(node)
        content = _content_text(node)
        if not content:
            continue
        bucket = by_container.setdefault(c, {})
        key = " ".join(content.lower().split())[:160]
        entry = bucket.get(key)
        t = int(getattr(node, "t_ms", 0))
        if entry is None:
            bucket[key] = {"text": content[:160], "count": 1, "t_lo": t,
                           "t_hi": t, "grade": _grade(node)}
        else:
            entry["count"] += 1
            entry["t_lo"] = min(entry["t_lo"], t)
            entry["t_hi"] = max(entry["t_hi"], t)
            if _grade(node) == "authoritative":
                entry["grade"] = "authoritative"

    ranked_containers = sorted(
        by_container.items(),
        key=lambda kv: sum(e["count"] for e in kv[1].values()),
        reverse=True,
    )[:MAX_CONTAINERS]

    lines: list[str] = []
    kept: list[tuple[str, tuple[dict, ...]]] = []
    for cpath, bucket in ranked_containers:
        entries = sorted(bucket.values(), key=lambda e: e["count"],
                         reverse=True)[:MAX_LINES_PER_CONTAINER]
        kept.append((cpath, tuple(entries)))
        lines.append(f"▸ {cpath}")
        for e in entries:
            when = _hhmm(e["t_lo"])
            if e["t_hi"] > e["t_lo"]:
                when += f"–{_hhmm(e['t_hi'])}"
            times = f" ×{e['count']} ({when})" if e["count"] > 1 else f" ({when})"
            lines.append(f'  • "{e["text"]}"{times}  [{e["grade"]}]')
    return SceneSlice(containers=tuple(kept), rendered="\n".join(lines),
                      node_count=len(nodes))
