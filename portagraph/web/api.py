"""JSON API для интерактивных экранов (граф, ассистент, impact, прогресс анализа)."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..services import access, assistant, graph_service, impact_service, projects, repos, webhook
from ..services.errors import BadRequest, NotFound
from . import ctx, login_required, pipeline

bp = Blueprint("api", __name__, url_prefix="/api")


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise BadRequest("Ожидается JSON-объект")
    return data


@bp.get("/me")
@login_required
def me():
    return {"id": g.user["id"], "email": g.user["email"], "full_name": g.user["full_name"]}


@bp.get("/projects")
@login_required
def project_list():
    return jsonify(projects.list_for_user(ctx(), g.user["id"]))


@bp.get("/projects/<int:pid>")
@login_required
def project(pid):
    return projects.get(ctx(), pid, g.user["id"])


@bp.get("/projects/<int:pid>/repositories")
@login_required
def repository_list(pid):
    return jsonify(repos.list_repos(ctx(), pid, g.user["id"]))


@bp.post("/projects/<int:pid>/repositories/git")
@login_required
def repository_git(pid):
    b = _body()
    urls = b.get("urls") or []
    if isinstance(urls, str):
        urls = urls.split()
    return jsonify(repos.connect_git(ctx(), pid, g.user["id"], urls, b.get("token")))


@bp.get("/projects/<int:pid>/repositories/<int:rid>/webhook")
@login_required
def repository_webhook(pid, rid):
    return webhook.webhook_info(ctx(), pid, g.user["id"], rid)


# ---------------------------------------------------------------- анализ
@bp.post("/projects/<int:pid>/analysis")
@login_required
def analysis_start(pid):
    return pipeline().enqueue(pid, "MANUAL", g.user["id"]), 202


@bp.get("/projects/<int:pid>/runs/<int:rid>")
@login_required
def run_status(pid, rid):
    access.require(ctx(), pid, g.user["id"])
    run = ctx().db.one("SELECT id, status, progress, stage_message, started_at, finished_at, error_message, stats, log, trigger_type "
                       "FROM analysis_runs WHERE id = %s AND project_id = %s", rid, pid)
    if not run:
        raise NotFound("Запуск не найден")
    return run


@bp.post("/projects/<int:pid>/runs/cancel")
@login_required
def run_cancel(pid):
    return {"cancelled": pipeline().cancel(pid, g.user["id"])}


# ---------------------------------------------------------------- граф
@bp.get("/projects/<int:pid>/graph/overview")
@login_required
def graph_overview(pid):
    return graph_service.overview(ctx(), pid, g.user["id"])


@bp.get("/projects/<int:pid>/graph/detailed")
@login_required
def graph_detailed(pid):
    return graph_service.detailed(ctx(), pid, g.user["id"], request.args.get("repo", type=int),
                                  request.args.get("focus", type=int), request.args.get("depth", 2, type=int))


@bp.get("/projects/<int:pid>/nodes/search")
@login_required
def node_search(pid):
    types = [t for t in request.args.get("types", "").split(",") if t] or None
    return jsonify(graph_service.search_nodes(ctx(), pid, g.user["id"], request.args.get("q", ""), types))


@bp.get("/projects/<int:pid>/nodes/<int:nid>")
@login_required
def node(pid, nid):
    return graph_service.node_detail(ctx(), pid, g.user["id"], nid)


@bp.post("/projects/<int:pid>/verifications")
@login_required
def verify(pid):
    b = _body()
    return graph_service.verify(ctx(), pid, g.user["id"], b.get("subject", ""), int(b.get("id") or 0),
                                b.get("decision", ""), b.get("description"))


# ---------------------------------------------------------------- ассистент
@bp.post("/projects/<int:pid>/assistant")
@login_required
def ask(pid):
    b = _body()
    return assistant.ask(ctx(), pid, g.user["id"], b.get("session_id"), b.get("question", ""))


@bp.get("/projects/<int:pid>/assistant/sessions")
@login_required
def chat_sessions(pid):
    return jsonify(assistant.sessions(ctx(), pid, g.user["id"]))


# ---------------------------------------------------------------- impact
@bp.post("/projects/<int:pid>/impact")
@login_required
def impact(pid):
    b = _body()
    return impact_service.run(ctx(), pid, g.user["id"], b.get("node_ids") or [], b.get("depth", 3), b.get("description", ""))


@bp.get("/projects/<int:pid>/impact")
@login_required
def impact_history(pid):
    return jsonify(impact_service.history(ctx(), pid, g.user["id"]))
