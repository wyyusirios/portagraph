"""Генерация архитектурной документации из графа (UC-12).

В демо-режиме документы собираются по шаблонам из данных графа: назначения
репозиториев, стек, эндпоинты, связи с уверенностью и доказательствами.
Документ создаётся как черновик; архитектор утверждает его. После нового
анализа документы прошлых версий графа помечаются «Устарел».
"""
from __future__ import annotations

import datetime as dt
import re

import markdown as md

from . import access, graph_service
from .context import Context
from .errors import BadRequest, NotFound

TYPES = {"ARCHITECTURE_OVERVIEW": "Обзор архитектуры", "ONBOARDING_GUIDE": "Гайд для онбординга", "SERVICE_CARD": "Карточка сервиса"}
STATUS_RU = {"DRAFT": "Черновик", "APPROVED": "Утверждён", "OUTDATED": "Устарел"}
ROLE_RU = {"SERVICE": "Сервис", "FRONTEND": "Фронтенд", "LIBRARY": "Библиотека", "INFRASTRUCTURE": "Инфраструктура",
           "DOCUMENTATION": "Документация", "UNKNOWN": "Не определено"}
EDGE_RU = graph_service.EDGE_RU


def render_markdown(text: str) -> str:
    """Markdown → HTML без пропуска «сырого» HTML (документ могут редактировать участники проекта)."""
    m = md.Markdown(extensions=["tables", "fenced_code", "sane_lists"])
    m.preprocessors.deregister("html_block")
    m.inlinePatterns.deregister("html")
    return re.sub(r'(href|src)="\s*(javascript|data|vbscript):[^"]*"', r'\1="#"', m.convert(text), flags=re.I)


def _model(ctx: Context, project_id: int) -> dict:
    run = graph_service.require_run(ctx, project_id)
    project = ctx.db.one("SELECT * FROM projects WHERE id = %s", project_id)
    repos = ctx.db.all("""SELECT r.*, (SELECT count(*) FROM source_files f WHERE f.repository_id = r.id) AS files
                            FROM repositories r WHERE r.project_id = %s ORDER BY r.name""", project_id)
    nodes = ctx.db.all("""SELECT n.id, n.type, n.name, n.qualified_name, n.description, n.metadata, n.confidence, n.verified,
                                 n.repository_id, r.name AS repo_name
                            FROM graph_nodes n LEFT JOIN repositories r ON r.id = n.repository_id
                           WHERE n.run_id = %s""", run["id"])
    edges = ctx.db.all("""SELECT e.type, e.confidence, e.verified, e.evidence, s.id AS sid, s.name AS sname, s.type AS stype,
                                 t.id AS tid, t.name AS tname, t.type AS ttype
                            FROM graph_edges e JOIN graph_nodes s ON s.id = e.source_node_id JOIN graph_nodes t ON t.id = e.target_node_id
                           WHERE e.run_id = %s AND NOT e.rejected AND e.type <> 'IMPORTS' ORDER BY s.name, e.type, t.name""", run["id"])
    return {"run": run, "project": project, "repos": repos, "nodes": nodes, "edges": edges}


def _conf(c: float, verified: bool) -> str:
    return "подтверждено" if verified else (f"{c:.2f}" + (" ⚠ проверить" if c < 0.7 else ""))


def _ev(e: dict) -> str:
    ev = e["evidence"][0] if e["evidence"] else None
    return f"`{ev['repo']}/{ev['path']}:{ev.get('line') or 1}`" if ev else "—"


def _header(m: dict, title: str) -> list[str]:
    run = m["run"]
    when = run["finished_at"].strftime("%d.%m.%Y %H:%M") if run["finished_at"] else ""
    return [f"# {title}", "",
            f"> Сформировано PortaGraph по графу анализа №{run['id']} от {when} (UTC). "
            "Демо-режим: текст собран по шаблону из данных графа. Связи с уверенностью ниже 0,7 требуют проверки.", ""]


def _services(m: dict) -> list[dict]:
    return sorted([n for n in m["nodes"] if n["type"] == "SERVICE"], key=lambda n: n["name"])


