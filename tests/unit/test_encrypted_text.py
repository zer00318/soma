from __future__ import annotations

import base64
import hashlib
import secrets

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from trace_memory.adapters.encrypted_text import EncryptedTextCodec


def test_encrypted_text_round_trip_and_random_nonce() -> None:
    codec = EncryptedTextCodec(b"a" * 32)

    first = codec.encrypt("private text")
    second = codec.encrypt("private text")

    assert first != second
    assert codec.decrypt(first) == "private text"


def test_encrypted_text_rejects_tampering() -> None:
    codec = EncryptedTextCodec(b"b" * 32)
    token = codec.encrypt("private text")
    prefix, encoded = token.split(":", 1)
    payload = bytearray(base64.urlsafe_b64decode(encoded))
    payload[-1] ^= 1
    tampered = prefix + ":" + base64.urlsafe_b64encode(payload).decode("ascii")

    with pytest.raises(InvalidTag):
        codec.decrypt(tampered)


def test_encrypted_text_requires_a_strong_source_key() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        EncryptedTextCodec(b"short")


def test_encrypted_text_reads_pre_rename_aes_payload() -> None:
    source_key = b"c" * 32
    key = hashlib.sha256(source_key).digest()
    prefix = bytes.fromhex("736f6d6132").decode("ascii")
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, b"existing memory", prefix.encode("ascii"))
    token = prefix + ":" + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    assert EncryptedTextCodec(source_key).decrypt(token) == "existing memory"
