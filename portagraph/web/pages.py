"""Страницы интерфейса (экраны Э-01…Э-13)."""
from __future__ import annotations

import re

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, session, url_for
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer_for_filename
from pygments.util import ClassNotFound

from ..services import (access, assistant, auth, docs_service, graph_service, impact_service, projects, repos,
                        webhook)
from ..services.errors import AppError, BadRequest, NotFound
from . import ctx, load_project, login_required, pipeline

bp = Blueprint("pages", __name__)

LEXER_ALIAS = {"python": "python", "java": "java", "kotlin": "kotlin", "typescript": "typescript", "javascript": "javascript",
               "go": "go", "csharp": "csharp", "scala": "scala", "yaml": "yaml", "json": "json", "markdown": "markdown",
               "xml": "xml", "sql": "sql", "shell": "bash", "dockerfile": "docker", "terraform": "terraform", "toml": "toml",
               "gradle": "groovy", "properties": "properties", "html": "html", "css": "css", "ruby": "ruby", "php": "php"}


def _safe_next(target: str | None) -> str | None:
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target.rstrip("?")
    return None


# ---------------------------------------------------------------- вход и регистрация (Э-01)
@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for(".projects_list"))
    from ..services.seed import DEMO_PASSWORD, USERS
    demo = [{"email": e, "name": n, "role": ROLE} for e, n, ROLE in USERS] if ctx().settings.demo_seed else []
    if request.method == "POST":
        try:
            user = auth.authenticate(ctx(), request.form.get("email", ""), request.form.get("password", ""))
        except AppError as e:
            flash(e.message, "error")
            return render_template("auth/login.html", email=request.form.get("email", ""), demo=demo, demo_password=DEMO_PASSWORD), 401
        session.clear()
        session["uid"] = user["id"]
        session.permanent = True
        return redirect(_safe_next(request.args.get("next")) or url_for(".projects_list"))
    return render_template("auth/login.html", email="", demo=demo, demo_password=DEMO_PASSWORD)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for(".projects_list"))
    form = {"email": "", "full_name": ""}
    if request.method == "POST":
        form = {k: request.form.get(k, "") for k in ("email", "full_name")}
        if request.form.get("password") != request.form.get("password2"):
            flash("Пароли не совпадают", "error")
        else:
            try:
                user = auth.register(ctx(), form["email"], request.form.get("password", ""), form["full_name"])
                session.clear()
                session["uid"] = user["id"]
                flash("Аккаунт создан. Создайте первый проект", "success")
                return redirect(url_for(".projects_list"))
            except AppError as e:
                flash(e.message, "error")
    return render_template("auth/register.html", form=form)


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for(".login"))


@bp.get("/")
def index():
    return redirect(url_for(".projects_list") if g.user else url_for(".login"))


@bp.get("/health")
def health():
    ctx().db.scalar("SELECT 1")
    return {"status": "ok"}


# ---------------------------------------------------------------- проекты (Э-02, Э-03)
@bp.get("/projects")
@login_required
def projects_list():
    from flask import current_app
    items = projects.list_for_user(ctx(), g.user["id"])
    return render_template("projects/list.html", projects=items, seeding=current_app.extensions["portagraph"]["seeding"])


@bp.post("/projects")
@login_required
def projects_create():
    p = projects.create(ctx(), g.user["id"], request.form.get("name", ""), request.form.get("description"))
    flash(f"Проект «{p['name']}» создан. Подключите репозитории", "success")
    return redirect(url_for(".repositories", pid=p["id"], new=1))


@bp.get("/projects/new")
@login_required
def projects_new():
    return render_template("projects/new.html")


