from __future__ import annotations

import pytest

from soma.application import EgressGuard, PrivacyViolationError
from soma.domain import TextEgress


def test_egress_guard_accepts_only_provenance_bearing_text() -> None:
    payload = TextEgress("typed observation", ("event-1",))

    assert EgressGuard.text(payload) == "typed observation"


@pytest.mark.parametrize(
    "raw_payload",
    [b"raw audio", bytearray(b"pixels"), memoryview(b"frame"), "untyped text"],
)
def test_egress_guard_rejects_raw_or_untyped_payloads(raw_payload: object) -> None:
    with pytest.raises(PrivacyViolationError, match="only typed text"):
        EgressGuard.text(raw_payload)
