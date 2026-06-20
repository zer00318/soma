from __future__ import annotations

import json
from types import TracebackType
from urllib.error import URLError
from urllib.request import Request

import pytest

from soma.adapters.cloud_text import CloudTextReasoner
from soma.adapters.ollama import OllamaReasoner
from soma.application.egress_guard import EgressGuard, PrivacyViolationError


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_ollama_reasoner_strips_response() -> None:
    body = json.dumps({"response": " hi "}).encode("utf-8")

    def opener(_request: Request, _timeout: float) -> _FakeResponse:
        return _FakeResponse(body)

    reasoner = OllamaReasoner(opener=opener)

    assert reasoner.reason("q") == "hi"


def test_ollama_reasoner_wraps_transport_error() -> None:
    def opener(_request: Request, _timeout: float) -> _FakeResponse:
        raise URLError("connection refused")

    reasoner = OllamaReasoner(opener=opener)

    with pytest.raises(RuntimeError, match="ollama transport failed"):
        reasoner.reason("q")


def test_ollama_reasoner_wraps_malformed_json() -> None:
    def opener(_request: Request, _timeout: float) -> _FakeResponse:
        return _FakeResponse(b"not json")

    reasoner = OllamaReasoner(opener=opener)

    with pytest.raises(RuntimeError, match="malformed response"):
        reasoner.reason("q")


def test_cloud_text_reasoner_returns_sender_output() -> None:
    reasoner = CloudTextReasoner(sender=lambda text: f"echo:{text}")

    assert reasoner.reason("hello") == "echo:hello"


def test_cloud_text_reasoner_passes_through_egress_guard() -> None:
    seen: list[str] = []

    def sender(text: str) -> str:
        seen.append(text)
        return EgressGuard.text(_NotTextEgress())  # type: ignore[arg-type]

    reasoner = CloudTextReasoner(sender=sender)

    with pytest.raises(PrivacyViolationError, match="only typed text"):
        reasoner.reason("hello")
    assert seen == ["hello"]


def test_cloud_text_reasoner_default_sender_is_unconfigured() -> None:
    reasoner = CloudTextReasoner()

    with pytest.raises(NotImplementedError, match="configure a cloud endpoint"):
        reasoner.reason("hello")


class _NotTextEgress:
    text = "spoofed"
