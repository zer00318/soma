#!/usr/bin/env python3
"""Build a read-only capture-session index and dashboard."""
from __future__ import annotations

import argparse
import html
import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


THERMAL_ORDER = {
    "nominal": 0,
    "fair": 1,
    "serious": 2,
    "critical": 3,
}


def _json_load(path: Path) -> tuple[Any | None, str | None]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, str):
        value = value.strip().rstrip("%")
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _int_or_none(value: Any) -> int | None:
    out = _float_or_none(value)
    return int(out) if out is not None else None


def _round_or_none(value: float | None, places: int = 3) -> float | None:
    return round(value, places) if value is not None else None


def _capture_time(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _human_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{value} B"


def _duration_label(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    seconds_i = max(0, int(round(seconds)))
    minutes, sec = divmod(seconds_i, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {sec}s"
    return f"{sec}s"


def _thermal_state_name(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("state") or value.get("thermal_state") or value.get("label")
    text = str(value or "").strip().lower()
    if text.isdigit():
        states = ["nominal", "fair", "serious", "critical"]
        index = int(text)
        return states[index] if 0 <= index < len(states) else text
    return text or "unknown"


def _thermal_summary(meta: dict[str, Any]) -> tuple[int, str]:
    samples = meta.get("thermal") or meta.get("thermal_samples") or []
    if not isinstance(samples, list):
        samples = []
    states = [_thermal_state_name(sample) for sample in samples]
    if not states:
        state = _thermal_state_name(meta.get("thermal_state"))
        return (0, state if state != "unknown" else "unknown")
    return (
        len(states),
        max(states, key=lambda state: THERMAL_ORDER.get(state, -1)),
    )


def _device_label(meta: dict[str, Any]) -> str:
    direct = str(meta.get("device") or "").strip()
    if direct:
        return direct
    name = str(meta.get("device_name") or "").strip()
    model = str(meta.get("device_model") or "").strip()
    if name and model:
        return f"{name} ({model})"
    return name or model or ""


def _records_from_json(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        source = raw
    elif isinstance(raw, dict):
        source = raw.get("objects") or raw.get("labels") or raw.get("crops") or []
        if not isinstance(source, list):
            source = list(raw.values())
    else:
        source = []
    return [item for item in source if isinstance(item, dict)]


def _distinct_inventory_count(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        objects = raw.get("objects")
        if isinstance(objects, list):
            return sum(1 for item in objects if isinstance(item, dict))
        count = 0
        for key, value in raw.items():
            if key in {"schema", "generated_at", "source", "stats"}:
                continue
            if isinstance(value, dict):
                count += 1
        return count
    if isinstance(raw, list):
        labels = {
            str(item.get("label") or item.get("word") or item.get("name") or "").strip().lower()
            for item in raw
            if isinstance(item, dict)
        }
        labels.discard("")
        return len(labels) if labels else len(raw)
    return None


def _named_counts(raw: Any) -> tuple[int | None, int | None]:
    if raw is None:
        return None, None
    trusted = 0
    rejected = 0
    for record in _records_from_json(raw):
        trust = str(record.get("trust") or "trusted").strip().lower()
        if trust == "rejected":
            rejected += 1
        else:
            trusted += 1
    return trusted, rejected


def _positioned_count(raw: Any) -> int | None:
    if raw is None:
        return None
    count = 0
    for record in _records_from_json(raw):
        coords = [_float_or_none(record.get(axis)) for axis in ("x", "y", "z")]
        if all(coord is not None for coord in coords):
            count += 1
    return count


def _output_guard(walks_dir: Path, output_path: Path) -> bool:
    walks_resolved = walks_dir.resolve(strict=False)
    out_resolved = output_path.resolve(strict=False)
    try:
        out_resolved.relative_to(walks_resolved)
        return False
    except ValueError:
        return True


def _artifact_summary(work_dir: Path) -> dict[str, Any]:
    inventory_raw, inventory_error = _json_load(work_dir / "run_inventory.json")
    named_raw, named_error = _json_load(work_dir / "run_named.json")
    world_raw, world_error = _json_load(work_dir / "run_world.json")
    trusted_count, rejected_count = _named_counts(named_raw)
    summary = {
        "inventory_distinct_count": _distinct_inventory_count(inventory_raw),
        "named_trusted_count": trusted_count,
        "named_rejected_count": rejected_count,
        "world_positioned_count": _positioned_count(world_raw),
        "artifacts": {
            "run_inventory_json": (work_dir / "run_inventory.json").exists(),
            "run_named_json": (work_dir / "run_named.json").exists(),
            "run_world_json": (work_dir / "run_world.json").exists(),
        },
        "artifact_errors": {
            key: value
            for key, value in {
                "run_inventory_json": inventory_error,
                "run_named_json": named_error,
                "run_world_json": world_error,
            }.items()
            if value
        },
    }
    summary["processed"] = any(
        value is not None
        for value in (
            summary["inventory_distinct_count"],
            summary["named_trusted_count"],
            summary["named_rejected_count"],
            summary["world_positioned_count"],
        )
    )
    return summary


def capture_record(capture_dir: Path) -> dict[str, Any]:
    meta_raw, meta_error = _json_load(capture_dir / "meta.json")
    meta = meta_raw if isinstance(meta_raw, dict) else {}
    video_path = capture_dir / "video.mov"
    video_size = None
    if video_path.exists():
        try:
            video_size = video_path.stat().st_size
        except OSError:
            video_size = None
    battery_start_raw = meta.get("battery_start_pct") if meta.get("battery_start_pct") is not None else meta.get("battery_start")
    battery_stop_raw = meta.get("battery_stop_pct") if meta.get("battery_stop_pct") is not None else meta.get("battery_stop")
    duration_raw = meta.get("duration_seconds") if meta.get("duration_seconds") is not None else meta.get("duration")
    pose_count_raw = meta.get("pose_count") if meta.get("pose_count") is not None else meta.get("poses_count")
    battery_start = _float_or_none(battery_start_raw)
    battery_stop = _float_or_none(battery_stop_raw)
    drain = battery_start - battery_stop if battery_start is not None and battery_stop is not None else None
    thermal_samples, max_thermal_state = _thermal_summary(meta)
    updated_ts = meta.get("updated_ts") or meta.get("end_ts") or meta.get("stop_ts")
    start_ts = meta.get("start_ts") or meta.get("captured_at") or meta.get("created_at")
    sort_time = _capture_time(start_ts) or _capture_time(updated_ts)
    if sort_time is None:
        try:
            sort_time = capture_dir.stat().st_mtime
        except OSError:
            sort_time = 0.0

    record: dict[str, Any] = {
        "name": capture_dir.name,
        "path": str(capture_dir),
        "capture_id": str(meta.get("capture_id") or capture_dir.name),
        "start_ts": start_ts,
        "updated_ts": updated_ts,
        "sort_time": sort_time,
        "duration_seconds": _round_or_none(_float_or_none(duration_raw)),
        "duration_label": _duration_label(_float_or_none(duration_raw)),
        "battery_start_pct": _round_or_none(battery_start, 1),
        "battery_stop_pct": _round_or_none(battery_stop, 1),
        "battery_drain_pct": _round_or_none(drain, 1),
        "thermal_sample_count": thermal_samples,
        "max_thermal_state": max_thermal_state,
        "pose_count": _int_or_none(pose_count_raw),
        "build_sha": str(meta.get("app_build_sha") or meta.get("build_sha") or "").strip(),
        "device": _device_label(meta),
        "video_size_bytes": video_size,
        "video_size_label": _human_bytes(video_size),
        "has_meta_json": (capture_dir / "meta.json").exists(),
        "has_video_mov": video_path.exists(),
    }
    if meta_error:
        record["meta_error"] = meta_error
    record.update(_artifact_summary(capture_dir / "work"))
    return record


def build_index(walks_dir: Path) -> dict[str, Any]:
    captures: list[dict[str, Any]] = []
    if walks_dir.exists():
        for child in walks_dir.iterdir():
            if not child.is_dir():
                continue
            if (child / "meta.json").exists() or (child / "video.mov").exists():
                captures.append(capture_record(child))
    captures.sort(key=lambda item: float(item.get("sort_time") or 0.0), reverse=True)
    return {
        "schema": "capture_index.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "walks_dir": str(walks_dir),
        "capture_count": len(captures),
        "captures": captures,
    }


def _metric(value: Any, fallback: str = "unknown") -> str:
    return fallback if value is None or value == "" else html.escape(str(value))


def _drain_label(value: Any) -> str:
    if value is None:
        return "unknown"
    try:
        return f"{float(value):.1f} pp"
    except (TypeError, ValueError):
        return str(value)


def _bar_html(capture: dict[str, Any]) -> str:
    trusted = int(capture.get("named_trusted_count") or 0)
    rejected = int(capture.get("named_rejected_count") or 0)
    total_named = trusted + rejected
    if total_named > 0:
        trusted_width = 100.0 * trusted / total_named
        rejected_width = 100.0 - trusted_width
        return (
            '<div class="bar" title="trusted vs rejected named records">'
            f'<span class="bar-trusted" style="width:{trusted_width:.1f}%"></span>'
            f'<span class="bar-rejected" style="width:{rejected_width:.1f}%"></span>'
            "</div>"
        )
    distinct = int(capture.get("inventory_distinct_count") or 0)
    positioned = int(capture.get("world_positioned_count") or 0)
    if distinct or positioned:
        width = 100.0 if distinct else 0.0
        if distinct and positioned:
            width = max(8.0, min(100.0, 100.0 * positioned / distinct))
        return (
            '<div class="bar" title="positioned objects relative to distinct objects">'
            f'<span class="bar-positioned" style="width:{width:.1f}%"></span>'
            "</div>"
        )
    return ""


def render_html(index: dict[str, Any]) -> str:
    captures = index.get("captures") if isinstance(index.get("captures"), list) else []
    cards = []
    for capture in captures:
        name = html.escape(str(capture.get("name") or "capture"))
        processed = bool(capture.get("processed"))
        badge = '<span class="badge processed">processed</span>' if processed else '<span class="badge raw">not yet processed</span>'
        artifacts = capture.get("artifacts") if isinstance(capture.get("artifacts"), dict) else {}
        artifact_bits = ", ".join(k.replace("_json", "") for k, v in artifacts.items() if v) or "none"
        errors = capture.get("artifact_errors") if isinstance(capture.get("artifact_errors"), dict) else {}
        error_html = ""
        if errors:
            error_html = '<div class="errors">Artifact read issue: ' + html.escape("; ".join(f"{k}: {v}" for k, v in errors.items())) + "</div>"
        processed_html = ""
        if processed:
            processed_html = f"""
      <div class="pipeline">
        <div><strong>{_metric(capture.get('inventory_distinct_count'), '0')}</strong><span>distinct</span></div>
        <div><strong>{_metric(capture.get('named_trusted_count'), '0')}</strong><span>trusted</span></div>
        <div><strong>{_metric(capture.get('named_rejected_count'), '0')}</strong><span>rejected</span></div>
        <div><strong>{_metric(capture.get('world_positioned_count'), '0')}</strong><span>positioned</span></div>
      </div>
      {_bar_html(capture)}
"""
        cards.append(
            f"""
    <article class="card">
      <div class="card-head">
        <div>
          <h2>{name}</h2>
          <p>{html.escape(str(capture.get('capture_id') or ''))}</p>
        </div>
        {badge}
      </div>
      <div class="stats">
        <div><strong>{_metric(capture.get('duration_label'))}</strong><span>duration</span></div>
        <div><strong>{_drain_label(capture.get('battery_drain_pct'))}</strong><span>battery drain</span></div>
        <div><strong>{_metric(capture.get('max_thermal_state'))}</strong><span>max thermal</span></div>
        <div><strong>{_metric(capture.get('video_size_label'))}</strong><span>video size</span></div>
        <div><strong>{_metric(capture.get('pose_count'))}</strong><span>poses</span></div>
      </div>
      {processed_html}
      <div class="meta">
        <span>start: {_metric(capture.get('start_ts'))}</span>
        <span>device: {_metric(capture.get('device'))}</span>
        <span>build: {_metric(capture.get('build_sha'))}</span>
        <span>artifacts: {html.escape(artifact_bits)}</span>
      </div>
      {error_html}
    </article>
"""
        )
    empty = '<p class="empty">No capture directories found.</p>' if not cards else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Capture Sessions</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0f1115;
      --panel: #171b22;
      --panel-2: #1f2630;
      --text: #edf1f7;
      --muted: #9aa6b2;
      --line: #303846;
      --green: #41d17d;
      --red: #ff6b6b;
      --blue: #5aa7ff;
      --amber: #f4c95d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.4;
    }}
    main {{ width: min(1160px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 44px; }}
    header {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-end; margin-bottom: 18px; }}
    h1 {{ margin: 0; font-size: 28px; letter-spacing: 0; }}
    h2 {{ margin: 0; font-size: 19px; letter-spacing: 0; }}
    p {{ margin: 4px 0 0; color: var(--muted); }}
    .generated {{ color: var(--muted); font-size: 13px; text-align: right; }}
    .grid {{ display: grid; gap: 14px; }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .card-head {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }}
    .badge {{
      border-radius: 999px;
      padding: 5px 9px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }}
    .processed {{ background: rgba(65, 209, 125, 0.14); color: var(--green); }}
    .raw {{ background: rgba(244, 201, 93, 0.15); color: var(--amber); }}
    .stats, .pipeline {{
      display: grid;
      grid-template-columns: repeat(5, minmax(110px, 1fr));
      gap: 10px;
      margin-top: 16px;
    }}
    .pipeline {{ grid-template-columns: repeat(4, minmax(110px, 1fr)); }}
    .stats div, .pipeline div {{
      background: var(--panel-2);
      border-radius: 6px;
      padding: 10px;
      min-width: 0;
    }}
    strong {{ display: block; font-size: 18px; overflow-wrap: anywhere; }}
    span {{ color: var(--muted); font-size: 12px; }}
    .bar {{
      display: flex;
      height: 8px;
      overflow: hidden;
      background: #0a0c10;
      border-radius: 999px;
      margin-top: 12px;
      border: 1px solid #222935;
    }}
    .bar span {{ display: block; height: 100%; }}
    .bar-trusted {{ background: var(--green); }}
    .bar-rejected {{ background: var(--red); }}
    .bar-positioned {{ background: var(--blue); }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 16px;
      margin-top: 14px;
      color: var(--muted);
      font-size: 12px;
    }}
    .errors {{
      margin-top: 12px;
      color: #ffd7d7;
      background: rgba(255, 107, 107, 0.10);
      border-radius: 6px;
      padding: 8px;
      font-size: 12px;
    }}
    .empty {{ color: var(--muted); }}
    @media (max-width: 760px) {{
      header {{ display: block; }}
      .generated {{ text-align: left; margin-top: 8px; }}
      .stats, .pipeline {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .card-head {{ display: block; }}
      .badge {{ display: inline-block; margin-top: 10px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Capture Sessions</h1>
        <p>{len(captures)} captures from {html.escape(str(index.get("walks_dir") or ""))}</p>
      </div>
      <div class="generated">generated {html.escape(str(index.get("generated_at") or ""))}</div>
    </header>
    <section class="grid">
      {empty}
      {''.join(cards)}
    </section>
  </main>
</body>
</html>
"""


def write_outputs(index: dict[str, Any], out_json: Path, out_html: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_html.write_text(render_html(index), encoding="utf-8")


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        walks = root / "walks"
        capture = walks / "fake_capture"
        work = capture / "work"
        work.mkdir(parents=True)
        (capture / "meta.json").write_text(
            json.dumps(
                {
                    "capture_id": "fake_capture",
                    "battery_start_pct": 80,
                    "battery_stop_pct": 78,
                    "thermal": [
                        {"state": "nominal"},
                        {"state": "nominal"},
                        {"state": "nominal"},
                    ],
                    "duration_seconds": 600,
                    "pose_count": 5000,
                    "app_build_sha": "testsha",
                    "device_name": "Test iPhone",
                }
            ),
            encoding="utf-8",
        )
        (capture / "video.mov").write_bytes(b"0123456789")
        (work / "run_named.json").write_text(
            json.dumps(
                [
                    {"word": "mug", "trust": "trusted"},
                    {"word": "desk", "trust": "trusted"},
                    {"word": "phone", "trust": "trusted"},
                    {"word": "bedpan", "trust": "rejected"},
                ]
            ),
            encoding="utf-8",
        )
        out_json = root / "capture_index.json"
        out_html = root / "capture_index.html"
        index = build_index(walks)
        write_outputs(index, out_json, out_html)
        assert len(index["captures"]) == 1
        record = index["captures"][0]
        assert record["battery_drain_pct"] == 2
        assert record["named_trusted_count"] == 3
        assert out_json.exists()
        assert out_html.exists()
        assert "fake_capture" in out_html.read_text(encoding="utf-8")
    print("SELF-TEST PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--walks-dir", default="data/walks")
    parser.add_argument("--out-json", default="/tmp/capture_index.json")
    parser.add_argument("--out-html", default="/tmp/capture_index.html")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    walks_dir = Path(args.walks_dir)
    out_json = Path(args.out_json)
    out_html = Path(args.out_html)
    for output in (out_json, out_html):
        if not _output_guard(walks_dir, output):
            parser.error(f"refusing to write under walks dir: {output}")

    index = build_index(walks_dir)
    write_outputs(index, out_json, out_html)
    print(f"indexed {index['capture_count']} captures -> {out_json} and {out_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