def overview(m: dict) -> tuple[str, str]:
    p = m["project"]
    title = f"Обзор архитектуры — {p['name']}"
    out = _header(m, title)
    services = _services(m)
    stores = [n for n in m["nodes"] if n["type"] == "DATABASE"]
    topics = [n for n in m["nodes"] if n["type"] == "MESSAGE_QUEUE"]
    ext = [n for n in m["nodes"] if n["type"] == "EXTERNAL_SYSTEM"]
    out += ["## 1. Назначение системы", "", p["description"] or f"Система {p['name']}.", "",
            f"Система состоит из {len(m['repos'])} репозиториев: {len(services)} сервисов и фронтендов, "
            f"{sum(1 for r in m['repos'] if r['detected_role'] == 'LIBRARY')} библиотек, "
            f"{sum(1 for r in m['repos'] if r['detected_role'] == 'INFRASTRUCTURE')} инфраструктурных. "
            f"Хранилищ данных: {len(stores)}, топиков сообщений: {len(topics)}, внешних систем: {len(ext)}.", ""]
    out += ["## 2. Репозитории", "", "| Репозиторий | Роль | Назначение | Файлов |", "|---|---|---|---|"]
    for r in m["repos"]:
        out.append(f"| {r['name']} | {ROLE_RU.get(r['detected_role'], r['detected_role'])} ({r['role_confidence']:.2f}) | "
                   f"{(r['purpose_summary'] or '—').replace('|', '/')} | {r['files']} |")
    out += ["", "## 3. Сервисы", ""]
    for s in services:
        meta = s["metadata"] or {}
        out.append(f"### {s['name']}")
        out.append("")
        out.append(s["description"] or "Назначение не определено.")
        if meta.get("stack"):
            out.append("")
            out.append("Стек: " + ", ".join(meta["stack"]) + ".")
        if meta.get("endpoints"):
            out.append(f"Эндпоинтов API: {len(meta['endpoints'])}.")
        out.append("")
    out += ["## 4. Взаимодействия", "", "| Откуда | Связь | Куда | Уверенность | Доказательство |", "|---|---|---|---|---|"]
    for e in m["edges"]:
        if e["type"] == "CONTAINS":
            continue
        out.append(f"| {e['sname']} | {EDGE_RU.get(e['type'], e['type'])} | {e['tname']} | {_conf(e['confidence'], e['verified'])} | {_ev(e)} |")
    if topics:
        out += ["", "## 5. Асинхронный обмен", ""]
        for t in topics:
            pubs = [e["sname"] for e in m["edges"] if e["tid"] == t["id"] and e["type"] == "PUBLISHES"]
            subs = [e["sname"] for e in m["edges"] if e["tid"] == t["id"] and e["type"] == "CONSUMES"]
            out.append(f"- **{t['name']}**: публикует {', '.join(pubs) or '—'}; читает {', '.join(subs) or '—'}.")
    if stores or ext:
        out += ["", "## 6. Данные и внешние системы", ""]
        for n in stores + ext:
            users = sorted({e["sname"] for e in m["edges"] if e["tid"] == n["id"]})
            kind = "База данных" if n["type"] == "DATABASE" else "Внешняя система"
            out.append(f"- **{n['name']}** ({kind.lower()}) — используют: {', '.join(users) or '—'}.")
    weak = [e for e in m["edges"] if e["confidence"] < 0.7 and not e["verified"]]
    out += ["", "## 7. Открытые вопросы", ""]
    if weak:
        out.append("Следующие связи выведены по косвенным признакам и требуют подтверждения архитектором:")
        out.append("")
        for e in weak:
            out.append(f"- {e['sname']} → {e['tname']} ({EDGE_RU.get(e['type'], e['type'])}, уверенность {e['confidence']:.2f}), источник {_ev(e)}")
    else:
        out.append("Связей с низкой уверенностью нет.")
    return title, "\n".join(out) + "\n"


