"""Общий контекст сервисов: база данных, настройки, шифрование токенов."""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from ..config import Settings
from ..db import Database


@dataclass
class Context:
    db: Database
    settings: Settings

    def __post_init__(self):
        key = base64.urlsafe_b64encode(hashlib.sha256(("portagraph-tokens:" + self.settings.secret_key).encode()).digest())
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> bytes:
        """Токены Git-хостингов хранятся только в зашифрованном виде (Fernet: AES-128-CBC + HMAC-SHA256)."""
        return self._fernet.encrypt(value.encode("utf-8"))

    def decrypt(self, data: bytes) -> str | None:
        try:
            return self._fernet.decrypt(bytes(data)).decode("utf-8")
        except (InvalidToken, ValueError):
            return None
