#!/usr/bin/env python3
"""P34 Stage A — the AX adapter: the Mac's OWN semantic layer, not pixel guesses.

The brainstorm law (P34): a text at a coordinate is a title only under a THEORY
of the UI. On the Mac the theory's owner is the OS — the Accessibility tree
says "AXTab", "AXHeading", "AXButton" per element, for every app, generically.
This adapter walks the frontmost window's AX tree and emits the five P34
primitives with grade=authoritative; OCR remains the fallback channel
(grade=inferred) for what AX can't see (video frames, canvases).

Trust: needs the Accessibility TCC grant (System Settings → Privacy & Security
→ Accessibility) for the process that runs the daemon. `--request-trust`
triggers the system prompt; until granted the daemon silently stays OCR-only.

Browsers expose web content in the AX tree once AXEnhancedUserInterface is set
on the app element (the assistive-tech handshake) — done per app, idempotent.
"""

from __future__ import annotations

MAX_DEPTH = 9
MAX_ELEMENTS = 400
TEXT_ROLES = {  # roles whose text is CONTENT (vs pure structure)
    "AXStaticText", "AXHeading", "AXLink", "AXButton", "AXTab",
    "AXTextField", "AXTextArea", "AXMenuItem", "AXRadioButton",
    "AXCheckBox", "AXPopUpButton", "AXComboBox", "AXCell",
}


def ax_trusted(prompt: bool = False) -> bool:
    import ApplicationServices as AS
    if prompt:
        opts = {"AXTrustedCheckOptionPrompt": True}
        return bool(AS.AXIsProcessTrustedWithOptions(opts))
    return bool(AS.AXIsProcessTrusted())


def _attr(el, name):
    import ApplicationServices as AS
    err, value = AS.AXUIElementCopyAttributeValue(el, name, None)
    return value if err == 0 else None


def enable_web_ax(pid: int) -> None:
    """Assistive-tech handshake: browsers publish the web page's AX tree only
    when an AT is present; setting AXEnhancedUserInterface=true declares us."""
    import ApplicationServices as AS
    app = AS.AXUIElementCreateApplication(pid)
    try:
        AS.AXUIElementSetAttributeValue(app, "AXEnhancedUserInterface", True)
    except Exception:
        pass


def walk_front_window(pid: int) -> list[dict]:
    """Depth-first walk of the focused window's AX tree.
    Returns [{role, text, path, pos, size}] — bounded, never throws."""
    import ApplicationServices as AS
    app = AS.AXUIElementCreateApplication(pid)
    window = _attr(app, "AXFocusedWindow") or (
        (_attr(app, "AXWindows") or [None])[0])
    if window is None:
        return []
    out: list[dict] = []
    stack = [(window, [], 0)]
    while stack and len(out) < MAX_ELEMENTS:
        el, path, depth = stack.pop()
        role = str(_attr(el, "AXRole") or "?")
        text = ""
        for attr in ("AXValue", "AXTitle", "AXDescription"):
            v = _attr(el, attr)
            if isinstance(v, str) and v.strip():
                text = v.strip()
                break
        pos_v, size_v = _attr(el, "AXPosition"), _attr(el, "AXSize")
        pos = size = None
        try:
            import ApplicationServices as AS2
            if pos_v is not None:
                ok, pt = AS2.AXValueGetValue(pos_v, AS2.kAXValueCGPointType, None)
                if ok:
                    pos = (float(pt.x), float(pt.y))
            if size_v is not None:
                ok, sz = AS2.AXValueGetValue(size_v, AS2.kAXValueCGSizeType, None)
                if ok:
                    size = (float(sz.width), float(sz.height))
        except Exception:
            pass
        here = path + [role]
        if text and role in TEXT_ROLES:
            out.append({"role": role, "text": text[:300],
                        "path": "/".join(here), "pos": pos, "size": size})
        if depth < MAX_DEPTH:
            for child in (_attr(el, "AXChildren") or [])[:60]:
                stack.append((child, here, depth + 1))
    return out


# ------------------------------------------------------------- pure helpers

def container_path(app_name: str, url: str | None, element_path: str) -> str:
    """The P34 container path: display/app/(tab=url)/role-path — the digital
    twin of world/room/anchor/track. Pure."""
    parts = ["display:main", f"app:{app_name}"]
    if url:
        parts.append(f"tab:{url}")
    trimmed = "/".join(p for p in element_path.split("/")
                       if p not in ("AXWindow", "AXGroup", "?"))
    if trimmed:
        parts.append(trimmed)
    return "/".join(parts)


def elements_to_rows(app_name: str, url: str | None,
                     elements: list[dict], max_rows: int = 30) -> list[dict]:
    """AX elements -> contract observations. grade=authoritative: the OS said
    so. One row per element (they are individually addressable facts), capped
    by salience = text length (headings/titles beat chrome crumbs). Pure."""
    ranked = sorted(elements, key=lambda e: len(e["text"]), reverse=True)[:max_rows]
    rows = []
    for e in ranked:
        rows.append({
            "text": f"AXEL | app={app_name}"
                    + (f" | url={url}" if url else "")
                    + f" | role={e['role']} | text: {e['text']}",
            "provenance": {
                "app": app_name, "url": url, "role": e["role"],
                "container_path": container_path(app_name, url, e["path"]),
                "grade": "authoritative", "pos": e["pos"], "size": e["size"],
            },
        })
    return rows


if __name__ == "__main__":
    import sys
    if "--request-trust" in sys.argv:
        print("trusted:", ax_trusted(prompt=True),
              "(if False: System Settings → Privacy & Security → Accessibility)")
    else:
        from AppKit import NSWorkspace
        if not ax_trusted():
            print("NOT TRUSTED — run with --request-trust and grant access")
            sys.exit(1)
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        pid = app.processIdentifier()
        enable_web_ax(pid)
        els = walk_front_window(pid)
        print(f"{app.localizedName()}: {len(els)} text elements")
        for e in els[:15]:
            print(f"  [{e['role']:14s}] {e['text'][:80]}")
