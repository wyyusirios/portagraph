"""Приём веб-хуков от Git-хостингов (UC-14)."""
from __future__ import annotations

from flask import Blueprint, request

from ..services import webhook
from . import ctx, pipeline

bp = Blueprint("hooks", __name__, url_prefix="/hooks")


@bp.post("/repositories/<int:rid>")
def repository(rid):
    result = webhook.handle(ctx(), pipeline(), rid, request.get_data(cache=False), request.headers)
    return result, 202 if result.get("status") == "accepted" else 200
