from __future__ import annotations

import json

import scripts.trace_brain_server as brain


def test_capture_preserves_existing_kf_memory_on_restart(tmp_path, monkeypatch):
    moment_dir = tmp_path / "persisted-moment"
    moment_dir.mkdir()
    existing = [
        {"t": float(i), "frame": f"f_{i}", "caption": f"old {i}", "ocr": []}
        for i in range(5)
    ]
    (moment_dir / "kf_memory.json").write_text(json.dumps(existing))

    monkeypatch.setattr(brain, "_moment_dir", lambda moment_id: moment_dir)
    brain._LIVE.clear()

    first = brain._capture({"moment_id": "persisted-moment", "memory_text": "new frame 1"})
    rows = json.loads((moment_dir / "kf_memory.json").read_text())
    assert first["ok"] is True
    assert first["frames"] == 6
    assert len(rows) == 6
    assert rows[:5] == existing
    assert rows[-1]["caption"] == "new frame 1"

    second = brain._capture({"moment_id": "persisted-moment", "memory_text": "new frame 2"})
    rows = json.loads((moment_dir / "kf_memory.json").read_text())
    assert second["ok"] is True
    assert second["frames"] == 7
    assert len(rows) == 7
    assert rows[:5] == existing
    assert rows[-2]["caption"] == "new frame 1"
    assert rows[-1]["caption"] == "new frame 2"

    brain._LIVE.clear()
