"""Настройки приложения из переменных окружения (и файла .env, если он есть)."""
from __future__ import annotations

import os
import pathlib
import secrets
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_dotenv():
    env = ROOT / ".env"
    if not env.exists():
        return
    for raw in env.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on", "да")


@dataclass
class Settings:
    database_url: str
    secret_key: str
    data_dir: pathlib.Path
    allow_local_paths: bool
    demo_seed: bool
    max_upload_mb: int
    public_url: str
    workers: int
    testing: bool = False

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        _load_dotenv()
        data_dir = pathlib.Path(os.environ.get("PORTAGRAPH_DATA_DIR", ROOT / "data")).resolve()
        secret = os.environ.get("SECRET_KEY")
        if not secret:
            # ключ сохраняется в каталоге данных, чтобы сессии и токены переживали перезапуск
            data_dir.mkdir(parents=True, exist_ok=True)
            key_file = data_dir / ".secret_key"
            if not key_file.exists():
                key_file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
            secret = key_file.read_text(encoding="utf-8").strip()
        values = dict(
            database_url=os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/portagraph"),
            secret_key=secret,
            data_dir=data_dir,
            allow_local_paths=_bool("ALLOW_LOCAL_PATHS", True),
            demo_seed=_bool("DEMO_SEED", True),
            max_upload_mb=int(os.environ.get("MAX_UPLOAD_MB", "100")),
            public_url=os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/"),
            workers=int(os.environ.get("ANALYSIS_WORKERS", "2")),
        )
        values.update(overrides)
        return cls(**values)
