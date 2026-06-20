"""Local text-reasoner adapter boundary."""

from __future__ import annotations

import json
import urllib.request
from contextlib import AbstractContextManager
from typing import Callable, Protocol, cast
from urllib.error import URLError
from urllib.request import Request


class _Readable(Protocol):
    def read(self) -> bytes: ...


Opener = Callable[[Request, float], AbstractContextManager[_Readable]]


def _default_opener(request: Request, timeout: float) -> AbstractContextManager[_Readable]:
    return cast(
        "AbstractContextManager[_Readable]",
        urllib.request.urlopen(request, timeout=timeout),
    )


class OllamaReasoner:
    """TextReasoner backed by a local Ollama server."""

    def __init__(
        self,
        model: str = "gemma3:12b-it-qat",
        host: str = "http://127.0.0.1:11434",
        timeout: float = 60.0,
        opener: Opener | None = None,
    ) -> None:
        self._model = model
        self._host = host.rstrip("/")
        self._timeout = timeout
        self._opener = opener if opener is not None else _default_opener

    def reason(self, prompt: str) -> str:
        request = self._build_request(prompt)
        raw = self._send(request)
        return self._parse(raw)

    def _build_request(self, prompt: str) -> Request:
        body = json.dumps(
            {
                "model": self._model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0},
            }
        ).encode("utf-8")
        return Request(
            f"{self._host}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def _send(self, request: Request) -> bytes:
        try:
            with self._opener(request, self._timeout) as response:
                return response.read()
        except (URLError, OSError) as exc:
            raise RuntimeError(f"ollama transport failed: {exc}") from exc

    def _parse(self, raw: bytes) -> str:
        try:
            payload = json.loads(raw)
            response = payload["response"]
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError(f"ollama returned malformed response: {exc}") from exc
        if not isinstance(response, str):
            raise RuntimeError("ollama response field was not a string")
        return response.strip()
