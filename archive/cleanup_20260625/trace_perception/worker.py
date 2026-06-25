from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, OrderedDict

import cv2
from ultralytics import YOLO

from trace_perception.colors import dominant_color_name
from trace_perception.memory import MemoryEmitter
from trace_perception.models import Detection, TrackState, utc_now_iso
from trace_perception.scheduler import (
    EnrichmentScheduler,
    SalienceScorer,
    TokenBucket,
    TrackView,
)


class PerceptionWorker:
    def __init__(
        self,
        camera_index: int,
        model_name: str,
        frame_stride: int,
        confidence: float,
        enrich_budget_per_hour: float = 0.0,
    ) -> None:
        self.camera_index = camera_index
        self.model = YOLO(model_name)
        self.frame_stride = max(1, frame_stride)
        self.confidence = confidence
        self.tracks: OrderedDict[int, TrackState] = OrderedDict()
        self.memory = MemoryEmitter()

        # Enrichment scheduler (off unless a budget is given)
        self.scheduler: EnrichmentScheduler | None = None
        self._first_seen_mono: dict[int, float] = {}
        self._track_enriched: Counter = Counter()
        self._label_enriched: Counter = Counter()
        self._prev_gray = None
        if enrich_budget_per_hour > 0:
            self.scheduler = EnrichmentScheduler(
                budget=TokenBucket(enrich_budget_per_hour, time.monotonic),
                scorer=SalienceScorer(self._familiarity),
                clock=time.monotonic,
            )

    def _familiarity(self, label: str) -> float:
        """Session-local novelty proxy: labels enriched often are familiar.

        Placeholder for the graph-backed novelty lookup (design doc step 2+):
        the real signal is class+place co-occurrence in relational memory.
        """
        return min(1.0, self._label_enriched[label] / 3.0)

    def _scene_motion(self, frame) -> float:
        """Cheap global-motion proxy: mean abs diff of downscaled gray frames."""
        gray = cv2.cvtColor(cv2.resize(frame, (64, 36)), cv2.COLOR_BGR2GRAY)
        if self._prev_gray is None:
            self._prev_gray = gray
            return 0.0
        diff = cv2.absdiff(gray, self._prev_gray)
        self._prev_gray = gray
        # ~8/255 mean diff is already heavy shake on a downscaled frame
        return min(1.0, float(diff.mean()) / 8.0)

    def run(self) -> int:
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            print(json.dumps({"type": "error", "message": "Camera could not be opened"}), flush=True)
            return 2

        frame_index = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    print(json.dumps({"type": "error", "message": "Camera frame read failed"}), flush=True)
                    return 3

                frame_index += 1
                if frame_index % self.frame_stride != 0:
                    continue

                self._process_frame(frame)
        except KeyboardInterrupt:
            return 0
        finally:
            cap.release()

    def run_image(self, image_path: str) -> int:
        frame = cv2.imread(image_path)
        if frame is None:
            print(json.dumps({"type": "error", "message": f"Image could not be opened: {image_path}"}), flush=True)
            return 2

        # Process the same image a few times so tracker-backed memory events can stabilize.
        for _ in range(4):
            self._process_frame(frame)
        return 0

    def _process_frame(self, frame) -> None:
        results = self.model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            verbose=False,
            conf=self.confidence,
        )
        if not results:
            return

        detections = self._detections_from_result(frame, results[0])
        active_tracks = self._update_tracks(detections)
        events = self.memory.events_from_tracks(active_tracks)

        payload = {
            "type": "perception_tick",
            "timestamp_utc": utc_now_iso(),
            "tracks": [
                {
                    "track_id": track.track_id,
                    "label": track.label,
                    "color": track.color,
                    "confidence": round(track.confidence, 3),
                    "seen_count": track.seen_count,
                    "frame_position": track.frame_position,
                    "area_ratio": round(track.area_ratio, 4),
                }
                for track in active_tracks
            ],
            "events": [
                {
                    "event_type": event.event_type,
                    "summary_text": event.summary_text,
                    "confidence": round(event.confidence, 3),
                    "category": event.category,
                    "data": event.data,
                }
                for event in events
            ],
        }
        print(json.dumps(payload), flush=True)

        if self.scheduler is not None:
            self._schedule_enrichment(frame, active_tracks)

    ENRICH_DIR = "/tmp/trace_enrich"

    def _save_enrichment_crop(self, frame, track: TrackState, decision) -> None:
        """Drop crop + sidecar for the enricher daemon (file-queue handoff)."""
        import os

        os.makedirs(self.ENRICH_DIR, exist_ok=True)
        x1, y1, x2, y2 = (int(v) for v in track.bbox_xyxy)
        h, w = frame.shape[:2]
        pad = 12
        crop = frame[max(0, y1 - pad):min(h, y2 + pad), max(0, x1 - pad):min(w, x2 + pad)]
        if crop.size == 0:
            crop = frame
        stem = f"{int(time.time() * 1000)}_{decision.track_id}_l{decision.level}"
        cv2.imwrite(f"{self.ENRICH_DIR}/{stem}.jpg", crop)
        sidecar = {
            "track_id": decision.track_id,
            "label": decision.class_name,
            "level": decision.level,
            "detail_focus": decision.detail_focus,
            "salience": round(decision.salience, 3),
            "frame_position": track.frame_position,
            "color": track.color,
            "captured_at": utc_now_iso(),
        }
        tmp = f"{self.ENRICH_DIR}/{stem}.json.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sidecar, f)
        os.replace(tmp, f"{self.ENRICH_DIR}/{stem}.json")

    def _schedule_enrichment(self, frame, active_tracks: list[TrackState]) -> None:
        motion = self._scene_motion(frame)
        now = time.monotonic()
        for track in active_tracks:
            first = self._first_seen_mono.setdefault(track.track_id, now)
            self.scheduler.observe(
                TrackView(
                    track_id=str(track.track_id),
                    class_name=track.label,
                    first_seen=first,
                    last_seen=now,
                    motion=motion,
                    enriched_count=self._track_enriched[track.track_id],
                )
            )
        decision = self.scheduler.next_enrichment()
        if decision is not None:
            self._track_enriched[int(decision.track_id)] = decision.level
            self._label_enriched[decision.class_name] += 1
            winner = next(
                (t for t in active_tracks if str(t.track_id) == decision.track_id), None
            )
            if winner is not None:
                self._save_enrichment_crop(frame, winner, decision)
            print(
                json.dumps(
                    {
                        "type": "enrichment_request",
                        "timestamp_utc": utc_now_iso(),
                        "track_id": decision.track_id,
                        "label": decision.class_name,
                        "level": decision.level,
                        "detail_focus": decision.detail_focus,
                        "salience": round(decision.salience, 3),
                        "stats": {
                            "enriched": self.scheduler.stats.enriched,
                            "budget_denied": self.scheduler.stats.budget_denied,
                            "below_threshold": self.scheduler.stats.below_threshold,
                            "evicted_stale": self.scheduler.stats.evicted_stale,
                        },
                    }
                ),
                flush=True,
            )

    def _detections_from_result(self, frame, result) -> list[Detection]:
        boxes = result.boxes
        if boxes is None:
            return []

        detections: list[Detection] = []
        names = result.names
        for index in range(len(boxes)):
            xyxy = tuple(float(v) for v in boxes.xyxy[index].tolist())
            conf = float(boxes.conf[index].item())
            cls_id = int(boxes.cls[index].item())
            track_id = None
            if boxes.id is not None:
                track_id = int(boxes.id[index].item())

            label = str(names.get(cls_id, cls_id))
            color = dominant_color_name(frame, xyxy)
            frame_position = self._frame_position(frame, xyxy)
            area_ratio = self._area_ratio(frame, xyxy)
            detections.append(
                Detection(
                    label=label,
                    confidence=conf,
                    bbox_xyxy=xyxy,
                    track_id=track_id,
                    color=color,
                    frame_position=frame_position,
                    area_ratio=area_ratio,
                )
            )
        return detections

    def _update_tracks(self, detections: list[Detection]) -> list[TrackState]:
        now = utc_now_iso()
        active: list[TrackState] = []
        for detection in detections:
            if detection.track_id is None:
                continue

            existing = self.tracks.get(detection.track_id)
            if existing is None:
                existing = TrackState(
                    track_id=detection.track_id,
                    label=detection.label,
                    color=detection.color,
                    confidence=detection.confidence,
                    bbox_xyxy=detection.bbox_xyxy,
                    first_seen_utc=now,
                    last_seen_utc=now,
                    frame_position=detection.frame_position,
                    area_ratio=detection.area_ratio,
                )
                self.tracks[detection.track_id] = existing
            else:
                existing.label = detection.label
                existing.color = detection.color
                existing.confidence = detection.confidence
                existing.bbox_xyxy = detection.bbox_xyxy
                existing.last_seen_utc = now
                existing.frame_position = detection.frame_position
                existing.area_ratio = detection.area_ratio
                existing.seen_count += 1

            active.append(existing)

        # Keep memory bounded.
        while len(self.tracks) > 200:
            self.tracks.popitem(last=False)

        return active

    def _frame_position(self, frame, bbox_xyxy: tuple[float, float, float, float]) -> str:
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = bbox_xyxy
        mid_x = ((x1 + x2) / 2) / max(1, width)
        mid_y = ((y1 + y2) / 2) / max(1, height)
        vertical = "upper" if mid_y < 0.33 else "lower" if mid_y > 0.66 else "middle"
        horizontal = "left" if mid_x < 0.33 else "right" if mid_x > 0.66 else "center"
        return f"{vertical} {horizontal} frame"

    def _area_ratio(self, frame, bbox_xyxy: tuple[float, float, float, float]) -> float:
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = bbox_xyxy
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        return area / max(1.0, float(width * height))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run TRACE detector/tracker perception worker.")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--frame-stride", type=int, default=8)
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--image", help="Process one image file instead of opening a camera")
    parser.add_argument(
        "--enrich-budget", type=float, default=0.0,
        help="VLM enrichments per hour (0 = scheduler off)",
    )
    args = parser.parse_args(argv)

    worker = PerceptionWorker(
        camera_index=args.camera,
        model_name=args.model,
        frame_stride=args.frame_stride,
        confidence=args.confidence,
        enrich_budget_per_hour=args.enrich_budget,
    )
    if args.image:
        return worker.run_image(args.image)

    return worker.run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
