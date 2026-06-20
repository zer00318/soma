"""Cloud text-only reasoner boundary; all payloads must pass EgressGuard."""

from __future__ import annotations

from typing import Callable

from soma.application.egress_guard import EgressGuard
from soma.domain.egress import TextEgress


def _unconfigured_sender(_text: str) -> str:
    raise NotImplementedError("configure a cloud endpoint")


class CloudTextReasoner:
    """TextReasoner for an optional frontier model, gated by the EgressGuard."""

    def __init__(
        self,
        sender: Callable[[str], str] | None = None,
        source_event_ids: tuple[str, ...] = ("reasoner-prompt",),
    ) -> None:
        self._sender = sender if sender is not None else _unconfigured_sender
        self._source_ids = source_event_ids

    def reason(self, prompt: str) -> str:
        payload = TextEgress(text=prompt, source_event_ids=self._source_ids)
        guarded = EgressGuard.text(payload)
        return self._sender(guarded)
