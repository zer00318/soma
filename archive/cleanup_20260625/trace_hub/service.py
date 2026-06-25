from __future__ import annotations

from pathlib import Path

from trace_hub.capture_simulator import CaptureSimulator
from trace_hub.crypto import EncryptedTextCodec
from trace_hub.extraction import ExtractedInput, ExtractionPipeline
from trace_hub.graph import RelationalMemoryGraph
from trace_hub.platform_audio import live_audio_status
from trace_hub.recall import RecallFirewall
from trace_hub import importer
from trace_hub.storage import MemoryStore


class TraceHub:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.root_dir = Path(__file__).resolve().parent.parent
        self.codec = EncryptedTextCodec.from_env_or_file(data_dir)
        self.store = MemoryStore(data_dir / "trace_hub.sqlite3", self.codec)
        self.graph = RelationalMemoryGraph(data_dir / "trace_hub.sqlite3", self.codec)
        self.extraction = ExtractionPipeline()
        self.capture = CaptureSimulator()
        self.recall = RecallFirewall(self.store, self.graph)
        self.graph.start_stale_encounter_cleaner()
        self.graph.start_confidence_promoter()
        self.graph.start_pruner()

    def ingest_text(self, text: str, source_type: str = "audio") -> dict:
        return self.ingest_extracted(
            {
                "text": text,
                "source_type": source_type,
                "provider": "prototype_text",
            }
        )

    def ingest_extracted(self, payload: dict) -> dict:
        extracted = ExtractedInput(
            text=str(payload["text"]).strip(),
            source_type=str(payload.get("source_type", "audio")),
            provider=str(payload.get("provider", "prototype_text")),
            confidence=float(payload["confidence"]) if payload.get("confidence") is not None else None,
            metadata=dict(payload.get("metadata", {})),
        )
        memory, public_summary = self.extraction.build_memory(extracted)
        record = self.store.add(memory, public_summary)
        return {
            "id": record.id,
            "captured_at": record.captured_at,
            "category": record.category,
            "sensitivity": record.sensitivity,
            "summary": record.public_summary,
            "provider": extracted.provider,
        }

    def ingest_perception(self, payload: dict) -> dict:
        graph_result = self.graph.ingest_packet(payload)
        text = str(payload.get("memory_text") or payload.get("text") or "").strip()
        legacy_record = None
        if text:
            if payload.get("store_legacy", True):
                memory, public_summary = self.extraction.build_memory(
                    ExtractedInput(
                        text=text,
                        source_type=str(payload.get("source_type", payload.get("source", "vision"))),
                        provider="prototype_text",
                        confidence=float(payload["confidence"]) if payload.get("confidence") is not None else None,
                        metadata={
                            "graph_ingest": True,
                            "source": payload.get("source", "native_perception"),
                            **dict(payload.get("metadata", {})),
                        },
                    )
                )
                record = self.store.add(memory, public_summary)
                legacy_record = {
                    "id": record.id,
                    "captured_at": record.captured_at,
                    "category": record.category,
                    "summary": record.public_summary,
                }
        return {
            "graph": graph_result,
            "legacy_memory": legacy_record,
        }

    def chat(self, message: str) -> dict:
        return self.recall.answer(message)

    def metadata(self) -> dict:
        return self.store.metadata()

    def graph_metadata(self) -> dict:
        return self.graph.metadata()

    def entities_list(self) -> list:
        return self.graph.metadata(limit=50).get("recent_entities", [])

    def graph_relations(self, label: str | None = None, relation_type: str | None = None) -> dict:
        return {"relations": self.graph.query_relations(label=label, relation_type=relation_type)}

    def graph_profiles(self, label: str | None = None) -> dict:
        return self.graph.profiles(label=label)

    def vlm_enrich(self, entity_id: str, vlm_description: str, captured_at: str) -> dict:
        return self.graph.ingest_vlm_enrichment(entity_id, vlm_description, captured_at)

    def benchmark(self) -> dict:
        from trace_hub.evaluation import run_default_evaluation

        return run_default_evaluation()

    def status(self) -> dict:
        capture = self.capture.status()
        return {
            "hub": "online",
            "capture_active": capture.active,
            "buffered_segments": capture.buffered_segments,
            "persisted_raw_media_files": capture.persisted_raw_media_files,
            "memory_total": self.store.metadata(limit=0)["total"],
            "graph": self.graph.metadata(limit=5),
            "extraction_providers": self.extraction.list_providers(),
            "live_audio": live_audio_status(self.root_dir),
        }

    def delete(self, payload: dict) -> dict:
        scope = payload.get("scope")
        if scope == "all":
            deleted = self.store.delete_all()
        elif scope == "category":
            deleted = self.store.delete_category(str(payload["category"]))
        elif scope == "time_range":
            deleted = self.store.delete_time_range(str(payload["start"]), str(payload["end"]))
        else:
            raise ValueError("scope must be all, category, or time_range")
        graph_deleted = self.graph.delete_all() if scope == "all" else 0
        return {"deleted": deleted, "graph_deleted": graph_deleted}

    def link_person_name(self, encounter_label: str, real_name: str) -> dict:
        return self.graph.link_person_name(encounter_label, real_name)

    def search(self, q: str) -> dict:
        entities = self.graph.profiles(label=q, limit=5).get("profiles", [])
        relations = self.graph.query_relations(label=q, limit=10)
        return {"query": q, "entities": entities, "relations": relations, "total": len(entities) + len(relations)}

    def import_whatsapp(self, export_path: str) -> dict:
        return importer.import_whatsapp(export_path, str(self.data_dir / "trace_hub.sqlite3"))

    def import_ics(self, ics_path: str) -> dict:
        return importer.import_ics(ics_path, str(self.data_dir / "trace_hub.sqlite3"))

    def import_imessage(self) -> dict:
        return importer.import_imessage(str(self.data_dir / "trace_hub.sqlite3"))
