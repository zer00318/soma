from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EncryptedTextCodec:
    """Authenticated encryption for text memory, with legacy read support."""

    VERSION = "soma2"
    LEGACY_VERSION = "soma1"

    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("SOMA encryption key must be at least 32 bytes")
        self._key = hashlib.sha256(key).digest()
        self._aesgcm = AESGCM(self._key)

    def encrypt(self, text: str) -> str:
        nonce = secrets.token_bytes(12)
        ciphertext = self._aesgcm.encrypt(nonce, text.encode("utf-8"), self.VERSION.encode("utf-8"))
        payload = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
        return f"{self.VERSION}:{payload}"

    def decrypt(self, token: str) -> str:
        prefix, encoded = token.split(":", 1)
        payload = base64.urlsafe_b64decode(encoded.encode("ascii"))
        if prefix == self.VERSION:
            plaintext = self._aesgcm.decrypt(
                payload[:12], payload[12:], self.VERSION.encode("utf-8")
            )
            return plaintext.decode("utf-8")
        if prefix == self.LEGACY_VERSION:
            return self._decrypt_legacy(payload)
        raise ValueError("unsupported encrypted memory payload")

    def _decrypt_legacy(self, payload: bytes) -> str:
        nonce, mac, ciphertext = payload[:16], payload[16:48], payload[48:]
        expected = hmac.new(self._key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError("encrypted memory integrity check failed")
        plaintext = bytes(
            left ^ right
            for left, right in zip(ciphertext, self._legacy_stream(nonce, len(ciphertext)))
        )
        return plaintext.decode("utf-8")

    def _legacy_stream(self, nonce: bytes, size: int) -> bytes:
        output = bytearray()
        counter = 0
        while len(output) < size:
            block = hmac.new(self._key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
            output.extend(block)
            counter += 1
        return bytes(output[:size])
