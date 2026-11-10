"""Регистрация и вход. Пароли хранятся только в виде хэша (scrypt через werkzeug)."""
from __future__ import annotations

import re

from werkzeug.security import check_password_hash, generate_password_hash

from ..db import UniqueViolation
from .context import Context
from .errors import BadRequest, Conflict, Unauthorized

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def register(ctx: Context, email: str, password: str, full_name: str) -> dict:
    email = (email or "").strip().lower()
    full_name = (full_name or "").strip()
    if not EMAIL.match(email):
        raise BadRequest("Укажите корректный email")
    if len(password or "") < 8:
        raise BadRequest("Пароль должен быть не короче 8 символов")
    if not full_name:
        raise BadRequest("Укажите имя")
    try:
        return ctx.db.one(
            "INSERT INTO users(email, password_hash, full_name) VALUES (%s, %s, %s) RETURNING id, email, full_name",
            email, generate_password_hash(password), full_name[:150])
    except UniqueViolation:
        raise Conflict("Пользователь с таким email уже зарегистрирован") from None


def authenticate(ctx: Context, email: str, password: str) -> dict:
    user = ctx.db.one("SELECT id, email, full_name, password_hash FROM users WHERE email = %s", (email or "").strip().lower())
    if not user or not check_password_hash(user["password_hash"], password or ""):
        raise Unauthorized("Неверный email или пароль")
    return {k: user[k] for k in ("id", "email", "full_name")}


def get_user(ctx: Context, user_id: int) -> dict | None:
    return ctx.db.one("SELECT id, email, full_name, created_at FROM users WHERE id = %s", user_id)