# ---------------------------------------------------------------- обзор проекта
@bp.get("/p/<int:pid>")
@login_required
def overview(pid):
    p = load_project(pid)
    c = ctx()
    run = graph_service.latest_run(c, pid)
    last = c.db.one("SELECT * FROM analysis_runs WHERE project_id = %s ORDER BY id DESC LIMIT 1", pid)
    history = c.db.all("SELECT id, status, stats, finished_at, trigger_type FROM analysis_runs WHERE project_id = %s "
                       "AND status = 'COMPLETED' ORDER BY id DESC LIMIT 12", pid)[::-1]
    repo_rows = repos.list_repos(c, pid, g.user["id"])
    counts = {}
    if run:
        for r in c.db.all("SELECT type, count(*) AS n FROM graph_nodes WHERE run_id = %s GROUP BY type", run["id"]):
            counts[r["type"]] = r["n"]
    weak = c.db.all("""SELECT e.id, e.type, e.confidence, s.name AS sname, t.name AS tname, s.id AS sid
                         FROM graph_edges e JOIN graph_nodes s ON s.id = e.source_node_id JOIN graph_nodes t ON t.id = e.target_node_id
                        WHERE e.run_id = %s AND e.type <> 'IMPORTS' AND e.confidence < 0.7 AND NOT e.verified AND NOT e.rejected
                        ORDER BY e.confidence""", run["id"]) if run else []
    hubs = c.db.all("""SELECT t.id, t.name, t.type, count(*) AS n FROM graph_edges e JOIN graph_nodes t ON t.id = e.target_node_id
                        WHERE e.run_id = %s AND e.type IN ('CALLS_HTTP','DEPENDS_ON','CONSUMES','READS_WRITES') AND NOT e.rejected
                          AND t.type IN ('SERVICE','REPOSITORY','DATABASE')
                        GROUP BY t.id, t.name, t.type ORDER BY n DESC, t.name LIMIT 5""", run["id"]) if run else []
    reports = impact_service.history(c, pid, g.user["id"])[:4]
    docs = docs_service.list_docs(c, pid, g.user["id"])[:4]
    members = projects.members(c, pid, g.user["id"])
    health = graph_service.repo_health(c, pid, g.user["id"])
    return render_template("workspace/overview.html", p=p, run=run, last=last, history=history, repos=repo_rows, counts=counts, health=health,
                           weak=weak, hubs=hubs, reports=reports, docs=docs, members=members, nav="overview")


# ---------------------------------------------------------------- репозитории (Э-04, Э-05)
@bp.get("/p/<int:pid>/repositories")
@login_required
def repositories(pid):
    p = load_project(pid)
    rows = repos.list_repos(ctx(), pid, g.user["id"])
    last = ctx().db.one("SELECT * FROM analysis_runs WHERE project_id = %s ORDER BY id DESC LIMIT 1", pid)
    results = session.pop("git_results", None)
    health = graph_service.repo_health(ctx(), pid, g.user["id"])
    return render_template("workspace/repositories.html", p=p, repos=rows, last=last, results=results, health=health,
                           new=request.args.get("new"), allow_local=ctx().settings.allow_local_paths,
                           max_mb=ctx().settings.max_upload_mb, nav="repositories")


@bp.post("/p/<int:pid>/repositories/git")
@login_required
def repo_git(pid):
    urls = re.split(r"[\r\n,;]+", request.form.get("urls", ""))
    res = repos.connect_git(ctx(), pid, g.user["id"], urls, request.form.get("token"))
    session["git_results"] = res
    ok = sum(1 for r in res if r["ok"])
    flash(f"Подключено репозиториев: {ok} из {len(res)}", "success" if ok == len(res) else "warn")
    return redirect(url_for(".repositories", pid=pid))


@bp.post("/p/<int:pid>/repositories/zip")
@login_required
def repo_zip(pid):
    f = request.files.get("archive")
    if not f or not f.filename:
        raise BadRequest("Выберите ZIP-архив")
    if not f.filename.lower().endswith(".zip"):
        raise BadRequest("Поддерживаются только архивы .zip")
    r = repos.connect_zip(ctx(), pid, g.user["id"], f.filename, f.stream, request.form.get("name"))
    flash(f"Архив загружен как репозиторий «{r['name']}»", "success")
    return redirect(url_for(".repositories", pid=pid))


