"""Доступ к PostgreSQL: пул соединений, удобные функции запросов и миграции."""
from __future__ import annotations

import logging
import pathlib
import queue
import threading
from contextlib import contextmanager

from .pgwire import Connection, DatabaseError, InterfaceError, Json, UniqueViolation  # noqa: F401

log = logging.getLogger(__name__)
MIGRATIONS = pathlib.Path(__file__).with_name("migrations")


class Database:
    """Пул соединений. Каждый поток берёт соединение на время работы и возвращает его."""

    def __init__(self, dsn: str, size: int = 8):
        self.dsn = dsn
        self.size = size
        self._idle: queue.LifoQueue[Connection] = queue.LifoQueue()
        self._created = 0
        self._lock = threading.Lock()
        self._local = threading.local()

    def _new(self) -> Connection:
        return Connection(self.dsn)

    def acquire(self) -> Connection:
        while True:
            try:
                conn = self._idle.get_nowait()
            except queue.Empty:
                with self._lock:
                    if self._created < self.size:
                        self._created += 1
                        try:
                            return self._new()
                        except Exception:
                            self._created -= 1
                            raise
                conn = self._idle.get(timeout=30)
            if conn.closed:
                with self._lock:
                    self._created -= 1
                continue
            return conn

    def release(self, conn: Connection):
        try:
            conn.reset()
        except Exception:
            conn.close()
        if conn.closed:
            with self._lock:
                self._created -= 1
            return
        self._idle.put(conn)

    @contextmanager
    def connection(self):
        """Соединение текущего потока; вложенные вызовы получают то же самое."""
        existing = getattr(self._local, "conn", None)
        if existing is not None:
            yield existing
            return
        conn = self.acquire()
        self._local.conn = conn
        try:
            yield conn
        finally:
            self._local.conn = None
            self.release(conn)

    @contextmanager
    def transaction(self):
        with self.connection() as conn, conn.transaction():
            yield conn

    # ---------------------------------------------------------------- сокращения
    def all(self, sql: str, *params) -> list[dict]:
        with self.connection() as c:
            return c.execute(sql, params).all()

    def one(self, sql: str, *params) -> dict | None:
        with self.connection() as c:
            return c.execute(sql, params).one()

    def scalar(self, sql: str, *params):
        with self.connection() as c:
            return c.execute(sql, params).scalar()

    def run(self, sql: str, *params) -> int:
        with self.connection() as c:
            return c.execute(sql, params).rowcount

    def close(self):
        while True:
            try:
                self._idle.get_nowait().close()
            except queue.Empty:
                break

    # ---------------------------------------------------------------- миграции
    def ensure_database(self) -> bool:
        """Создаёт базу данных из DSN, если её ещё нет (удобно для запуска «одной командой»)."""
        try:
            Connection(self.dsn).close()
            return False
        except DatabaseError as e:
            if e.sqlstate != "3D000":  # invalid_catalog_name
                raise
        import re
        from urllib.parse import urlsplit, urlunsplit
        parts = urlsplit(self.dsn)
        name = parts.path.lstrip("/")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\-]{0,62}", name):
            raise InterfaceError(f"Недопустимое имя базы данных: {name}")
        admin = Connection(urlunsplit(parts._replace(path="/postgres")))
        try:
            admin.execute(f'CREATE DATABASE "{name}"')
            log.info("Создана база данных %s", name)
        finally:
            admin.close()
        return True

    def migrate(self) -> list[str]:
        self.ensure_database()
        applied = []
        with self.connection() as c:
            c.execute_script("CREATE TABLE IF NOT EXISTS schema_migrations "
                             "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
            done = {r["version"] for r in c.execute("SELECT version FROM schema_migrations").all()}
            for path in sorted(MIGRATIONS.glob("*.sql")):
                if path.stem in done:
                    continue
                log.info("Применяю миграцию %s", path.name)
                with c.transaction():
                    c.execute_script(path.read_text(encoding="utf-8"))
                    c.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (path.stem,))
                applied.append(path.stem)
        return applied
