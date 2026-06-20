from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EncryptedTextCodec:
    """AES-GCM encryption for private extracted memory.

    New writes use `soma2`, while legacy `soma1` payloads remain readable so
    older prototype data does not break when the codec is upgraded.
    """

    VERSION = "soma2"
    LEGACY_VERSION = "soma1"

    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("SOMA encryption key must be at least 32 bytes")
        self._key = hashlib.sha256(key).digest()
        self._aesgcm = AESGCM(self._key)

    @classmethod
    def from_env_or_file(cls, data_dir: Path) -> "EncryptedTextCodec":
        env_key = os.environ.get("SOMA_HUB_KEY")
        if env_key:
            return cls(env_key.encode("utf-8"))

        data_dir.mkdir(parents=True, exist_ok=True)
        key_path = data_dir / ".soma_hub_key"
        if not key_path.exists():
            key_path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
            try:
                key_path.chmod(0o600)
            except OSError:
                pass
        return cls(key_path.read_text(encoding="utf-8").strip().encode("utf-8"))

    def encrypt(self, text: str) -> str:
        nonce = secrets.token_bytes(12)
        plaintext = text.encode("utf-8")
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, self.VERSION.encode("utf-8"))
        payload = nonce + ciphertext
        return f"{self.VERSION}:{base64.urlsafe_b64encode(payload).decode('ascii')}"

    def decrypt(self, token: str) -> str:
        prefix, encoded = token.split(":", 1)
        payload = base64.urlsafe_b64decode(encoded.encode("ascii"))
        if prefix == self.VERSION:
            nonce, ciphertext = payload[:12], payload[12:]
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, self.VERSION.encode("utf-8"))
            return plaintext.decode("utf-8")
        if prefix == self.LEGACY_VERSION:
            return self._decrypt_legacy(payload)
        raise ValueError("Unsupported encrypted memory payload")

    def _decrypt_legacy(self, payload: bytes) -> str:
        nonce, mac, ciphertext = payload[:16], payload[16:48], payload[48:]
        expected = hmac.new(self._key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError("Encrypted memory integrity check failed")
        keystream = self._legacy_stream(nonce, len(ciphertext))
        plaintext = bytes(a ^ b for a, b in zip(ciphertext, keystream))
        return plaintext.decode("utf-8")

    def _legacy_stream(self, nonce: bytes, size: int) -> bytes:
        out = bytearray()
        counter = 0
        while len(out) < size:
            counter_bytes = counter.to_bytes(8, "big")
            out.extend(hmac.new(self._key, nonce + counter_bytes, hashlib.sha256).digest())
            counter += 1
        return bytes(out[:size])
