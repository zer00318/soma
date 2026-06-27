import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from node_merge import merge_jittered, brand_tokens  # noqa: E402


def _node(type_, texts, xyz, frames):
    return {"type": type_, "texts": texts, "label": f"{type_} {texts[0]}" if texts else type_,
            "world_xyz": xyz, "frames": frames, "count_frames": len(frames), "located": xyz is not None}


def _result(nodes):
    return {"nodes": nodes, "counts_by_type": {}, "summary": ""}


def test_merge_same_brand_close():
    nodes = [_node("jar", ["nutella", "Nutella jar"], [0.0, 0.0, 0.0], [0, 1]),
             _node("jar", ["nutella"], [0.10, 0.0, 0.0], [2])]
    out = merge_jittered(_result(nodes), radius_m=0.15)
    assert out["counts_by_type"]["jar"]["distinct"] == 1


def test_no_merge_far():
    nodes = [_node("jar", ["nutella"], [0.0, 0.0, 0.0], [0]),
             _node("jar", ["nutella"], [0.50, 0.0, 0.0], [1])]
    out = merge_jittered(_result(nodes), radius_m=0.15)
    assert out["counts_by_type"]["jar"]["distinct"] == 2


def test_no_merge_disjoint_brand():
    nodes = [_node("jar", ["nutella"], [0.0, 0.0, 0.0], [0]),
             _node("jar", ["barilla"], [0.05, 0.0, 0.0], [1])]
    out = merge_jittered(_result(nodes), radius_m=0.15)
    assert out["counts_by_type"]["jar"]["distinct"] == 2


def test_merge_generic_close():
    nodes = [_node("jar", ["Jar"], [0.0, 0.0, 0.0], [0]),
             _node("jar", ["Jar"], [0.08, 0.0, 0.0], [1])]
    out = merge_jittered(_result(nodes), radius_m=0.15)
    assert out["counts_by_type"]["jar"]["distinct"] == 1


def test_frames_union_no_double_count():
    nodes = [_node("jar", ["nutella"], [0.0, 0.0, 0.0], [0, 1]),
             _node("jar", ["nutella"], [0.05, 0.0, 0.0], [1, 2])]
    out = merge_jittered(_result(nodes), radius_m=0.15)
    assert out["nodes"][0]["count_frames"] == 3  # frames {0,1,2}


def test_none_xyz_and_empty():
    nodes = [_node("jar", ["nutella"], None, [0]),
             _node("jar", ["nutella"], None, [1])]
    out = merge_jittered(_result(nodes), radius_m=0.15)
    assert out["counts_by_type"]["jar"]["distinct"] == 2  # no coords -> never merged
    assert merge_jittered(_result([]), 0.15)["nodes"] == []


def test_brand_tokens_excludes_generic():
    n = _node("jar", ["Nutella jar", "Hazelnut spread"], [0, 0, 0], [0])
    assert "nutella" in brand_tokens(n)
    assert "jar" not in brand_tokens(n) and "spread" not in brand_tokens(n)
