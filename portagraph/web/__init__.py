"""Веб-слой: авторизация по сессии, CSRF, обработка ошибок, фильтры шаблонов."""
from __future__ import annotations

import datetime as dt
import functools
import secrets

from flask import (Flask, abort, current_app, flash, g, jsonify, redirect, render_template, request, session,
                   url_for)

from .. import __version__
from ..services import access, auth, projects
from ..services.errors import AppError, Forbidden, NotFound, Unauthorized

try:
    from zoneinfo import ZoneInfo
    import os
    LOCAL_TZ = ZoneInfo(os.environ.get("PORTAGRAPH_TZ", "Europe/Moscow"))
except Exception:  # noqa: BLE001 — на Windows без tzdata используем фиксированное смещение
    LOCAL_TZ = dt.timezone(dt.timedelta(hours=3))

ROLE_RU = access.ROLE_RU
REPO_ROLE_RU = {"SERVICE": "Сервис", "FRONTEND": "Фронтенд", "LIBRARY": "Библиотека", "INFRASTRUCTURE": "Инфраструктура",
                "DOCUMENTATION": "Документация", "UNKNOWN": "Не определено"}
RUN_STATUS_RU = {"QUEUED": "В очереди", "FETCHING": "Загрузка исходников", "INDEXING": "Индексация", "ANALYZING": "Анализ",
                 "BUILDING_GRAPH": "Построение графа", "COMPLETED": "Завершён", "FAILED": "Ошибка", "CANCELLED": "Отменён"}
REPO_STATUS_RU = {"CONNECTED": "Подключён", "FETCHING": "Загрузка", "READY": "Готов", "ERROR": "Ошибка"}
SOURCE_RU = {"git": "Git", "zip": "ZIP-архив", "demo": "Демо", "local": "Локальная папка"}


def ctx():
    return current_app.extensions["portagraph"]["ctx"]


def pipeline():
    return current_app.extensions["portagraph"]["pipeline"]


def wants_json() -> bool:
    return request.path.startswith(("/api/", "/hooks/")) or request.accept_mimetypes.best == "application/json"


def login_required(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None:
            if wants_json():
                raise Unauthorized("Войдите в систему")
            return redirect(url_for("pages.login", next=request.full_path if request.method == "GET" else None))
        return view(*args, **kwargs)
    return wrapper


def load_project(pid: int) -> dict:
    """Проект для страниц рабочего пространства (сайдбар, права)."""
    p = projects.get(ctx(), pid, g.user["id"])
    g.project = p
    return p


def csrf_token() -> str:
    tok = session.get("_csrf")
    if not tok:
        tok = session["_csrf"] = secrets.token_urlsafe(32)
    return tok


def _fmt_dt(value, fmt="%d.%m.%Y %H:%M"):
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = dt.datetime.fromisoformat(value)
        except ValueError:
            return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(LOCAL_TZ).strftime(fmt)


def _ago(value):
    if not value:
        return "никогда"
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    sec = int((dt.datetime.now(dt.timezone.utc) - value).total_seconds())
    if sec < 60:
        return "только что"
    if sec < 3600:
        return f"{sec // 60} мин назад"
    if sec < 86400:
        return f"{sec // 3600} ч назад"
    if sec < 86400 * 7:
        return f"{sec // 86400} дн назад"
    return _fmt_dt(value, "%d.%m.%Y")


def _plural(n, one, few, many):
    n = abs(int(n or 0))
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} {few}"
    return f"{n} {many}"


def _initials(name: str) -> str:
    parts = [p for p in (name or "?").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def register(app: Flask) -> None:
    from . import api, hooks, pages

    app.register_blueprint(pages.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(hooks.bp)

    app.jinja_env.filters.update(dt=_fmt_dt, ago=_ago, initials=_initials)
    app.jinja_env.globals.update(csrf_token=csrf_token, plural=_plural, version=__version__, ROLE_RU=ROLE_RU,
                                 REPO_ROLE_RU=REPO_ROLE_RU, RUN_STATUS_RU=RUN_STATUS_RU, REPO_STATUS_RU=REPO_STATUS_RU,
                                 SOURCE_RU=SOURCE_RU)

    @app.before_request
    def _load_user():
        g.user = None
        g.project = None
        uid = session.get("uid")
        if uid:
            g.user = auth.get_user(ctx(), uid)
            if g.user is None:
                session.clear()
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not request.path.startswith("/hooks/"):
            sent = request.headers.get("X-CSRF-Token") or request.form.get("_csrf")
            if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
                if wants_json():
                    return jsonify(error="Сессия устарела — обновите страницу"), 400
                flash("Сессия устарела — повторите действие", "error")
                return redirect(request.referrer or url_for("pages.index"))

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    @app.errorhandler(AppError)
    def _app_error(e: AppError):
        if wants_json():
            return jsonify(error=e.message), e.status
        if isinstance(e, (NotFound, Forbidden)):
            return render_template("errors/error.html", code=e.status, message=e.message), e.status
        flash(e.message, "error")
        return redirect(request.referrer or url_for("pages.index"))

    @app.errorhandler(404)
    def _not_found(e):
        if wants_json():
            return jsonify(error="Не найдено"), 404
        return render_template("errors/error.html", code=404, message="Такой страницы нет"), 404

    @app.errorhandler(413)
    def _too_large(e):
        msg = f"Файл больше {ctx().settings.max_upload_mb} МБ"
        if wants_json():
            return jsonify(error=msg), 413
        flash(msg, "error")
        return redirect(request.referrer or url_for("pages.index"))

    @app.errorhandler(500)
    def _server_error(e):
        if wants_json():
            return jsonify(error="Внутренняя ошибка сервера — подробности в журнале"), 500
        return render_template("errors/error.html", code=500, message="Внутренняя ошибка сервера. Подробности — в журнале приложения."), 500

    _ = abort  # реэкспорт для блюпринтов