@bp.post("/p/<int:pid>/repositories/local")
@login_required
def repo_local(pid):
    r = repos.connect_local(ctx(), pid, g.user["id"], request.form.get("path", ""))
    flash(f"Папка подключена как репозиторий «{r['name']}»", "success")
    return redirect(url_for(".repositories", pid=pid))


@bp.post("/p/<int:pid>/repositories/demo")
@login_required
def repo_demo(pid):
    added = repos.connect_demo(ctx(), pid, g.user["id"])
    flash(f"Подключено демо-репозиториев ShopFlow: {len(added)}" if added else "Демо-репозитории уже подключены", "success")
    return redirect(url_for(".repositories", pid=pid))


@bp.post("/p/<int:pid>/repositories/<int:rid>/delete")
@login_required
def repo_delete(pid, rid):
    repos.disconnect(ctx(), pid, g.user["id"], rid)
    flash("Репозиторий отключён. Граф обновится при следующем анализе", "success")
    return redirect(url_for(".repositories", pid=pid))


@bp.post("/p/<int:pid>/analyze")
@login_required
def analyze(pid):
    run = pipeline().enqueue(pid, "MANUAL", g.user["id"])
    return redirect(url_for(".run_view", pid=pid, rid=run["id"]))


@bp.post("/p/<int:pid>/sync")
@login_required
def sync(pid):
    run = webhook.sync(ctx(), pipeline(), pid, g.user["id"])
    return redirect(url_for(".run_view", pid=pid, rid=run["id"]))


@bp.post("/p/<int:pid>/cancel")
@login_required
def cancel(pid):
    flash("Анализ отменён" if pipeline().cancel(pid, g.user["id"]) else "Нет анализа, который можно отменить", "success")
    return redirect(request.referrer or url_for(".overview", pid=pid))


# ---------------------------------------------------------------- прогресс анализа (Э-06)
@bp.get("/p/<int:pid>/runs")
@login_required
def runs(pid):
    p = load_project(pid)
    rows = ctx().db.all("SELECT * FROM analysis_runs WHERE project_id = %s ORDER BY id DESC LIMIT 50", pid)
    return render_template("workspace/runs.html", p=p, runs=rows, nav="runs")


@bp.get("/p/<int:pid>/runs/<int:rid>")
@login_required
def run_view(pid, rid):
    p = load_project(pid)
    run = ctx().db.one("SELECT * FROM analysis_runs WHERE id = %s AND project_id = %s", rid, pid)
    if not run:
        raise NotFound("Запуск анализа не найден")
    return render_template("workspace/run.html", p=p, run=run, nav="runs")


# ---------------------------------------------------------------- карта и граф (Э-07, Э-08)
@bp.get("/p/<int:pid>/map")
@login_required
def system_map(pid):
    p = load_project(pid)
    run = graph_service.latest_run(ctx(), pid)
    return render_template("workspace/map.html", p=p, run=run, nav="map", focus=request.args.get("node", type=int))


@bp.get("/p/<int:pid>/graph")
@login_required
def code_graph(pid):
    p = load_project(pid)
    run = graph_service.latest_run(ctx(), pid)
    repo_rows = [r for r in repos.list_repos(ctx(), pid, g.user["id"])]
    return render_template("workspace/graph.html", p=p, run=run, repos=repo_rows, nav="graph",
                           repo_id=request.args.get("repo", type=int), focus=request.args.get("focus", type=int))


# ---------------------------------------------------------------- исходный код (Э-09)
@bp.get("/p/<int:pid>/code")
@login_required
def code_browser(pid):
    p = load_project(pid)
    repo_rows = repos.list_repos(ctx(), pid, g.user["id"])
    rid = request.args.get("repo", type=int) or (repo_rows[0]["id"] if repo_rows else None)
    files = graph_service.file_tree(ctx(), pid, g.user["id"], rid) if rid else []
    return render_template("workspace/code.html", p=p, repos=repo_rows, repo_id=rid, files=files, file=None, nav="code")


