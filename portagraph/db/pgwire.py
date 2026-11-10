"""Минимальный клиент PostgreSQL на чистом Python (протокол v3).

Зачем свой драйвер: приложение должно запускаться на любом ноутбуке без сборки
нативных библиотек. Поддерживается всё, что нужно PortaGraph:

* аутентификация trust, password, MD5 и SCRAM-SHA-256 (по умолчанию в PostgreSQL 14+);
* простой протокол (несколько SQL-команд за раз – для миграций);
* расширенный протокол с параметрами `%s` (защита от SQL-инъекций);
* преобразование основных типов: целые, дробные, bool, text, json/jsonb,
  timestamp/timestamptz, date, bytea, uuid;
* транзакции через контекстный менеджер `transaction()`.
"""
from __future__ import annotations

import base64
import datetime as dt
import decimal
import hashlib
import hmac
import json
import os
import re
import socket
import struct
import uuid
from contextlib import contextmanager
from urllib.parse import unquote, urlparse


def _decode_msg(raw: bytes) -> str:
    """Сообщения об ошибках до входа приходят в кодировке сервера (на русской Windows – cp1251)."""
    for enc in ("utf-8", "cp1251", "cp866"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


class DatabaseError(Exception):
    """Ошибка, которую вернул сервер PostgreSQL."""

    def __init__(self, fields: dict[str, str]):
        self.fields = fields
        self.sqlstate = fields.get("C", "")
        self.message = fields.get("M", "ошибка базы данных")
        super().__init__(f"{self.sqlstate}: {self.message}" + (f" ({fields['D']})" if "D" in fields else ""))


class UniqueViolation(DatabaseError):
    pass


class InterfaceError(Exception):
    """Ошибка соединения или протокола на стороне клиента."""


# OID основных типов PostgreSQL
_INT = {20, 21, 23, 26}
_FLOAT = {700, 701}
_NUMERIC = 1700
_BOOL = 16
_JSON = {114, 3802}
_TIMESTAMPTZ = 1184
_TIMESTAMP = 1114
_DATE = 1082
_BYTEA = 17
_UUID = 2950


def _parse_timestamp(s: str) -> dt.datetime:
    # 2026-11-10 18:07:53.282+03 | 2026-11-10 18:07:53+00:30 | 2026-11-10 18:07:53
    m = re.match(r"(\d+)-(\d+)-(\d+)[ T](\d+):(\d+):(\d+)(?:\.(\d+))?(?:([+-])(\d\d)(?::?(\d\d))?(?::?(\d\d))?)?$", s)
    if not m:
        raise InterfaceError(f"Не удалось разобрать дату {s!r}")
    y, mo, d, h, mi, se, frac, sign, th, tm, ts = m.groups()
    micro = int((frac or "0").ljust(6, "0")[:6])
    tz = None
    if sign:
        off = dt.timedelta(hours=int(th), minutes=int(tm or 0), seconds=int(ts or 0))
        tz = dt.timezone(off if sign == "+" else -off)
    return dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(se), micro, tzinfo=tz)


def _convert(oid: int, raw: bytes | None):
    if raw is None:
        return None
    s = raw.decode("utf-8")
    if oid in _INT:
        return int(s)
    if oid == _BOOL:
        return s == "t"
    if oid in _FLOAT:
        return float(s)
    if oid == _NUMERIC:
        return float(decimal.Decimal(s))
    if oid in _JSON:
        return json.loads(s)
    if oid == _TIMESTAMPTZ or oid == _TIMESTAMP:
        return _parse_timestamp(s)
    if oid == _DATE:
        return dt.date.fromisoformat(s)
    if oid == _BYTEA:
        return bytes.fromhex(s[2:]) if s.startswith("\\x") else s.encode()
    if oid == _UUID:
        return uuid.UUID(s)
    return s


def _to_text(v) -> bytes | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return b"true" if v else b"false"
    if isinstance(v, (int, float, decimal.Decimal)):
        return str(v).encode()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return ("\\x" + bytes(v).hex()).encode()
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat().encode()
    if isinstance(v, uuid.UUID):
        return str(v).encode()
    if isinstance(v, Json):
        return json.dumps(v.value, ensure_ascii=False, default=str).encode()
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False, default=str).encode()
    if isinstance(v, (list, tuple, set, frozenset)):
        # список → массив PostgreSQL (для JSON-массивов используйте Json(...))
        return _array_literal(list(v)).encode()
    return str(v).encode()


def _array_literal(items: list) -> str:
    parts = []
    for x in items:
        if x is None:
            parts.append("NULL")
        elif isinstance(x, bool):
            parts.append("true" if x else "false")
        elif isinstance(x, (int, float, decimal.Decimal)):
            parts.append(str(x))
        else:
            s = str(x).replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'"{s}"')
    return "{" + ",".join(parts) + "}"


class Json:
    """Обёртка для явной передачи значения как JSON."""

    def __init__(self, value):
        self.value = value


_PLACEHOLDER = re.compile(r"%%|%s")


