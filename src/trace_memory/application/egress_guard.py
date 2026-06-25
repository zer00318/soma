from __future__ import annotations

from trace_memory.domain.egress import TextEgress


class PrivacyViolationError(ValueError):
    pass


class EgressGuard:
    """Reject every outbound payload that is not provenance-bearing text."""

    @staticmethod
    def text(payload: object) -> str:
        if not isinstance(payload, TextEgress):
            raise PrivacyViolationError("only typed text may egress")
        return payload.text