def _lexer(path: str, language: str | None, content: str):
    try:
        if language and language in LEXER_ALIAS:
            return get_lexer_by_name(LEXER_ALIAS[language])
        return guess_lexer_for_filename(path, content[:4000])
    except ClassNotFound:
        return TextLexer()


@bp.get("/p/<int:pid>/files/<int:fid>")
@login_required
def file_view(pid, fid):
    p = load_project(pid)
    f = graph_service.get_file(ctx(), pid, g.user["id"], fid)
    html = highlight(f["content"] or "", _lexer(f["path"], f["language"], f["content"] or ""),
                     HtmlFormatter(linespans="L", cssclass="hl", wrapcode=True))
    files = graph_service.file_tree(ctx(), pid, g.user["id"], f["repository_id"])
    repo_rows = repos.list_repos(ctx(), pid, g.user["id"])
    lines = request.args.get("l", "")
    m = re.match(r"^(\d+)(?:-(\d+))?$", lines)
    sel = (int(m.group(1)), int(m.group(2) or m.group(1))) if m else None
    return render_template("workspace/code.html", p=p, repos=repo_rows, repo_id=f["repository_id"], files=files, file=f,
                           code_html=html, sel=sel, nav="code")


# ---------------------------------------------------------------- ассистент (Э-10)
@bp.get("/p/<int:pid>/assistant")
@bp.get("/p/<int:pid>/assistant/<int:sid>")
@login_required
def assistant_view(pid, sid=None):
    p = load_project(pid)
    c = ctx()
    sessions = assistant.sessions(c, pid, g.user["id"])
    msgs = assistant.messages(c, pid, g.user["id"], sid) if sid else []
    run = graph_service.latest_run(c, pid)
    return render_template("workspace/assistant.html", p=p, sessions=sessions, sid=sid, messages=msgs, run=run,
                           mode_note=assistant.MODE_NOTE, nav="assistant")


# ---------------------------------------------------------------- impact analysis (Э-11)
@bp.get("/p/<int:pid>/impact")
@login_required
def impact_view(pid):
    p = load_project(pid)
    run = graph_service.latest_run(ctx(), pid)
    hist = impact_service.history(ctx(), pid, g.user["id"])
    pre = request.args.get("node", type=int)
    pre_node = ctx().db.one("SELECT id, name, type FROM graph_nodes WHERE id = %s AND project_id = %s", pre, pid) if pre else None
    return render_template("workspace/impact.html", p=p, run=run, history=hist, report=None, pre_node=pre_node, nav="impact")


@bp.get("/p/<int:pid>/impact/<int:report_id>")
@login_required
def impact_report(pid, report_id):
    p = load_project(pid)
    rep = impact_service.get(ctx(), pid, g.user["id"], report_id)
    hist = impact_service.history(ctx(), pid, g.user["id"])
    run = graph_service.latest_run(ctx(), pid)
    return render_template("workspace/impact.html", p=p, run=run, history=hist, report=rep, pre_node=None, nav="impact")


# ---------------------------------------------------------------- документация (Э-12)
@bp.get("/p/<int:pid>/docs")
@login_required
def docs(pid):
    p = load_project(pid)
    rows = docs_service.list_docs(ctx(), pid, g.user["id"])
    run = graph_service.latest_run(ctx(), pid)
    services = ctx().db.all("SELECT id, name FROM graph_nodes WHERE run_id = %s AND type = 'SERVICE' ORDER BY name", run["id"]) if run else []
    return render_template("workspace/docs.html", p=p, docs=rows, doc=None, run=run, services=services, nav="docs")


