import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from capture_integrity import audit_native_meta, build_offline_audit, timeline_stats


def _good_meta():
    return {
        "final": True,
        "video_file": "video.mov",
        "video_duration_seconds": 92.0,
        "duration_seconds": 92.2,
        "frame_count": 2760,
        "dropped_video_frames": 0,
        "max_frame_gap_seconds": 0.04,
        "audio_recorded": True,
        "audio_file": "audio.m4a",
        "audio_duration_seconds": 91.9,
        "audio_start_offset_seconds": 0.1,
        "pose_count": 920,
        "pose_end_seconds": 91.9,
    }


def test_native_contract_accepts_complete_replayable_capture():
    assert audit_native_meta(_good_meta())["pass"] is True


def test_native_contract_exposes_missing_channels_and_tail():
    meta = _good_meta()
    meta.update({
        "dropped_video_frames": 4,
        "max_frame_gap_seconds": 1.2,
        "audio_recorded": False,
        "audio_duration_seconds": 0,
        "pose_end_seconds": 80,
    })
    failures = audit_native_meta(meta)["failures"]
    assert "video_frames_dropped" in failures
    assert "video_timeline_gap" in failures
    assert "audio_evidence_missing" in failures
    assert "pose_tail_missing" in failures


def test_offline_audit_keeps_raw_source_authoritative(tmp_path):
    source = tmp_path / "clip.mov"
    source.write_bytes(b"source-video")
    frames = tmp_path / "frames"
    frames.mkdir()
    for name in ("frame_000_0.0s.jpg", "frame_001_0.5s.jpg", "frame_002_1.0s.jpg"):
        (frames / name).write_bytes(b"jpg")
    audit = build_offline_audit(str(source), str(frames), 1.0)
    assert audit["real_time_proven"] is False
    assert audit["source"]["retained"] is True
    assert audit["derived_frame_index"]["tail_gap_seconds"] == 0
    assert audit["source"]["sha256"]


def test_timeline_stats_reports_the_largest_hole():
    assert timeline_stats([0.0, 0.5, 4.0])["max_gap_seconds"] == 3.5