def onboarding(m: dict) -> tuple[str, str]:
    p = m["project"]
    title = f"Онбординг в проект {p['name']}"
    out = _header(m, title)
    services = _services(m)
    gateway = next((s for s in services if "gateway" in s["name"]), None)
    front = [r for r in m["repos"] if r["detected_role"] == "FRONTEND"]
    libs = [r for r in m["repos"] if r["detected_role"] == "LIBRARY"]
    infra = [r for r in m["repos"] if r["detected_role"] == "INFRASTRUCTURE"]
    out += ["## С чего начать", "",
            f"1. Прочитайте «Обзор архитектуры» и откройте карту системы в PortaGraph — на ней {len(services)} сервисов и их связи.",
            "2. Пройдите путь запроса пользователя: " + " → ".join(
                [r["name"] for r in front[:1]] + ([gateway["name"]] if gateway else []) + ["нужный сервис"]) + ".",
            "3. Задайте вопросы ассистенту: «Кто использует auth-service?», «Где хранится заказ?», «Что делает billing?»." if any(
                s["name"] == "auth-service" for s in services) else "3. Задайте вопросы ассистенту о незнакомых сервисах.",
            "4. Перед изменением общего кода запустите impact analysis.", ""]
    out += ["## Карта репозиториев", ""]
    for r in m["repos"]:
        out.append(f"- **{r['name']}** — {ROLE_RU.get(r['detected_role'], '')}. {r['purpose_summary'] or ''}")
    if libs:
        out += ["", "## Общие библиотеки", "",
                "Изменения в них затрагивают сразу несколько сервисов — согласуйте их с владельцами потребителей:", ""]
        for r in libs:
            used = sorted({e["sname"] for e in m["edges"] if e["tname"] == r["name"]})
            out.append(f"- **{r['name']}**" + (f" — используют {', '.join(used)}" if used else ""))
    if infra:
        out += ["", "## Как запустить локально", ""]
        for r in infra:
            out.append(f"- Инфраструктура описана в **{r['name']}**: {r['purpose_summary'] or 'docker-compose и манифесты развёртывания'}.")
    out += ["", "## Ключевые сервисы", ""]
    deg = {}
    for e in m["edges"]:
        deg[e["tname"]] = deg.get(e["tname"], 0) + 1
    for s in sorted(services, key=lambda s: -deg.get(s["name"], 0))[:6]:
        out.append(f"- **{s['name']}** (входящих связей: {deg.get(s['name'], 0)}) — {s['description'] or ''}")
    out += ["", "## Договорённости", "", "- Секреты не хранятся в репозиториях: PortaGraph маскирует найденные значения при индексации.",
            "- Связь, которую PortaGraph показывает пунктиром, выведена по косвенным признакам — уточните её у владельца сервиса.", ""]
    return title, "\n".join(out)


def service_card(m: dict, node_id: int) -> tuple[str, str]:
    s = next((n for n in m["nodes"] if n["id"] == node_id and n["type"] == "SERVICE"), None)
    if not s:
        raise BadRequest("Выберите сервис для карточки")
    meta = s["metadata"] or {}
    title = f"Карточка сервиса {s['name']}"
    out = _header(m, title)
    repo = next((r for r in m["repos"] if r["id"] == s["repository_id"]), None)
    out += ["## Назначение", "", s["description"] or "—", "",
            "## Паспорт", "", "| Параметр | Значение |", "|---|---|",
            f"| Репозиторий | {s['repo_name'] or '—'} |",
            f"| Источник | {repo['url'] if repo else '—'} |",
            f"| Стек | {', '.join(meta.get('stack') or []) or '—'} |",
            f"| Уверенность роли | {repo['role_confidence']:.2f} |" if repo else "| Уверенность роли | — |", ""]
    eps = meta.get("endpoints") or []
    if eps:
        out += ["## API", "", "| Метод | Путь | Где |", "|---|---|---|"]
        for ep in eps[:60]:
            out.append(f"| {ep.get('method', '')} | `{ep.get('path', '')}` | `{ep.get('file', '')}:{ep.get('line', '')}` |")
        out.append("")
    outs = [e for e in m["edges"] if e["sid"] == s["id"]]
    ins = [e for e in m["edges"] if e["tid"] == s["id"]]
    out += ["## Зависимости (от чего зависит)", ""]
    out += [f"- {EDGE_RU.get(e['type'], e['type'])} **{e['tname']}** — {_conf(e['confidence'], e['verified'])}, {_ev(e)}" for e in outs] or ["- нет"]
    out += ["", "## Потребители (кто зависит)", ""]
    out += [f"- **{e['sname']}** {EDGE_RU.get(e['type'], e['type'])} — {_conf(e['confidence'], e['verified'])}, {_ev(e)}" for e in ins] or ["- нет"]
    out += ["", "## Риски изменений", "",
            f"Прямых потребителей: {len(ins)}. " + ("Изменение контракта затронет их — согласуйте его заранее." if ins else
                                                     "Изменение контракта не затронет другие сервисы проекта."), ""]
    return title, "\n".join(out)


