from __future__ import annotations

from types import SimpleNamespace

from trace_memory.brain.slices import build_slice, container_of


def _n(text, t_ms, prov=None, place=None):
    return SimpleNamespace(text=text, t_ms=t_ms, provenance=prov or {}, place=place)


def test_containers_separate_tab_from_playing_content():
    yt = {"app": "Brave Browser", "url": "https://youtube.com/watch?v=x", "region": "main"}
    rail = {"app": "Brave Browser", "url": "https://youtube.com/watch?v=x", "region": "left-rail"}
    nodes = [
        _n("SCREEN | app=Brave | text: TEAMWORK DEATHRUN", 1000, yt),
        _n("SCREEN | app=Brave | text: TEAMWORK DEATHRUN", 61_000, yt),
        _n("SCREEN | app=Brave | text: Rao Bahadur (2026)", 2000, rail),
        _n("OBJECT | laptop", 3000, {"location_hint": "GPS 1,2 | Waldstrasse, Garching"}),
    ]
    scene = build_slice(nodes)
    r = scene.rendered
    # the founder's case, structurally: same page, DIFFERENT containers
    assert "region:main" in r and "region:left-rail" in r
    assert "world/Waldstrasse" in r
    main_part = r.split("region:main")[1].split("▸")[0]
    assert "TEAMWORK DEATHRUN" in main_part and "Rao Bahadur" not in main_part


def test_repeats_aggregate_with_count_and_span():
    prov = {"app": "Terminal"}
    nodes = [_n("SCREEN | x | text: pytest green", t, prov) for t in (0, 60_000, 120_000)]
    scene = build_slice(nodes)
    assert "×3" in scene.rendered and "01:00" in scene.rendered  # span end shown


def test_ax_container_path_and_grade_win():
    ax = {"container_path": "display:main/app:Brave/tab:u/AXWebArea/AXHeading",
          "grade": "authoritative"}
    node = _n("AXEL | app=Brave | role=AXHeading | text: The Title", 1000, ax)
    assert container_of(node).endswith("AXWebArea/AXHeading")
    scene = build_slice([node])
    assert "[authoritative]" in scene.rendered