def _convert_placeholders(sql: str) -> tuple[str, int]:
    """`%s` → `$1, $2…`; `%%` → `%`."""
    counter = 0

    def repl(m):
        nonlocal counter
        if m.group(0) == "%%":
            return "%"
        counter += 1
        return f"${counter}"

    return _PLACEHOLDER.sub(repl, sql), counter


class Result:
    """Результат запроса: строки в виде словарей и число затронутых строк."""

    def __init__(self, columns: list[str], rows: list[dict], status: str):
        self.columns = columns
        self.rows = rows
        self.status = status

    @property
    def rowcount(self) -> int:
        parts = self.status.split()
        return int(parts[-1]) if parts and parts[-1].isdigit() else len(self.rows)

    def one(self):
        return self.rows[0] if self.rows else None

    def scalar(self):
        return next(iter(self.rows[0].values())) if self.rows else None

    def all(self) -> list[dict]:
        return self.rows


class Connection:
    """Одно соединение с PostgreSQL. Не потокобезопасно – используйте пул."""

    def __init__(self, dsn: str, timeout: float = 30.0):
        u = urlparse(dsn)
        if u.scheme not in ("postgres", "postgresql"):
            raise InterfaceError("DSN должен начинаться с postgresql://")
        self.user = unquote(u.username or "postgres")
        self.password = unquote(u.password or "")
        self.database = (u.path or "/postgres").lstrip("/") or "postgres"
        self.host = u.hostname or "127.0.0.1"
        self.port = u.port or 5432
        self.timeout = timeout
        self.params: dict[str, str] = {}
        self.status = b"I"
        self._sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._buf = b""
        self.closed = False
        try:
            self._startup()
        except Exception:
            self._sock.close()
            raise

    # ------------------------------------------------------------------ низкий уровень
    def _send(self, kind: bytes, payload: bytes = b""):
        self._sock.sendall(kind + struct.pack("!I", len(payload) + 4) + payload)

    def _recv_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self._sock.recv(max(65536, n - len(self._buf)))
            if not chunk:
                self.closed = True
                raise InterfaceError("Сервер PostgreSQL закрыл соединение")
            self._buf += chunk
        data, self._buf = self._buf[:n], self._buf[n:]
        return data

    def _read(self) -> tuple[bytes, bytes]:
        head = self._recv_exact(5)
        kind = head[:1]
        (length,) = struct.unpack("!I", head[1:])
        return kind, self._recv_exact(length - 4)

    @staticmethod
    def _cstr(s: str) -> bytes:
        return s.encode("utf-8") + b"\x00"

    @staticmethod
    def _error_fields(payload: bytes) -> dict[str, str]:
        fields = {}
        for part in payload.split(b"\x00"):
            if part:
                fields[chr(part[0])] = _decode_msg(part[1:])
        return fields

    def _raise(self, payload: bytes):
        fields = self._error_fields(payload)
        if fields.get("C") == "23505":
            raise UniqueViolation(fields)
        raise DatabaseError(fields)

    # ------------------------------------------------------------------ подключение
    def _startup(self):
        body = struct.pack("!I", 196608)
        for k, v in (("user", self.user), ("database", self.database), ("client_encoding", "UTF8"),
                     ("application_name", "portagraph"), ("TimeZone", "UTC")):
            body += self._cstr(k) + self._cstr(v)
        body += b"\x00"
        self._sock.sendall(struct.pack("!I", len(body) + 4) + body)
        scram = None
        while True:
            kind, payload = self._read()
            if kind == b"R":
                (code,) = struct.unpack("!I", payload[:4])
                if code == 0:
                    continue
                if code == 3:
                    self._send(b"p", self._cstr(self.password))
                elif code == 5:
                    salt = payload[4:8]
                    inner = hashlib.md5((self.password + self.user).encode()).hexdigest()
                    outer = hashlib.md5(inner.encode() + salt).hexdigest()
                    self._send(b"p", self._cstr("md5" + outer))
                elif code == 10:
                    mechs = [m.decode() for m in payload[4:].split(b"\x00") if m]
                    if "SCRAM-SHA-256" not in mechs:
                        raise InterfaceError(f"Неподдерживаемый метод SASL: {mechs}")
                    scram = _Scram(self.password)
                    first = scram.client_first().encode()
                    self._send(b"p", self._cstr("SCRAM-SHA-256") + struct.pack("!I", len(first)) + first)
                elif code == 11:
                    self._send(b"p", scram.client_final(payload[4:].decode()).encode())
                elif code == 12:
                    scram.verify_server(payload[4:].decode())
                else:
                    raise InterfaceError(f"Неподдерживаемый способ аутентификации: {code}")
            elif kind == b"S":
                k, v, _ = payload.split(b"\x00", 2)
                self.params[k.decode()] = v.decode()
            elif kind == b"K":
                pass
            elif kind == b"Z":
                self.status = payload[:1]
                return
            elif kind == b"E":
                self._raise(payload)
            elif kind == b"N":
                pass

    # ------------------------------------------------------------------ запросы
    def _collect(self) -> list[Result]:
        """Читает ответы до ReadyForQuery. Ошибку поднимает после синхронизации."""
        results: list[Result] = []
        columns: list[tuple[str, int]] = []
        rows: list[dict] = []
        error = None
        while True:
            kind, payload = self._read()
            if kind == b"T":
                (n,) = struct.unpack("!H", payload[:2])
                pos, columns = 2, []
                for _ in range(n):
                    end = payload.index(b"\x00", pos)
                    name = payload[pos:end].decode()
                    pos = end + 1
                    _tbl, _att, oid, _len, _mod, _fmt = struct.unpack("!IHIhih", payload[pos:pos + 18])
                    pos += 18
                    columns.append((name, oid))
                rows = []
            elif kind == b"D":
                (n,) = struct.unpack("!H", payload[:2])
                pos, row = 2, {}
                for i in range(n):
                    (ln,) = struct.unpack("!i", payload[pos:pos + 4])
                    pos += 4
                    raw = None
                    if ln >= 0:
                        raw = payload[pos:pos + ln]
                        pos += ln
                    name, oid = columns[i]
                    row[name] = _convert(oid, raw)
                rows.append(row)
            elif kind == b"C":
                results.append(Result([c[0] for c in columns], rows, payload.rstrip(b"\x00").decode()))
                columns, rows = [], []
            elif kind == b"I":  # пустой запрос
                results.append(Result([], [], ""))
            elif kind == b"E":
                error = payload
            elif kind == b"Z":
                self.status = payload[:1]
                if error is not None:
                    self._raise(error)
                return results
            # 1, 2, n, s, t, N, S, A – пропускаем

    def execute_script(self, sql: str) -> None:
        """Простой протокол: можно передать несколько команд через точку с запятой."""
        self._send(b"Q", self._cstr(sql))
        self._collect()

    def execute(self, sql: str, params: tuple | list = ()) -> Result:
        query, n = _convert_placeholders(sql)
        params = list(params)
        if n != len(params):
            raise InterfaceError(f"Ожидалось {n} параметров, передано {len(params)}")
        parse = self._cstr("") + self._cstr(query) + struct.pack("!H", 0)
        bind = self._cstr("") + self._cstr("") + struct.pack("!H", 0) + struct.pack("!H", len(params))
        for p in params:
            t = _to_text(p)
            bind += struct.pack("!i", -1) if t is None else struct.pack("!i", len(t)) + t
        bind += struct.pack("!H", 0)
        msg = (b"P" + struct.pack("!I", len(parse) + 4) + parse
               + b"B" + struct.pack("!I", len(bind) + 4) + bind
               + b"D" + struct.pack("!I", 6) + b"P\x00"
               + b"E" + struct.pack("!I", 9) + b"\x00" + struct.pack("!I", 0)
               + b"S" + struct.pack("!I", 4))
        self._sock.sendall(msg)
        results = self._collect()
        return results[-1] if results else Result([], [], "")

    @contextmanager
    def transaction(self):
        if self.status == b"T":  # вложенная транзакция – работаем в текущей
            yield self
            return
        self.execute_script("BEGIN")
        try:
            yield self
        except BaseException:
            if not self.closed:
                self.execute_script("ROLLBACK")
            raise
        else:
            self.execute_script("COMMIT")

    def reset(self):
        """Возвращает соединение в исходное состояние перед повторным использованием."""
        if self.status != b"I" and not self.closed:
            self.execute_script("ROLLBACK")

    def close(self):
        if not self.closed:
            try:
                self._send(b"X")
            except OSError:
                pass
            self._sock.close()
            self.closed = True


