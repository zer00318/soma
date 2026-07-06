"""P34 — container identity for any observation (store-layer, shared).

One container path per observation: the digital twin of the anchor hierarchy.
Precedence: explicit AX container_path > daemon app/tab(url)/region >
physical place from the location hint > unplaced. Consumed by the brain's
slice renderer AND the sleep organs (episodes/digests), so the whole stack
speaks one container vocabulary.
"""

from __future__ import annotations

import urllib.parse
from typing import Any


def container_of(node: Any) -> str:
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


def container_head(node: Any) -> str:
    """The human-scale container: a site domain for digital rows, the place
    for physical rows — what a day digest should NAME ('youtube.com', not a
    90-char tab path)."""
    prov = getattr(node, "provenance", None) or {}
    url = prov.get("url")
    if url:
        domain = urllib.parse.urlparse(str(url)).netloc
        if domain:
            return domain.removeprefix("www.")
    app = prov.get("app")
    if app:
        return str(app)
    path = container_of(node)
    if path.startswith("world/"):
        return path.removeprefix("world/")
    return path.split("/")[-1]


def content_text(node: Any) -> str:
    """Displayable content — text after the last '| text:' marker (daemon
    rows), else the full row text."""
    text = str(getattr(node, "text", ""))
    if "| text:" in text:
        return text.rsplit("| text:", 1)[1].strip()
    return text.strip()


def grade_of(node: Any) -> str:
    return str((getattr(node, "provenance", None) or {}).get("grade") or "inferred")
