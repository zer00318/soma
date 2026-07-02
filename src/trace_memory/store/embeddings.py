from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

import numpy as np


class TextEmbedder(Protocol):
    def embed(self, texts: list[str]) -> list[tuple[float, ...]]: ...


def _normalize(vector: np.ndarray) -> tuple[float, ...]:
    norm = float(np.linalg.norm(vector))
    if norm <= 0.0:
        return tuple(float(x) for x in vector)
    return tuple(float(x) for x in (vector / norm))


def discover_sentence_transformer_path() -> str | None:
    configured = os.environ.get("TRACE_SENTENCE_TRANSFORMER_MODEL")
    if configured:
        return configured

    root = (
        Path.home()
        / ".cache"
        / "huggingface"
        / "hub"
        / "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2"
        / "snapshots"
    )
    if not root.exists():
        return None
    snapshots = sorted(path for path in root.iterdir() if path.is_dir())
    if not snapshots:
        return None
    return str(snapshots[-1])


class SentenceTransformerEmbedder:
    def __init__(self, model_path: str | None = None) -> None:
        self._model_path = model_path or discover_sentence_transformer_path()
        if self._model_path is None:
            raise FileNotFoundError("no local sentence-transformers model was found")
        self._model = None
        self.mode = "sentence-transformer"

    def _load(self):
        if self._model is None:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            from sentence_transformers import SentenceTransformer

            # TRACE_EMBED_DEVICE=cpu lets the eval/query path avoid the Metal GPU when a local
            # LLM (binder/authoring) is using it — running both on MPS OOMs the M2 (~32GB).
            device = os.environ.get("TRACE_EMBED_DEVICE") or None
            self._model = SentenceTransformer(self._model_path, device=device)
        return self._model

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        if not texts:
            return []
        model = self._load()
        vectors = model.encode(
            texts,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return [tuple(float(value) for value in row) for row in vectors]


class LexicalFallbackEmbedder:
    """Deterministic fallback when the local sentence-transformer is unavailable."""

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim
        self.mode = "lexical-fallback"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            bucket = np.zeros(self._dim, dtype=np.float32)
            for token in text.lower().split():
                bucket[hash(token) % self._dim] += 1.0
            vectors.append(_normalize(bucket))
        return vectors


def build_default_embedder() -> TextEmbedder:
    try:
        return SentenceTransformerEmbedder()
    except Exception:
        return LexicalFallbackEmbedder()
