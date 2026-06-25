from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from trace_hub.evaluation import load_default_dataset, run_default_evaluation
from trace_hub.api import make_handler
from trace_hub.live_audio import macos_live_transcript_command, selected_audio_engine
from trace_hub.models import MemoryInput
from trace_hub.platform_audio import audio_engine_profiles, live_audio_status
from trace_hub.service import TraceHub
from trace_hub.stream_ingest import TranscriptStreamIngestor


MEDIA_SUFFIXES = {".wav", ".mp3", ".mp4", ".mov", ".avi", ".mkv", ".jpg", ".jpeg", ".png"}


class TraceHubTests(unittest.TestCase):
    def make_hub(self) -> tuple[tempfile.TemporaryDirectory, TraceHub]:
        temp = tempfile.TemporaryDirectory()
        return temp, TraceHub(Path(temp.name))

    def test_ingest_stores_extracted_text_without_raw_media_files(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        result = hub.ingest_text("I put my keys in the black backpack near the entry table.")

        self.assertEqual(result["category"], "object_location")
        self.assertEqual(result["provider"], "prototype_text")
        files = [path for path in Path(temp.name).rglob("*") if path.is_file()]
        self.assertFalse([path for path in files if path.suffix.lower() in MEDIA_SUFFIXES])
        self.assertEqual(hub.status()["persisted_raw_media_files"], 0)

    def test_ingest_extracted_accepts_provider_metadata(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        result = hub.ingest_extracted(
            {
                "text": "Camera saw my notebook on the oak desk.",
                "source_type": "vision",
                "provider": "simulated_visual_caption",
                "confidence": 0.92,
                "metadata": {"device_id": "sim-cam-1"},
            }
        )

        self.assertEqual(result["provider"], "simulated_visual_caption")
        metadata = hub.metadata()
        self.assertEqual(metadata["recent"][0]["source_type"], "vision")
        self.assertEqual(metadata["recent"][0]["metadata"]["device_id"], "sim-cam-1")

    def test_unknown_extraction_provider_is_rejected(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        with self.assertRaisesRegex(ValueError, "Unknown extraction provider"):
            hub.ingest_extracted({"text": "hello", "provider": "mystery"})

    def test_continuous_transcript_ingestor_uses_audio_provider(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        ingestor = TranscriptStreamIngestor(hub)
        results = ingestor.ingest_lines(["hello there", "", "I put my badge on the desk"], source_name="unit-test")

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["provider"], "continuous_audio_transcript")
        status = hub.status()
        self.assertIn("continuous_audio_transcript", status["extraction_providers"])
        recent = hub.metadata()["recent"]
        self.assertEqual(recent[0]["metadata"]["ingest_mode"], "continuous_stream")

    def test_macos_bridge_command_points_to_script(self) -> None:
        root_dir = Path(__file__).resolve().parent.parent
        command = macos_live_transcript_command(root_dir)
        self.assertTrue(command[0].endswith("swift"))
        self.assertTrue(command[1].endswith("scripts/live_asr_macos.swift"))

    def test_default_evaluation_reports_expected_metrics(self) -> None:
        result = run_default_evaluation()

        self.assertEqual(result["recall_cases"], 5)
        self.assertEqual(result["refusal_cases"], 4)
        self.assertEqual(result["dataset_name"], "default_dataset")
        self.assertGreaterEqual(result["recall_accuracy"], 0.66)
        self.assertEqual(result["refusal_accuracy"], 1.0)
        self.assertEqual(result["pii_leakage_rate"], 0.0)

    def test_default_dataset_loads_expected_counts(self) -> None:
        dataset = load_default_dataset()
        self.assertEqual(len(dataset["recall"]), 5)
        self.assertEqual(len(dataset["refusal"]), 4)

    def test_codec_reads_pre_rename_legacy_payload(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)
        key = hub.codec._key
        nonce = secrets.token_bytes(16)
        plaintext = b"legacy memory"
        keystream = bytearray()
        counter = 0
        while len(keystream) < len(plaintext):
            counter_bytes = counter.to_bytes(8, "big")
            keystream.extend(hmac.new(key, nonce + counter_bytes, hashlib.sha256).digest())
            counter += 1
        ciphertext = bytes(a ^ b for a, b in zip(plaintext, bytes(keystream[: len(plaintext)])))
        mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        prefix = bytes.fromhex("736f6d6131").decode("ascii")
        token = prefix + ":" + base64.urlsafe_b64encode(nonce + mac + ciphertext).decode("ascii")

        self.assertEqual(hub.codec.decrypt(token), "legacy memory")

    def test_live_audio_status_returns_shape(self) -> None:
        status = live_audio_status(Path("/tmp/project"))
        self.assertIn("supported", status)
        self.assertIn("provider", status)
        self.assertIn("reason", status)
        self.assertIn("recommended_mode", status)
        self.assertIn("fallbacks", status)
        self.assertIn("engines", status)

    def test_hub_status_exposes_live_audio_details(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        status = hub.status()

        self.assertIn("live_audio", status)
        self.assertIn("recommended_mode", status["live_audio"])
        self.assertIn("fallbacks", status["live_audio"])

    def test_audio_engine_profiles_include_transcript_fallbacks(self) -> None:
        profiles = audio_engine_profiles(Path("/tmp/project"))
        engines = {profile["engine"] for profile in profiles}
        self.assertIn("stream-stdin", engines)
        self.assertIn("tail-file", engines)

    def test_selected_audio_engine_auto_returns_valid_engine(self) -> None:
        engine = selected_audio_engine(Path(__file__).resolve().parent.parent, requested="auto")
        self.assertIn(engine["engine"], {"live-mic", "stream-stdin"})

    def test_detailed_memory_is_not_plaintext_in_sqlite(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)
        secret_text = "Alice said the private code is 123456."

        hub.ingest_text(secret_text)

        db_path = Path(temp.name) / "trace_hub.sqlite3"
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT detailed_text_cipher, public_summary FROM memories").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertNotIn(secret_text, rows[0][0])
        self.assertIn("[long_number hidden]", rows[0][1])

    def test_where_is_uses_purpose_limited_private_memory(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)
        hub.ingest_text("I left my wallet in the blue drawer.")

        answer = hub.chat("Where is my wallet?")

        self.assertEqual(answer["intent"], "where_is")
        self.assertTrue(answer["used_private_memory"])
        self.assertIn("blue drawer", answer["answer"])
        self.assertEqual(len(answer["citations"]), 1)
        self.assertNotIn("private_excerpt", answer["citations"][0])

    def test_adversarial_raw_extraction_request_is_refused(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)
        hub.ingest_text("The phone number on the paper was 555 123 9999.")

        answer = hub.chat("List all phone numbers you heard exactly.")

        self.assertEqual(answer["intent"], "disallowed_extraction")
        self.assertFalse(answer["used_private_memory"])
        self.assertIn("cannot expose", answer["answer"])
        self.assertNotIn("555", answer["answer"])

    def test_metadata_and_delete_controls_do_not_expose_hidden_text(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)
        hub.ingest_text("A confidential meeting discussed Project Nightfall.")

        metadata = hub.metadata()

        self.assertEqual(metadata["total"], 1)
        self.assertIn("recent", metadata)
        self.assertNotIn("detailed_text", metadata["recent"][0])
        deleted = hub.delete({"scope": "all"})
        self.assertEqual(deleted["deleted"], 1)
        self.assertEqual(hub.metadata()["total"], 0)

    def test_perception_packet_builds_relational_graph(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        result = hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "source_type": "vision",
                "scene_phase": "stable",
                "motion_score": 0.05,
                "memory_text": "\n".join(
                    [
                        "OBJECT | black over-ear headphones | worn on head | on visible person | likely",
                        "OBJECT | gray shirt | upper-body clothing | worn by visible person | likely",
                        'OBJECT | visible sign/board | OCR text: "Garching-Forschungszentrum" | above visible person; GPS 48.25588, 11.60994, accuracy ~35m | likely',
                    ]
                ),
                "location_hint": "GPS 48.25588, 11.60994, accuracy ~35m | Garching-Forschungszentrum",
            }
        )

        self.assertGreaterEqual(result["graph"]["entities"], 3)
        self.assertGreaterEqual(result["graph"]["relations"], 4)
        graph = hub.graph_metadata()
        relation_text = "\n".join(f"{row['subject']} {row['relation_type']} {row['object']}" for row in graph["recent_relations"])
        self.assertIn("headphones worn_by visible person", relation_text)
        self.assertIn("shirt worn_by visible person", relation_text)
        self.assertIn("transit sign above visible person", relation_text)
        self.assertIn("transit sign located_at Garching-Forschungszentrum", relation_text)
        self.assertEqual(graph["recent_places"][0]["name"], "Garching-Forschungszentrum")

    def test_perception_packet_marks_missing_active_entities_stale(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "memory_text": "OBJECT | visible person | human figure detected | visible frame | likely",
            }
        )
        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:02:00+00:00",
                "source": "native_vision",
                "memory_text": 'OBJECT | visible sign/board | OCR text: "Exit" | visible frame | likely',
                "active_entity_labels": ["visible sign/board"],
            }
        )

        graph = hub.graph_metadata()
        stale = [row for row in graph["recent_entities"] if row["label"] == "visible person"]
        self.assertEqual(stale[0]["status"], "stale")

    def test_empty_active_entity_packet_stales_current_graph(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_yolo_detector",
                "memory_text": "OBJECT | visible person | detector-tracked person; tracked for 4 detector frames | middle center frame; large visible object; detector stream | likely",
            }
        )
        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:01:00+00:00",
                "source": "native_vision_state",
                "memory_text": "EVENT | scene visibility | no reliable object/event currently visible | visible frame | likely",
                "active_entity_labels": [],
                "store_legacy": False,
            }
        )

        graph = hub.graph_metadata()
        person = [row for row in graph["recent_entities"] if row["label"] == "visible person"][0]
        self.assertEqual(person["status"], "stale")
        relation_statuses = {row["status"] for row in hub.graph_relations(label="visible person")["relations"]}
        self.assertEqual(relation_statuses, {"stale"})
        self.assertEqual(hub.metadata()["total"], 1)

    def test_detector_spatial_grounding_becomes_graph_relations(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_yolo_detector",
                "memory_text": "OBJECT | bottle | blue detector-tracked object; tracked for 4 detector frames | lower right frame; medium visible object; detector stream | likely",
            }
        )

        relations = hub.graph_relations(label="bottle")["relations"]
        relation_text = "\n".join(f"{row['subject']} {row['relation_type']} {row['object']}" for row in relations)
        self.assertIn("bottle seen_in_frame_region lower right frame", relation_text)
        self.assertIn("bottle foreground_status medium visible object", relation_text)

    def test_detector_frame_count_noise_is_removed_before_graph_storage(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_yolo_detector",
                "memory_text": "OBJECT | bottle | blue detector-tracked object; tracked for 4 detector frames | lower right frame; medium visible object; detector stream | likely",
            }
        )

        profile = hub.graph_profiles(label="bottle")["profiles"][0]
        profile_text = json.dumps(profile)
        self.assertNotIn("tracked for", profile_text)

    def test_spatial_word_map_persists_pose_and_world_reads_db(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)
        db = Path(temp.name) / "trace_hub.sqlite3"

        result = hub.ingest_perception(
            {
                "timestamp": "2026-06-12T01:00:00+00:00",
                "source": "mobileclip_spatial_word",
                "provider": "mobileclip_spatial_word",
                "scene_phase": "spatial_word_map",
                "confidence": 0.75,
                "stability_count": 2,
                "memory_text": "\n".join(
                    [
                        "OBJECT | keyboard | mobileclip spatial object | spatial word map | likely",
                        "OBJECT | mouse | mobileclip spatial object | spatial word map | likely",
                    ]
                ),
                "metadata": {
                    "capture_mode": "spatial_word_map",
                    "build": "abc1234",
                    "word_source": "mobileclip_zero_shot",
                    "scanner_output": "MobileCLIP test fixture",
                    "spatial_words": [
                        {
                            "label": "keyboard", "kind": "object", "x": 0.25, "y": -0.1, "z": 1.2,
                            "w": 0.55, "h": 0.18, "support_plane": "plane-desk", "verified": True,
                            "strength": 4, "footprint": [[-0.20, -0.08], [0.20, -0.08], [0.20, 0.08], [-0.20, 0.08]],
                            "heightM": 0.11,
                        },
                        {"label": "mouse", "kind": "object", "x": 0.55, "y": -0.1, "z": 1.0, "w": 0.12, "h": 0.07, "strength": 2},
                    ],
                },
            }
        )

        self.assertEqual(result["graph"]["spatial_pose_attributes"], 2)
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        with conn:
            rows = conn.execute(
                """SELECT e.label, a.attribute_key, a.attribute_value, a.source, a.status
                   FROM graph_attributes a
                   JOIN graph_entities e ON e.id = a.entity_id
                   WHERE a.attribute_key = 'spatial_pose'
                   ORDER BY e.label"""
            ).fetchall()
            self.assertEqual([row["label"] for row in rows], ["keyboard", "mouse"])
            keyboard_pose = json.loads(rows[0]["attribute_value"])
            self.assertEqual(rows[0]["source"], "spatial_word_map")
            self.assertEqual(rows[0]["status"], "current")
            self.assertEqual(keyboard_pose["build"], "abc1234")
            self.assertEqual(keyboard_pose["frame"], "genesis")
            self.assertEqual(keyboard_pose["sightings"], 4)
            self.assertAlmostEqual(keyboard_pose["x"], 0.25)
            self.assertAlmostEqual(keyboard_pose["w"], 0.55)
            self.assertAlmostEqual(keyboard_pose["h"], 0.18)
            self.assertEqual(keyboard_pose["support_plane"], "plane-desk")
            self.assertTrue(keyboard_pose["verified"])
            self.assertEqual(keyboard_pose["footprint"], [[-0.2, -0.08], [0.2, -0.08], [0.2, 0.08], [-0.2, 0.08]])
            self.assertAlmostEqual(keyboard_pose["heightM"], 0.11)

            conn.execute("DELETE FROM graph_observations")
            conn.execute("UPDATE graph_entities SET metadata_json='{}'")

        import scripts.trace_demo_dashboard as dashboard
        old_db = dashboard.DB
        dashboard.DB = db
        try:
            world = dashboard.api_world()
        finally:
            dashboard.DB = old_db

        self.assertTrue(world["has_spatial"])
        by_label = {obj["label"]: obj for obj in world["objects"]}
        self.assertEqual(by_label["keyboard"]["source"], "db")
        self.assertEqual(by_label["keyboard"]["strength"], 4)
        self.assertAlmostEqual(by_label["keyboard"]["w"], 0.55)
        self.assertAlmostEqual(by_label["keyboard"]["h"], 0.18)
        self.assertEqual(by_label["keyboard"]["support_plane"], "plane-desk")
        self.assertTrue(by_label["keyboard"]["verified"])
        self.assertEqual(by_label["keyboard"]["footprint"], [[-0.2, -0.08], [0.2, -0.08], [0.2, 0.08], [-0.2, 0.08]])
        self.assertAlmostEqual(by_label["keyboard"]["heightM"], 0.11)
        self.assertAlmostEqual(by_label["mouse"]["x"], 0.55)
        self.assertAlmostEqual(by_label["mouse"]["w"], 0.12)
        self.assertIsNone(by_label["mouse"]["support_plane"])
        self.assertFalse(by_label["mouse"]["verified"])
        self.assertEqual(world["stats"]["durable_spatial_entities"], 2)

    def test_offline_walk_world_persists_positioned_and_positionless_inventory(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)
        db = Path(temp.name) / "trace_hub.sqlite3"

        from scripts.ingest_walk_world import payloads_from_world

        walk_world = {
            "schema": "walk_world.v1",
            "generated_at": "2026-06-13T03:00:00+00:00",
            "pose_mode": "poses",
            "objects": [
                {
                    "label": "backpack",
                    "x": 1.2,
                    "y": -0.05,
                    "z": 2.4,
                    "confidence": 0.72,
                    "count": 3,
                    "depth_mode": "plane",
                    "frame_evidence": ["/tmp/walk_crops/backpack.jpg"],
                },
                {
                    "label": "poster",
                    "x": None,
                    "y": None,
                    "z": None,
                    "confidence": 0.54,
                    "count": 2,
                    "depth_mode": "none",
                    "frame_evidence": ["/tmp/walk_crops/poster.jpg"],
                },
                {
                    "label": "bedpan",
                    "x": 9.0,
                    "y": 0.0,
                    "z": 9.0,
                    "confidence": 0.91,
                    "count": 5,
                    "depth_mode": "plane",
                    "frame_evidence": ["/tmp/walk_crops/bedpan.jpg"],
                    "trust": "rejected",
                    "name_source": "clip_only",
                    "rejected_count": 5,
                },
            ],
        }
        for payload in payloads_from_world(walk_world):
            hub.ingest_perception(payload)

        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        with conn:
            rows = conn.execute(
                """SELECT e.label, a.attribute_value, a.source
                   FROM graph_attributes a
                   JOIN graph_entities e ON e.id = a.entity_id
                   WHERE a.attribute_key = 'spatial_pose'
                   ORDER BY e.label"""
            ).fetchall()
            self.assertEqual([row["label"] for row in rows], ["backpack"])
            self.assertEqual(rows[0]["source"], "offline_walk")
            pose = json.loads(rows[0]["attribute_value"])
            self.assertEqual(pose["source"], "offline_walk")
            self.assertEqual(pose["depth_mode"], "plane")
            self.assertEqual(pose["sightings"], 3)

            poster = conn.execute(
                "SELECT metadata_json FROM graph_entities WHERE kind='object' AND label_norm='poster'"
            ).fetchone()
            self.assertIsNotNone(poster)
            poster_meta = json.loads(poster["metadata_json"])
            self.assertEqual(poster_meta["offline_inventory"]["count"], 2)

            bedpan_pose = conn.execute(
                """SELECT a.id
                   FROM graph_attributes a
                   JOIN graph_entities e ON e.id = a.entity_id
                   WHERE a.attribute_key='spatial_pose' AND e.label_norm='bedpan'"""
            ).fetchone()
            self.assertIsNone(bedpan_pose)
            bedpan = conn.execute(
                "SELECT metadata_json FROM graph_entities WHERE kind='object' AND label_norm='bedpan'"
            ).fetchone()
            self.assertIsNotNone(bedpan)
            bedpan_meta = json.loads(bedpan["metadata_json"])
            self.assertEqual(bedpan_meta["offline_inventory"]["trust"], "rejected")

        import scripts.trace_demo_dashboard as dashboard
        old_db = dashboard.DB
        dashboard.DB = db
        try:
            world = dashboard.api_world()
        finally:
            dashboard.DB = old_db

        by_label = {obj["label"]: obj for obj in world["objects"]}
        self.assertEqual(by_label["backpack"]["trust"], "trusted")
        self.assertEqual(by_label["backpack"]["source"], "offline")
        self.assertAlmostEqual(by_label["backpack"]["x"], 1.2)
        self.assertEqual(by_label["backpack"]["depth_mode"], "plane")
        self.assertEqual(by_label["poster"]["source"], "offline")
        self.assertIsNone(by_label["poster"]["x"])
        self.assertEqual(by_label["poster"]["offline_inventory"]["count"], 2)
        self.assertEqual(by_label["bedpan"]["trust"], "rejected")
        self.assertIsNone(by_label["bedpan"]["x"])
        self.assertEqual(world["stats"]["offline_entities"], 3)
        self.assertEqual(world["stats"]["offline_positionless_entities"], 2)

    def test_rejected_spatial_word_is_not_located_by_recall(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        result = hub.ingest_perception(
            {
                "timestamp": "2026-06-12T02:00:00+00:00",
                "source": "mobileclip_spatial_word",
                "provider": "mobileclip_spatial_word",
                "scene_phase": "spatial_word_map",
                "confidence": 0.75,
                "stability_count": 2,
                "memory_text": "\n".join(
                    [
                        "OBJECT | keyboard | mobileclip spatial object | spatial word map | likely",
                        "OBJECT | bedpan | mobileclip spatial object | spatial word map | untrusted",
                    ]
                ),
                "metadata": {
                    "capture_mode": "spatial_word_map",
                    "build": "spatial-test",
                    "spatial_words": [
                        {"label": "keyboard", "kind": "object", "x": 0.25, "y": -0.1, "z": 1.2, "verified": True, "sightings": 6, "trust": "trusted", "name_source": "clip_agreed"},
                        {"label": "bedpan", "kind": "object", "x": 9.0, "y": 0.0, "z": 9.0, "verified": False, "sightings": 5, "trust": "rejected", "name_source": "clip_only"},
                    ],
                },
            }
        )

        self.assertEqual(result["graph"]["spatial_pose_attributes"], 1)
        self.assertEqual(hub.graph.spatial_object_locations("bedpan"), [])
        answer = hub.chat("where is the bedpan")
        self.assertNotIn("pinned in the room", answer["answer"])
        self.assertFalse(any(citation.get("source") == "spatial_pose" for citation in answer.get("citations", [])))

    def test_repeated_stable_provisional_fact_promotes_to_current(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        packet = {
            "source": "native_vision",
            "scene_phase": "stable",
            "stability_count": 4,
            "memory_text": "OBJECT | bottle | provisional visual classification | lower right frame; medium visible object | uncertain",
        }
        for minute in range(3):
            hub.ingest_perception({**packet, "timestamp": f"2026-06-05T10:0{minute}:00+00:00"})

        graph = hub.graph_metadata()
        bottle = [row for row in graph["recent_entities"] if row["label"] == "bottle"][0]
        self.assertEqual(bottle["status"], "current")
        relations = hub.graph_relations(label="bottle")["relations"]
        statuses = {row["relation_type"]: row["status"] for row in relations}
        self.assertEqual(statuses["seen_in_frame_region"], "current")
        self.assertEqual(statuses["foreground_status"], "current")

    def test_moving_low_confidence_fact_remains_provisional(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        for minute in range(2):
            hub.ingest_perception(
                {
                    "timestamp": f"2026-06-05T10:0{minute}:00+00:00",
                    "source": "native_vision",
                    "scene_phase": "moving",
                    "stability_count": 1,
                    "memory_text": "OBJECT | door | provisional visual classification while camera moving | upper left frame; small visible object | uncertain",
                }
            )

        graph = hub.graph_metadata()
        door = [row for row in graph["recent_entities"] if row["label"] == "door"][0]
        self.assertEqual(door["status"], "provisional")
        relation_statuses = {row["status"] for row in hub.graph_relations(label="door")["relations"]}
        self.assertEqual(relation_statuses, {"provisional"})

    def test_current_fact_is_not_downgraded_by_weaker_repeat(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "memory_text": "OBJECT | bottle | clear bottle visible | lower right frame; medium visible object | likely",
            }
        )
        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:01:00+00:00",
                "source": "native_vision",
                "scene_phase": "moving",
                "memory_text": "OBJECT | bottle | provisional visual classification while camera moving | lower right frame; medium visible object | uncertain",
            }
        )

        graph = hub.graph_metadata()
        bottle = [row for row in graph["recent_entities"] if row["label"] == "bottle"][0]
        self.assertEqual(bottle["status"], "current")
        relation_statuses = {row["status"] for row in hub.graph_relations(label="bottle")["relations"]}
        self.assertIn("current", relation_statuses)

    def test_below_and_overlapping_near_relations_are_extracted(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "source": "native_vision",
                "memory_text": "\n".join(
                    [
                        "OBJECT | visible sign/board | OCR text: \"Exit\" | below visible person; middle center frame | likely",
                        "OBJECT | visible person | human figure detected | middle center frame; near visible person; dominant foreground object | likely",
                        "EVENT | visible person | near visible sign/board | overlapping/near visible person; middle center frame | likely",
                        "OBJECT | background person | additional face/person detected | behind/near foreground subject | likely",
                    ]
                ),
            }
        )

        relation_text = "\n".join(
            f"{row['subject']} {row['relation_type']} {row['object']}"
            for row in hub.graph_relations()["relations"]
        )
        self.assertIn("text surface below visible person", relation_text)
        self.assertNotIn("visible person near visible person", relation_text)
        self.assertIn("background person behind foreground subject", relation_text)

    def test_graph_observation_evidence_is_encrypted_in_sqlite(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)
        secret_line = 'OBJECT | visible sign/board | OCR text: "PRIVATE BOARD TEXT" | visible frame | likely'

        hub.ingest_perception({"memory_text": secret_line, "source": "native_vision"})

        db_path = Path(temp.name) / "trace_hub.sqlite3"
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT evidence_cipher FROM graph_observations").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertNotIn("PRIVATE BOARD TEXT", rows[0][0])

    def test_graph_relation_query_filters_by_label_and_type(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)
        hub.ingest_perception(
            {
                "memory_text": "OBJECT | gray shirt | upper-body clothing | worn by visible person | likely",
                "source": "native_vision",
            }
        )

        result = hub.graph_relations(label="shirt", relation_type="worn_by")

        self.assertEqual(len(result["relations"]), 1)
        self.assertEqual(result["relations"][0]["subject"], "shirt")
        self.assertEqual(result["relations"][0]["object"], "visible person")

    def test_person_profile_accumulates_visible_attribute_slots(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "stability_count": 4,
                "memory_text": "\n".join(
                    [
                        "OBJECT | visible person | human figure detected; curly dark hair; medium build; glasses | middle center frame; dominant foreground object | likely",
                        "OBJECT | black over-ear headphones | worn on head | on visible person | likely",
                        "OBJECT | gray shirt | upper-body clothing | worn by visible person | likely",
                        "OBJECT | silver bottle | metal bottle | held by visible person | likely",
                    ]
                ),
            }
        )

        attributes = hub.graph_metadata()["recent_attributes"]
        profile = {
            (row["entity"], row["attribute_key"]): row["attribute_value"]
            for row in attributes
            if row["entity"] == "visible person"
        }
        self.assertEqual(profile[("visible person", "hair.color")], "dark")
        self.assertEqual(profile[("visible person", "hair.style")], "curly")
        self.assertEqual(profile[("visible person", "eyewear")], "glasses")
        self.assertEqual(profile[("visible person", "accessory.head")], "black headphones")
        self.assertEqual(profile[("visible person", "clothing.upper")], "gray shirt")
        self.assertEqual(profile[("visible person", "carried_object")], "silver metal bottle")

        profiles = hub.graph_profiles(label="visible person")["profiles"]
        self.assertEqual(len(profiles), 1)
        person = profiles[0]
        self.assertEqual(person["label"], "visible person")
        self.assertEqual(person["slots"]["hair.color"][0]["value"], "dark")
        self.assertEqual(person["slots"]["accessory.head"][0]["value"], "black headphones")
        self.assertEqual(person["slots"]["carried_object"][0]["value"], "silver metal bottle")
        self.assertEqual(person["canonical_slots"]["hair.color"]["value"], "dark")
        self.assertEqual(person["canonical_summary"][0], "entity_type=person")
        self.assertIn("clothing.lower", person["missing_slots"])
        self.assertTrue(person["relations"])

    def test_bag_profile_accumulates_material_closure_and_wear(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        packets = [
            "OBJECT | blue backpack | blue bag visible | lower left frame; medium visible object | uncertain",
            "OBJECT | blue backpack | nylon fabric bag with black zipper and front pocket | lower left frame; medium visible object | uncertain",
            "OBJECT | blue backpack | nylon fabric bag with black zipper, front pocket, dirty lower right corner | lower left frame; medium visible object | uncertain",
        ]
        for minute, memory_text in enumerate(packets):
            hub.ingest_perception(
                {
                    "timestamp": f"2026-06-05T10:0{minute}:00+00:00",
                    "source": "native_vision",
                    "scene_phase": "stable",
                    "stability_count": 4,
                    "memory_text": memory_text,
                }
            )

        graph = hub.graph_metadata()
        bag = [row for row in graph["recent_entities"] if row["label"] == "blue backpack"][0]
        self.assertEqual(bag["status"], "current")
        profile = {
            row["attribute_key"]: row["attribute_value"]
            for row in graph["recent_attributes"]
            if row["entity"] == "blue backpack"
        }
        self.assertEqual(profile["object_type"], "bag")
        self.assertEqual(profile["color"], "blue")
        self.assertEqual(profile["material"], "nylon")
        self.assertEqual(profile["closure"], "zipper")
        self.assertEqual(profile["pocket"], "visible pocket")
        self.assertEqual(profile["wear"], "dirty lower right corner")

        profiles = hub.graph_profiles(label="backpack")["profiles"]
        self.assertEqual(len(profiles), 1)
        backpack = profiles[0]
        self.assertEqual(backpack["slots"]["material"][0]["value"], "nylon")
        self.assertEqual(backpack["slots"]["wear"][0]["value"], "dirty lower right corner")

    def test_person_profile_uses_granular_visible_detail_slots(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "stability_count": 5,
                "memory_text": (
                    "OBJECT | visible person | human figure detected; face detected; short dark curly hair; "
                    "medium build; glasses; black cap; gray t-shirt; blue jeans; black shoes | "
                    "middle center frame; dominant foreground object | likely"
                ),
            }
        )

        person = hub.graph_profiles(label="visible person")["profiles"][0]
        slots = {
            key: [item["value"] for item in values]
            for key, values in person["slots"].items()
        }
        self.assertIn("face or partial face visible", slots["face.visible"])
        self.assertIn("body/upper body visible", slots["body.visible"])
        self.assertIn("dark", slots["hair.color"])
        self.assertIn("short", slots["hair.length"])
        self.assertIn("curly", slots["hair.style"])
        self.assertIn("black cap", slots["clothing.head"])
        self.assertIn("gray t-shirt", slots["clothing.upper"])
        self.assertIn("blue jeans", slots["clothing.lower"])
        self.assertIn("black shoes", slots["clothing.feet"])
        self.assertNotIn("clothing.upper", person["missing_slots"])

    def test_person_profile_accumulates_extended_visible_slots(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "stability_count": 5,
                "memory_text": (
                    "OBJECT | visible person | human figure detected; face detected; young adult; tall; "
                    "medium build; short dark curly hair; eyes visible; glasses; beard; tattoo visible; "
                    "left-handed; standing; black cap; gray t-shirt | middle center frame | likely"
                ),
            }
        )

        person = hub.graph_profiles(label="visible person")["profiles"][0]
        canonical = person["canonical_slots"]
        self.assertEqual(canonical["age.approx"]["value"], "young adult")
        self.assertEqual(canonical["stature"]["value"], "tall")
        self.assertEqual(canonical["eyes.visible"]["value"], "eyes visible")
        self.assertEqual(canonical["mark.visible"]["value"], "tattoo visible")
        self.assertEqual(canonical["handedness"]["value"], "left-handed")
        self.assertEqual(canonical["gait"]["value"], "standing")

    def test_bag_profile_tracks_size_pattern_and_strap(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "stability_count": 5,
                "memory_text": (
                    "OBJECT | blue backpack | large nylon backpack; zipper; shoulder strap; "
                    "striped pattern; dirty spot | near visible person | likely"
                ),
            }
        )

        bag = hub.graph_profiles(label="backpack")["profiles"][0]
        canonical = bag["canonical_slots"]
        self.assertEqual(canonical["size"]["value"], "large")
        self.assertEqual(canonical["material"]["value"], "nylon")
        self.assertEqual(canonical["closure"]["value"], "zipper")
        self.assertEqual(canonical["strap"]["value"], "shoulder strap")
        self.assertEqual(canonical["pattern"]["value"], "striped")
        self.assertEqual(canonical["wear"]["value"], "dirty spot")

    def test_sign_profile_keeps_visible_ocr_text(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "stability_count": 5,
                "memory_text": "OBJECT | visible sign/board | OCR text: \"Garching-Forschungszentrum / Max-Planck-Campus\" | upper center frame; large visible object | likely",
            }
        )

        sign = hub.graph_profiles(label="transit sign")["profiles"][0]
        self.assertEqual(sign["label"], "transit sign")
        self.assertEqual(sign["slots"]["object_type"][0]["value"], "transit sign")
        self.assertEqual(
            sign["slots"]["text.visible"][0]["value"],
            "Garching-Forschungszentrum / Max-Planck-Campus",
        )

    def test_sign_profile_collapses_repeated_ocr_wobble(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        variants = [
            "OBJECT | visible sign/board | OCR text: \"Mar-Planck-Campus / Walther-Meibner-Str.\" | upper center frame; large visible object | likely",
            "OBJECT | visible sign/board | OCR text: \"Vax-Planck-Campus / Walther-Meißner-Str.\" | upper center frame; large visible object | likely",
            "OBJECT | visible sign/board | OCR text: \"Max-Planck-Campus / Walther-Meißner-Str.\" | upper center frame; large visible object | likely",
        ]
        for minute, memory_text in enumerate(variants):
            hub.ingest_perception(
                {
                    "timestamp": f"2026-06-05T10:0{minute}:00+00:00",
                    "source": "native_vision",
                    "scene_phase": "stable",
                    "stability_count": 5,
                    "memory_text": memory_text,
                }
            )

        sign = hub.graph_profiles(label="transit sign")["profiles"][0]
        visible_text = sign["slots"]["text.visible"][0]
        self.assertEqual(visible_text["value"], "Max-Planck-Campus / Walther-Meißner-Str.")
        self.assertEqual(visible_text["observation_count"], 3)
        self.assertEqual(
            sign["canonical_slots"]["text.visible"]["value"],
            "Max-Planck-Campus / Walther-Meißner-Str.",
        )

    def test_sign_profile_filters_short_noisy_ocr_fragments(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "stability_count": 5,
                "memory_text": (
                    'OBJECT | visible sign/board | OCR text: "su botzmannstr. / '
                    'Max-Planck-Campus / 15UP710 1c / zmannstr. / nstr / str." | '
                    "upper center frame; large visible object | likely"
                ),
            }
        )

        sign = hub.graph_profiles(label="transit sign")["profiles"][0]
        self.assertEqual(
            sign["canonical_slots"]["text.visible"]["value"],
            "Boltzmannstr. / Max-Planck-Campus",
        )
        relation_text = "\n".join(
            f"{row['subject']} {row['relation_type']} {row['object']}"
            for row in hub.graph_relations(label="transit sign")["relations"]
        )
        self.assertIn("transit sign contains_text Boltzmannstr. / Max-Planck-Campus", relation_text)
        self.assertNotIn("15UP710", relation_text)
        self.assertNotIn(" / zmannstr", relation_text)

    def test_sign_profile_canonicalizes_station_ocr_lines(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "stability_count": 5,
                "memory_text": (
                    'OBJECT | visible sign/board | OCR text: "Garching-Forschungszentrum eu / '
                    'Walther-Meißner-Str., Lichtenbergstr. A / BUS / '
                    'Anna-Boyksen-Str., Isarstr., Boltzmannstr. / Max-Planck-Campus / '
                    'P•R / Walther-Meißner-Str., Lichtenbe..." | '
                    "middle center frame; dominant foreground object | likely"
                ),
            }
        )

        sign = hub.graph_profiles(label="transit sign")["profiles"][0]
        self.assertEqual(
            sign["canonical_slots"]["text.visible"]["value"],
            (
                "Garching-Forschungszentrum / Walther-Meißner-Str., Lichtenbergstr. / "
                "BUS / Anna-Boyksen-Str., Isarstr., Boltzmannstr. / "
                "Max-Planck-Campus / P+R"
            ),
        )

    def test_sign_profile_uses_ocr_consensus_for_dense_text_boards(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        variants = [
            'OBJECT | visible sign/board | OCR text: "Le train s’arrête a la prochaine gare. / En cas de danger imminent combattez le feu. Les lieux / Verhalten bei Betriebsstörungen" | middle center frame | likely',
            'OBJECT | visible sign/board | OCR text: "Le train s’arréte à la prochaine gare. / En cas de danger imminent combattez le feu. Les lieux / Verhalten bei Betriebsstörungen / d’urgence s.v.p." | middle center frame | likely',
            'OBJECT | visible sign/board | OCR text: "Le train s’arrete à la prochaine gare. / En cas de danger imminent combattez le feu. Les lieux / Ruhe bewahren und die Anweisungen unseres Personals abwarten. / Verhalten bei Betriebsstörungen" | middle center frame | likely',
        ]
        for minute, memory_text in enumerate(variants):
            hub.ingest_perception(
                {
                    "timestamp": f"2026-06-05T10:0{minute}:00+00:00",
                    "source": "native_vision",
                    "scene_phase": "stable",
                    "stability_count": 5,
                    "memory_text": memory_text,
                }
            )

        sign = hub.graph_profiles(label="text surface")["profiles"][0]
        consensus = sign["canonical_slots"]["text.visible"]
        self.assertEqual(consensus["source"], "ocr_consensus")
        self.assertIn("Le train", consensus["value"])
        self.assertIn("En cas de danger imminent", consensus["value"])
        self.assertIn("Verhalten bei Betriebsstörungen", consensus["value"])
        self.assertNotIn("d’urgence s.v.p.", consensus["value"])

    def test_sign_profile_skips_empty_ocr_after_filtering(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "stability_count": 5,
                "memory_text": 'OBJECT | visible sign/board | OCR text: "nstr / str / 1c" | upper center frame | likely',
            }
        )

        sign = hub.graph_profiles(label="text surface")["profiles"][0]
        self.assertNotIn("text.visible", sign["slots"])
        relation_text = "\n".join(
            f"{row['subject']} {row['relation_type']} {row['object']}"
            for row in hub.graph_relations(label="text surface")["relations"]
        )
        self.assertNotIn("contains_text", relation_text)

    def test_screen_like_ocr_becomes_display_screen_not_transit_sign(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "stability_count": 5,
                "memory_text": (
                    'OBJECT | visible sign/board | OCR text: "984K Views / Post / instagram.com / '
                    'Last edited 18:29 / Follow" | middle center frame | likely'
                ),
            }
        )

        screen = hub.graph_profiles(label="display screen")["profiles"][0]
        self.assertEqual(screen["label"], "display screen")
        self.assertEqual(screen["slots"]["object_type"][0]["value"], "display screen")
        self.assertEqual(hub.graph_profiles(label="transit sign")["profiles"], [])

    def test_wikipedia_style_ocr_becomes_display_screen(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "stability_count": 5,
                "memory_text": (
                    'OBJECT | visible sign/board | OCR text: "11:10 Sun 7. Jun / '
                    'en.wikipedia.org / Recently featured / Full article" | middle center frame | likely'
                ),
            }
        )

        screen = hub.graph_profiles(label="display screen")["profiles"][0]
        self.assertEqual(screen["slots"]["object_type"][0]["value"], "display screen")

    def test_generic_text_surface_upgrades_into_display_screen_when_ocr_clues_improve(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "stability_count": 5,
                "memory_text": 'OBJECT | visible sign/board | OCR text: "Featured article / Horizon Call of the Mountain" | middle center frame | likely',
            }
        )
        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:01:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "stability_count": 5,
                "memory_text": 'OBJECT | visible sign/board | OCR text: "11:10 Sun 7. Jun / en.wikipedia.org / Featured article / Horizon Call of the Mountain" | middle center frame | likely',
            }
        )

        self.assertEqual(hub.graph_profiles(label="text surface")["profiles"], [])
        screen = hub.graph_profiles(label="display screen")["profiles"][0]
        self.assertEqual(screen["observation_count"], 2)
        self.assertEqual(screen["canonical_slots"]["object_type"]["value"], "display screen")

    def test_generic_repeat_does_not_downgrade_existing_display_screen(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "stability_count": 5,
                "memory_text": 'OBJECT | visible sign/board | OCR text: "11:10 Sun 7. Jun / en.wikipedia.org / Featured article" | middle center frame | likely',
            }
        )
        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:01:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "stability_count": 5,
                "memory_text": 'OBJECT | visible sign/board | OCR text: "Featured article / Horizon Call of the Mountain" | middle center frame | likely',
            }
        )

        self.assertEqual(hub.graph_profiles(label="text surface")["profiles"], [])
        screen = hub.graph_profiles(label="display screen")["profiles"][0]
        self.assertEqual(screen["observation_count"], 2)
        self.assertEqual(screen["canonical_slots"]["object_type"]["value"], "display screen")

    def test_profile_canonical_slot_prefers_current_repeated_value(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "scene_phase": "moving",
                "memory_text": "OBJECT | visible person | human figure detected; brown upper-body clothing | middle center frame | uncertain",
            }
        )
        for minute in range(1, 4):
            hub.ingest_perception(
                {
                    "timestamp": f"2026-06-05T10:0{minute}:00+00:00",
                    "source": "native_yolo_detector",
                    "scene_phase": "stable",
                    "stability_count": 5,
                    "memory_text": "OBJECT | visible person | human figure detected; gray upper-body clothing | middle center frame | likely",
                }
            )

        person = hub.graph_profiles(label="visible person")["profiles"][0]
        self.assertEqual(person["canonical_slots"]["clothing.upper"]["value"], "gray upper-body clothing")
        self.assertEqual(person["canonical_slots"]["clothing.upper"]["status"], "current")

    def test_visible_people_does_not_merge_with_visible_person(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "memory_text": "\n".join(
                    [
                        "OBJECT | visible people | 2 people/faces detected | middle center frame | likely",
                        "OBJECT | background person | additional face/person detected | behind/near foreground subject | likely",
                    ]
                ),
            }
        )

        labels = {profile["label"] for profile in hub.graph_profiles()["profiles"]}
        self.assertIn("visible people", labels)
        self.assertIn("background person", labels)
        self.assertNotIn("visible person", labels)

    def test_attributes_become_stale_when_entity_disappears(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "memory_text": "OBJECT | visible person | human figure detected; glasses | middle center frame | likely",
            }
        )
        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:01:00+00:00",
                "source": "native_vision_state",
                "memory_text": "EVENT | scene visibility | no reliable object/event currently visible | visible frame | likely",
                "active_entity_labels": [],
                "store_legacy": False,
            }
        )

        attributes = [row for row in hub.graph_metadata()["recent_attributes"] if row["entity"] == "visible person"]
        self.assertTrue(attributes)
        self.assertEqual({row["status"] for row in attributes}, {"stale"})

    def test_near_eyeglasses_enrich_visible_person_eyewear(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "scene_phase": "stable",
                "memory_text": "OBJECT | eyeglasses | image-level visual classification | near visible person; middle center frame; medium visible object | likely",
            }
        )

        attributes = hub.graph_metadata()["recent_attributes"]
        self.assertIn(
            ("visible person", "eyewear", "eyeglasses"),
            {(row["entity"], row["attribute_key"], row["attribute_value"]) for row in attributes},
        )

    def test_graph_profiles_api_route_uses_label_filter(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)
        hub.ingest_perception(
            {
                "source": "native_vision",
                "memory_text": "OBJECT | visible person | human figure detected; glasses | middle center frame | likely",
            }
        )

        handler_cls = make_handler(hub, "dev-token")
        handler = object.__new__(handler_cls)
        handler.path = "/graph/profiles?label=visible%20person"
        handler.headers = {"X-TRACE-Token": "dev-token"}
        handler._json = Mock()

        handler.do_GET()

        payload = handler._json.call_args.args[0]
        self.assertEqual(payload["profiles"][0]["label"], "visible person")
        self.assertIn("eyewear", payload["profiles"][0]["slots"])

    def test_delete_time_range_removes_only_matching_memories(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        first = MemoryInput(
            detailed_text="I put my keys in the hallway bowl.",
            category="object_location",
            captured_at="2026-06-01T10:00:00+00:00",
        )
        second = MemoryInput(
            detailed_text="I discussed a travel plan with Sam.",
            category="conversation",
            sensitivity="restricted",
            captured_at="2026-06-01T11:00:00+00:00",
        )
        hub.store.add(first, "I put my keys in the hallway bowl.")
        hub.store.add(second, "I discussed a travel plan with Sam.")

        deleted = hub.delete(
            {
                "scope": "time_range",
                "start": "2026-06-01T09:59:00+00:00",
                "end": "2026-06-01T10:01:00+00:00",
            }
        )

        self.assertEqual(deleted["deleted"], 1)
        remaining = hub.metadata()
        self.assertEqual(remaining["total"], 1)
        self.assertEqual(remaining["recent"][0]["category"], "conversation")


    def test_event_upsert_deduplicates_repeated_scene_visibility(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        for i in range(5):
            hub.ingest_perception({
                "timestamp": f"2026-06-07T12:0{i}:00Z",
                "source_type": "vision",
                "source": "test",
                "scene_phase": "stable",
                "location_hint": "GPS 48.2558, 11.6101",
                "active_entity_labels": [],
                "store_legacy": False,
                "memory_text": "EVENT | scene visibility | no reliable object/event currently visible | visible frame | likely",
            })

        meta = hub.graph_metadata()
        self.assertEqual(meta["events"], 1, "repeated scene-visibility should upsert, not insert 5 events")
        self.assertLessEqual(meta["relations"], 3, "deduped events should not cascade duplicate relations")

    def test_event_upsert_creates_new_event_for_different_types(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception({
            "timestamp": "2026-06-07T12:00:00Z",
            "source_type": "vision",
            "source": "test",
            "scene_phase": "stable",
            "active_entity_labels": [],
            "store_legacy": False,
            "memory_text": "EVENT | scene visibility | nothing visible | frame | likely",
        })
        hub.ingest_perception({
            "timestamp": "2026-06-07T12:01:00Z",
            "source_type": "vision",
            "source": "test",
            "scene_phase": "stable",
            "active_entity_labels": ["door"],
            "store_legacy": False,
            "memory_text": "EVENT | door | opened | hallway | likely",
        })

        meta = hub.graph_metadata()
        self.assertEqual(meta["events"], 2, "different event types should create separate events")

    def test_gps_place_dedup_at_four_decimal_precision(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        coords = [
            "GPS 48.25580, 11.61010",
            "GPS 48.25581, 11.61012",
            "GPS 48.25584, 11.61014",
        ]
        for i, gps in enumerate(coords):
            hub.ingest_perception({
                "timestamp": f"2026-06-07T12:0{i}:00Z",
                "source_type": "vision",
                "source": "test",
                "scene_phase": "stable",
                "location_hint": gps,
                "active_entity_labels": ["keys"],
                "store_legacy": False,
                "memory_text": "OBJECT | keys | on table | center frame | likely",
            })

        meta = hub.graph_metadata()
        self.assertEqual(meta["places"], 1, "GPS coords within ~11m should merge to one place at 4dp")

    def test_graph_aware_recall_returns_location(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception({
            "timestamp": "2026-06-07T12:00:00Z",
            "source_type": "vision",
            "source": "test",
            "scene_phase": "stable",
            "location_hint": "GPS 48.2558, 11.6101 | Robert-Bosch-Straße 17, Garching",
            "active_entity_labels": ["keys"],
            "store_legacy": False,
            "memory_text": "OBJECT | keys | metal keys on desk | center frame | likely",
        })

        result = hub.chat("where is my keys?")
        self.assertIn("Robert-Bosch", result["answer"], "graph recall should return place name from graph")
        self.assertEqual(result["intent"], "where_is")

    def test_where_is_spatial_pose_answers_coordinates(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception(
            {
                "timestamp": "2026-06-12T02:00:00+00:00",
                "source": "mobileclip_spatial_word",
                "provider": "mobileclip_spatial_word",
                "scene_phase": "spatial_word_map",
                "confidence": 0.75,
                "stability_count": 2,
                "memory_text": "\n".join(
                    [
                        "OBJECT | keyboard | mobileclip spatial object | spatial word map | likely",
                        "OBJECT | water bottle | mobileclip spatial object | spatial word map | likely",
                    ]
                ),
                "metadata": {
                    "capture_mode": "spatial_word_map",
                    "build": "spatial-test",
                    "spatial_words": [
                        {"label": "keyboard", "kind": "object", "x": 0.25, "y": -0.1, "z": 1.2, "w": 0.55, "h": 0.18, "support_plane": "plane-desk", "verified": True, "sightings": 6},
                        {"label": "water bottle", "kind": "object", "x": -0.4, "y": 0.02, "z": 0.85, "w": 0.08, "h": 0.24, "verified": False, "sightings": 3},
                    ],
                },
            }
        )

        keyboard = hub.chat("where is the keyboard")
        self.assertEqual(keyboard["intent"], "where_is")
        self.assertIn("keyboard: pinned in the room at (0.25, -0.10, 1.20) meters [frame: genesis]", keyboard["answer"])
        self.assertIn("size ~0.55×0.18 m", keyboard["answer"])
        self.assertIn("sightings 6", keyboard["answer"])
        self.assertEqual(keyboard["citations"][0]["source"], "spatial_pose")
        self.assertEqual(keyboard["citations"][0]["captured_at"], "2026-06-12T02:00:00+00:00")
        self.assertEqual(keyboard["citations"][0]["confidence"], 0.9)

        bottle = hub.chat("where's my bottle")
        self.assertEqual(bottle["intent"], "where_is")
        self.assertIn("water bottle: pinned in the room at (-0.40, 0.02, 0.85) meters [frame: genesis]", bottle["answer"])
        self.assertEqual(bottle["citations"][0]["confidence"], 0.6)

        unknown = hub.chat("where is the stapler")
        self.assertEqual(unknown["intent"], "grounded_answer")
        self.assertIn("I don't have anything about that in memory yet", unknown["answer"])
        self.assertEqual(unknown["citations"], [])

    def test_vlm_person_enrichment_fills_attribute_slots(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception({
            "timestamp": "2026-06-07T12:00:00Z",
            "source_type": "vision",
            "source": "fastvlm_person_enrichment",
            "scene_phase": "stable",
            "location_hint": "GPS 48.2558, 11.6101 | Garching",
            "active_entity_labels": ["visible person"],
            "store_legacy": False,
            "memory_text": "OBJECT | visible person | adult, average height, short dark hair, glasses, gray t-shirt, blue jeans, white sneakers | sitting at desk | likely",
        })

        profiles = hub.graph_profiles(label="visible person")
        slot_keys = set(profiles["profiles"][0]["slots"].keys())

        self.assertIn("age.approx", slot_keys)
        self.assertIn("stature", slot_keys)
        self.assertIn("hair.color", slot_keys)
        self.assertIn("hair.length", slot_keys)
        self.assertIn("eyewear", slot_keys)
        self.assertIn("clothing.upper", slot_keys)
        self.assertIn("clothing.lower", slot_keys)
        self.assertIn("clothing.feet", slot_keys)

    def test_hair_color_matches_hyphenated_length_adjectives(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_perception({
            "timestamp": "2026-06-07T12:00:00Z",
            "source_type": "vision",
            "source": "test",
            "scene_phase": "stable",
            "active_entity_labels": ["visible person"],
            "store_legacy": False,
            "memory_text": "OBJECT | visible person | brown shoulder-length hair | standing | likely",
        })

        profiles = hub.graph_profiles(label="visible person")
        slots = {
            key: values[0]["value"]
            for key, values in profiles["profiles"][0]["slots"].items()
            if values
        }
        self.assertEqual(slots.get("hair.color"), "brown")
        self.assertEqual(slots.get("hair.length"), "shoulder-length")

    def test_graph_recall_falls_back_to_legacy_store(self) -> None:
        temp, hub = self.make_hub()
        self.addCleanup(temp.cleanup)

        hub.ingest_text("I left my passport in the top drawer of the oak desk.")

        result = hub.chat("where is my passport?")
        self.assertEqual(result["intent"], "where_is")
        self.assertTrue(result["used_private_memory"])


if __name__ == "__main__":
    unittest.main()