def generate(ctx: Context, project_id: int, user_id: int, type_: str, node_id: int | None = None) -> dict:
    access.require(ctx, project_id, user_id, "generate_docs")
    if type_ not in TYPES:
        raise BadRequest("Неизвестный тип документа")
    m = _model(ctx, project_id)
    if type_ == "ARCHITECTURE_OVERVIEW":
        title, text = overview(m)
    elif type_ == "ONBOARDING_GUIDE":
        title, text = onboarding(m)
    else:
        title, text = service_card(m, int(node_id or 0))
    doc_id = ctx.db.scalar("""INSERT INTO generated_documents(project_id, run_id, type, title, content_md, created_by)
                              VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""", project_id, m["run"]["id"], type_, title, text, user_id)
    return get(ctx, project_id, user_id, doc_id)


def get(ctx: Context, project_id: int, user_id: int, doc_id: int) -> dict:
    access.require(ctx, project_id, user_id)
    d = ctx.db.one("""SELECT d.*, c.full_name AS author, a.full_name AS approver FROM generated_documents d
                        LEFT JOIN users c ON c.id = d.created_by LEFT JOIN users a ON a.id = d.approved_by
                       WHERE d.id = %s AND d.project_id = %s""", doc_id, project_id)
    if not d:
        raise NotFound("Документ не найден")
    d["type_ru"] = TYPES[d["type"]]
    d["status_ru"] = STATUS_RU[d["status"]]
    d["html"] = render_markdown(d["content_md"])
    return d


def list_docs(ctx: Context, project_id: int, user_id: int) -> list[dict]:
    access.require(ctx, project_id, user_id)
    rows = ctx.db.all("""SELECT d.id, d.type, d.title, d.status, d.created_at, d.approved_at, c.full_name AS author
                           FROM generated_documents d LEFT JOIN users c ON c.id = d.created_by
                          WHERE d.project_id = %s ORDER BY d.created_at DESC""", project_id)
    for r in rows:
        r["type_ru"] = TYPES[r["type"]]
        r["status_ru"] = STATUS_RU[r["status"]]
    return rows


def update(ctx: Context, project_id: int, user_id: int, doc_id: int, content_md: str) -> dict:
    access.require(ctx, project_id, user_id, "generate_docs")
    d = get(ctx, project_id, user_id, doc_id)
    if d["status"] == "APPROVED":
        raise BadRequest("Утверждённый документ не редактируется — сформируйте новую версию")
    content_md = (content_md or "").strip()
    if not content_md:
        raise BadRequest("Документ не может быть пустым")
    m = re.match(r"#\s+(.+)", content_md)
    ctx.db.run("UPDATE generated_documents SET content_md = %s, title = %s WHERE id = %s",
               content_md + "\n", (m.group(1).strip() if m else d["title"])[:300], doc_id)
    return get(ctx, project_id, user_id, doc_id)


def approve(ctx: Context, project_id: int, user_id: int, doc_id: int) -> dict:
    access.require(ctx, project_id, user_id, "approve_docs")
    d = get(ctx, project_id, user_id, doc_id)
    if d["status"] == "OUTDATED":
        raise BadRequest("Документ устарел: граф изменился после его создания. Сформируйте документ заново")
    ctx.db.run("UPDATE generated_documents SET status = 'APPROVED', approved_by = %s, approved_at = now() WHERE id = %s", user_id, doc_id)
    return get(ctx, project_id, user_id, doc_id)


def delete(ctx: Context, project_id: int, user_id: int, doc_id: int) -> None:
    access.require(ctx, project_id, user_id, "approve_docs")
    if not ctx.db.run("DELETE FROM generated_documents WHERE id = %s AND project_id = %s", doc_id, project_id):
        raise NotFound("Документ не найден")


def filename(d: dict) -> str:
    base = re.sub(r"[^\w\-]+", "-", d["title"].lower()).strip("-")[:80] or "document"
    return f"{base}-{dt.date.today().isoformat()}.md"