class _Scram:
    """Клиентская часть SCRAM-SHA-256 (RFC 5802 / RFC 7677)."""

    def __init__(self, password: str):
        self.password = password.encode("utf-8")
        self.nonce = base64.b64encode(os.urandom(18)).decode()
        self.first_bare = f"n=,r={self.nonce}"

    def client_first(self) -> str:
        return "n,," + self.first_bare

    def client_final(self, server_first: str) -> str:
        attrs = dict(kv.split("=", 1) for kv in server_first.split(","))
        nonce, salt, iters = attrs["r"], base64.b64decode(attrs["s"]), int(attrs["i"])
        if not nonce.startswith(self.nonce):
            raise InterfaceError("SCRAM: сервер вернул чужой nonce")
        salted = hashlib.pbkdf2_hmac("sha256", self.password, salt, iters)
        client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
        stored_key = hashlib.sha256(client_key).digest()
        final_wo_proof = f"c=biws,r={nonce}"
        self.auth_message = f"{self.first_bare},{server_first},{final_wo_proof}".encode()
        signature = hmac.new(stored_key, self.auth_message, hashlib.sha256).digest()
        proof = bytes(a ^ b for a, b in zip(client_key, signature))
        self.server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
        return f"{final_wo_proof},p={base64.b64encode(proof).decode()}"

    def verify_server(self, server_final: str):
        attrs = dict(kv.split("=", 1) for kv in server_final.split(","))
        expected = hmac.new(self.server_key, self.auth_message, hashlib.sha256).digest()
        if not hmac.compare_digest(base64.b64decode(attrs.get("v", "")), expected):
            raise InterfaceError("SCRAM: подпись сервера не совпала")
