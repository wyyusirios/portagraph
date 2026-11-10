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
    import html as _html
    try:
        m = md.Markdown(extensions=["tables", "fenced_code", "sane_lists"])
        for reg, name in ((m.preprocessors, "html_block"), (m.inlinePatterns, "html")):
            try:
                reg.deregister(name)
            except (KeyError, ValueError):  # в другой версии Markdown имя может отличаться
                pass
        out = m.convert(text)
    except Exception:  # noqa: BLE001 — документ всё равно должен открыться
        return "<pre>" + _html.escape(text) + "</pre>"
    return re.sub(r'(href|src)="\s*(javascript|data|vbscript):[^"]*"', r'\1="#"', out, flags=re.I)


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


def to_docx(d: dict) -> bytes:
    """Документ в формате Word (.docx) без внешних библиотек: заголовки, абзацы, списки,
    таблицы, жирный и моноширинный текст."""
    import io
    import zipfile
    from xml.sax.saxutils import escape

    def run(text: str, bold=False, mono=False, italic=False, size=None, color=None) -> str:
        pr = ""
        if mono:
            pr += '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>'
        if bold:
            pr += "<w:b/>"
        if italic:
            pr += "<w:i/>"
        if color:
            pr += f'<w:color w:val="{color}"/>'
        if size or mono:
            pr += f'<w:sz w:val="{size or 19}"/>'
        return f'<w:r>{"<w:rPr>" + pr + "</w:rPr>" if pr else ""}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'

    def inline(text: str, **kw) -> str:
        out = []
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
        for part in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text):
            if not part:
                continue
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                out.append(run(part[2:-2], bold=True, **{k: v for k, v in kw.items() if k != "bold"}))
            elif part.startswith("`") and part.endswith("`") and len(part) > 2:
                out.append(run(part[1:-1], mono=True, **{k: v for k, v in kw.items() if k not in ("mono", "size")}))
            else:
                out.append(run(part, **kw))
        return "".join(out)

    def para(content: str, style: str | None = None, ind: int = 0, after: int | None = None) -> str:
        pr = f'<w:pStyle w:val="{style}"/>' if style else ""
        if ind:
            pr += f'<w:ind w:left="{ind}" w:hanging="300"/>'
        if after is not None:
            pr += f'<w:spacing w:after="{after}"/>'
        return f'<w:p>{"<w:pPr>" + pr + "</w:pPr>" if pr else ""}{content}</w:p>'

    def table(rows: list[list[str]]) -> str:
        cols = max(len(r) for r in rows)
        border = "".join(f'<w:{e} w:val="single" w:sz="4" w:color="BFBFBF"/>' for e in ("top", "left", "bottom", "right", "insideH", "insideV"))
        out = [f'<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>{border}</w:tblBorders>'
               '<w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>'
               + "".join('<w:gridCol w:w="2000"/>' for _ in range(cols)) + "</w:tblGrid>"]
        for ri, r in enumerate(rows):
            out.append("<w:tr>")
            for ci in range(cols):
                shade = '<w:shd w:val="clear" w:color="auto" w:fill="F6E7D8"/>' if ri == 0 else ""
                cell = r[ci] if ci < len(r) else ""
                out.append(f"<w:tc><w:tcPr>{shade}</w:tcPr>{para(inline(cell, bold=ri == 0, size=19), after=0)}</w:tc>")
            out.append("</w:tr>")
        out.append("</w:tbl>")
        return "".join(out) + para("")

    body = []
    lines = d["content_md"].split("\n")
    i, num = 0, 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            num = 0
            continue
        h = re.match(r"^(#{1,4})\s+(.*)", line)
        if h:
            level = len(h.group(1))
            body.append(para(inline(h.group(2)), "Title" if level == 1 else f"Heading{min(level - 1, 3)}"))
            i += 1
            continue
        if line.lstrip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                body.append(table(rows))
            continue
        if line.startswith("```"):
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(para(run(lines[i], mono=True), after=0))
                i += 1
            i += 1
            continue
        if line.startswith(">"):
            body.append(para(inline(line.lstrip("> "), italic=True, color="666666")))
            i += 1
            continue
        b = re.match(r"^(\s*)[-*]\s+(.*)", line)
        n = re.match(r"^(\s*)\d+[.)]\s+(.*)", line)
        if b or n:
            m = b or n
            depth = len(m.group(1)) // 2
            if n:
                num += 1
            mark = "•\t" if b else f"{num}.\t"
            body.append(para(run(mark) + inline(m.group(2)), ind=360 + 360 * depth, after=60))
            i += 1
            continue
        chunk = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||>|\s*[-*]\s|\s*\d+[.)]\s|```)", lines[i]):
            chunk.append(lines[i].strip())
            i += 1
        body.append(para(inline(" ".join(chunk))))

    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>{"".join(body)}'
                '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
                'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>')

    def hstyle(sid, name, size, color, before):
        return (f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>'
                f'<w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="{before}" w:after="120"/><w:outlineLvl w:val="{0 if sid == "Title" else int(sid[-1]) - 1}"/></w:pPr>'
                f'<w:rPr><w:b/><w:color w:val="{color}"/><w:sz w:val="{size}"/></w:rPr></w:style>')
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}>'
              '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri" w:eastAsia="Calibri"/>'
              '<w:sz w:val="22"/><w:lang w:val="ru-RU"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/>'
              '</w:pPr></w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
              + hstyle("Title", "Title", 40, "C4623A", 0) + hstyle("Heading1", "heading 1", 30, "C4623A", 360)
              + hstyle("Heading2", "heading 2", 25, "333333", 240) + hstyle("Heading3", "heading 3", 23, "333333", 200)
              + "</w:styles>")
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
    return buf.getvalue()