@bp.post("/p/<int:pid>/docs")
@login_required
def docs_generate(pid):
    d = docs_service.generate(ctx(), pid, g.user["id"], request.form.get("type", ""), request.form.get("node_id", type=int))
    flash("Документ сформирован как черновик", "success")
    return redirect(url_for(".doc_view", pid=pid, doc_id=d["id"]))


@bp.get("/p/<int:pid>/docs/<int:doc_id>")
@login_required
def doc_view(pid, doc_id):
    p = load_project(pid)
    d = docs_service.get(ctx(), pid, g.user["id"], doc_id)
    rows = docs_service.list_docs(ctx(), pid, g.user["id"])
    return render_template("workspace/docs.html", p=p, docs=rows, doc=d, run=None, services=[], nav="docs",
                           edit=request.args.get("edit") == "1")


@bp.post("/p/<int:pid>/docs/<int:doc_id>")
@login_required
def doc_update(pid, doc_id):
    docs_service.update(ctx(), pid, g.user["id"], doc_id, request.form.get("content_md", ""))
    flash("Изменения сохранены", "success")
    return redirect(url_for(".doc_view", pid=pid, doc_id=doc_id))


@bp.post("/p/<int:pid>/docs/<int:doc_id>/approve")
@login_required
def doc_approve(pid, doc_id):
    docs_service.approve(ctx(), pid, g.user["id"], doc_id)
    flash("Документ утверждён", "success")
    return redirect(url_for(".doc_view", pid=pid, doc_id=doc_id))


@bp.post("/p/<int:pid>/docs/<int:doc_id>/delete")
@login_required
def doc_delete(pid, doc_id):
    docs_service.delete(ctx(), pid, g.user["id"], doc_id)
    flash("Документ удалён", "success")
    return redirect(url_for(".docs", pid=pid))


@bp.get("/p/<int:pid>/docs/<int:doc_id>/export")
@login_required
def doc_export(pid, doc_id):
    d = docs_service.get(ctx(), pid, g.user["id"], doc_id)
    from urllib.parse import quote
    name = docs_service.filename(d)
    return Response(d["content_md"], mimetype="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=\"document.md\"; filename*=UTF-8''{quote(name)}"})


# ---------------------------------------------------------------- настройки и участники (Э-13)
@bp.get("/p/<int:pid>/settings")
@login_required
def settings(pid):
    p = load_project(pid)
    members = projects.members(ctx(), pid, g.user["id"])
    return render_template("workspace/settings.html", p=p, members=members, roles=access.ROLES, nav="settings")


@bp.post("/p/<int:pid>/settings")
@login_required
def settings_update(pid):
    projects.update(ctx(), pid, g.user["id"], request.form.get("name", ""), request.form.get("description"))
    flash("Проект обновлён", "success")
    return redirect(url_for(".settings", pid=pid))


@bp.post("/p/<int:pid>/members")
@login_required
def member_add(pid):
    projects.add_member(ctx(), pid, g.user["id"], request.form.get("email", ""), request.form.get("role", ""))
    flash("Участник добавлен", "success")
    return redirect(url_for(".settings", pid=pid))


@bp.post("/p/<int:pid>/members/<int:mid>")
@login_required
def member_role(pid, mid):
    projects.change_role(ctx(), pid, g.user["id"], mid, request.form.get("role", ""))
    flash("Роль изменена", "success")
    return redirect(url_for(".settings", pid=pid))


@bp.post("/p/<int:pid>/members/<int:mid>/delete")
@login_required
def member_remove(pid, mid):
    projects.remove_member(ctx(), pid, g.user["id"], mid)
    flash("Участник удалён из проекта", "success")
    return redirect(url_for(".settings", pid=pid))


@bp.post("/p/<int:pid>/archive")
@login_required
def archive(pid):
    projects.archive(ctx(), pid, g.user["id"])
    flash("Проект перенесён в архив", "success")
    return redirect(url_for(".projects_list"))


_ = abort
