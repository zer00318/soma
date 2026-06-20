from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from soma_hub.models import MemoryInput
from soma_hub.policy import classify_memory, redact_for_public_summary


@dataclass(frozen=True)
class ExtractedInput:
    text: str
    source_type: str = "audio"
    provider: str = "prototype_text"
    confidence: float | None = None
    metadata: dict[str, object] | None = None


class ExtractionProvider(Protocol):
    name: str

    def build_memory(self, extracted: ExtractedInput) -> tuple[MemoryInput, str]:
        ...


class TextExtractionProvider:
    """Default provider for already-extracted text from a capture pipeline."""

    name = "prototype_text"

    def build_memory(self, extracted: ExtractedInput) -> tuple[MemoryInput, str]:
        category, sensitivity = classify_memory(extracted.text)
        public_summary = redact_for_public_summary(extracted.text)
        memory = MemoryInput(
            detailed_text=extracted.text,
            source_type=extracted.source_type,
            category=category,
            sensitivity=sensitivity,
            confidence=extracted.confidence if extracted.confidence is not None else (0.8 if category != "general" else 0.65),
            metadata={
                "extractor": extracted.provider,
                **(extracted.metadata or {}),
            },
        )
        return memory, public_summary


class ExtractionPipeline:
    def __init__(self) -> None:
        default = TextExtractionProvider()
        self._providers: dict[str, ExtractionProvider] = {
            default.name: default,
            "simulated_audio_transcript": default,
            "simulated_visual_caption": default,
            "continuous_audio_transcript": default,
        }

    def build_memory(self, extracted: ExtractedInput) -> tuple[MemoryInput, str]:
        provider = self._providers.get(extracted.provider)
        if provider is None:
            raise ValueError(f"Unknown extraction provider: {extracted.provider}")
        return provider.build_memory(extracted)

    def list_providers(self) -> list[str]:
        return sorted(self._providers)
