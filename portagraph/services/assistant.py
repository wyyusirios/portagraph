"""AI-ассистент по проекту (UC-10) в демо-режиме без языковой модели.

Ответ собирается из двух источников:
1. граф архитектуры – если вопрос про связи («кто использует X», «от чего зависит Y»,
   «за что отвечает Z»), ответ строится по рёбрам графа с доказательствами;
2. полнотекстовый поиск PostgreSQL по фрагментам кода и документации – 12 лучших
   фрагментов только этого проекта, со ссылками «файл:строки».

Уверенность ответа ниже 0,4 помечается предупреждением о неполных данных.
"""
from __future__ import annotations

import re

from ..core.text import query_terms, russian_stem, split_identifier
from . import access, graph_service
from .context import Context
from .errors import BadRequest, NotFound
from ..db import Json

TOP_K = 12
MIN_CONFIDENCE = 0.4
MODE_NOTE = ("Демо-режим без языковой модели: ответ собран из графа архитектуры и полнотекстового поиска по коду. "
             "Проверяйте выводы по ссылкам на источники.")

INTENTS = [
    ("dependents", re.compile(r"(кто|какие|что|какой).{0,40}(использ|зависит|зависят|вызыва|обращ|ходит|подпис|чита|потребля|слуша)|"
                              r"(потребител|клиент|подписчик)", re.I)),
    ("dependencies", re.compile(r"(от чего|от каких|от кого).{0,20}завис|что (использует|вызывает)|куда .{0,20}(обращ|ходит|пишет)|"
                                r"(зависимост|с чем (связан|работает))", re.I)),
    ("purpose", re.compile(r"(что так|за что отвечает|зачем|назначени|что делает|для чего|опиши|расскажи)", re.I)),
]
SYNONYMS = {"заказ": ["order"], "пользовател": ["user", "auth"], "клиент": ["user", "customer"], "оплат": ["payment", "billing"],
            "плат": ["payment", "billing"], "товар": ["product", "catalog"], "каталог": ["catalog", "product"], "письм": ["mail", "notification"],
            "почт": ["mail", "email"], "уведомл": ["notification", "notify"], "токен": ["token", "jwt"], "авториз": ["auth", "login"],
            "аутентиф": ["auth", "login"], "вход": ["login", "auth"], "регистрац": ["register", "signup"], "цен": ["price"],
            "остат": ["stock"], "событ": ["event"], "шлюз": ["gateway"], "очеред": ["kafka", "topic"], "топик": ["topic", "kafka"],
            "счет": ["invoice"], "счёт": ["invoice"], "корзин": ["cart"], "доставк": ["delivery", "shipping"], "фронт": ["frontend", "web"]}
STORAGE = re.compile(r"(хран|сохран|база данных|базе данных|бд\b|таблиц|где лежат|persist|entity|сущност)", re.I)
EDGE_PHRASE = {"CALLS_HTTP": "по HTTP", "PUBLISHES": "публикует события", "CONSUMES": "читает события", "READS_WRITES": "читает и пишет данные",
               "DEPENDS_ON": "зависит (сборка/запуск)", "IMPORTS": "использует код"}


def _session(ctx: Context, project_id: int, user_id: int, session_id: int | None, question: str) -> int:
    if session_id:
        s = ctx.db.one("SELECT id FROM chat_sessions WHERE id = %s AND project_id = %s AND user_id = %s", session_id, project_id, user_id)
        if not s:
            raise NotFound("Диалог не найден")
        return s["id"]
    title = re.sub(r"\s+", " ", question.strip())
    title = title if len(title) <= 80 else title[:77] + "…"
    return ctx.db.scalar("INSERT INTO chat_sessions(project_id, user_id, title) VALUES (%s, %s, %s) RETURNING id",
                         project_id, user_id, title)


def _find_entities(ctx: Context, run_id: int, question: str, terms: list[str]) -> list[dict]:
    """Узлы графа, названные в вопросе (сервисы, топики, БД, классы)."""
    q = question.lower()
    rows = ctx.db.all("""SELECT n.id, n.type, n.name, n.description, n.qualified_name, r.name AS repo_name
                           FROM graph_nodes n LEFT JOIN repositories r ON r.id = n.repository_id
                          WHERE n.run_id = %s AND n.type IN ('SERVICE','REPOSITORY','DATABASE','MESSAGE_QUEUE','EXTERNAL_SYSTEM','CLASS','ENTITY')""",
                      run_id)
    found = []
    for n in rows:
        name = n["name"].lower()
        parts = split_identifier(n["name"])
        if len(name) >= 3 and (re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", q)
                               or (len(parts) > 1 and " ".join(parts) in q)
                               or (n["type"] == "DATABASE" and f"{name}-db" in q)):
            found.append(n)
    # сервис важнее одноимённого репозитория
    names = {n["name"] for n in found if n["type"] == "SERVICE"}
    found = [n for n in found if not (n["type"] == "REPOSITORY" and n["name"] in names)]
    order = {"SERVICE": 0, "MESSAGE_QUEUE": 1, "DATABASE": 2, "EXTERNAL_SYSTEM": 3, "REPOSITORY": 4, "ENTITY": 5, "CLASS": 6}
    return sorted(found, key=lambda n: (order.get(n["type"], 9), -len(n["name"])))[:3]


def _search(ctx: Context, project_id: int, terms: list[str]) -> list[dict]:
    words = []
    for t in terms:
        t = re.sub(r"[^\wа-яё.\-]", "", t.lower())
        for part in {t, russian_stem(t)} | set(re.split(r"[.\-]", t)):
            part = re.sub(r"[^\wа-яё]", "", part)
            if len(part) >= 2:
                words.append(part + (":*" if len(part) >= 4 else ""))
    words = list(dict.fromkeys(words))[:24]
    if not words:
        return []
    tsq = " | ".join(words)
    return ctx.db.all("""SELECT c.id, c.start_line, c.end_line, c.symbol, c.content, f.id AS file_id, f.path, f.kind,
                                r.name AS repo_name, ts_rank_cd(c.tsv, q) AS rank,
                                (SELECT count(*) FROM unnest(%s::text[]) w WHERE c.tsv @@ to_tsquery('simple', w)) AS hits
                           FROM code_chunks c JOIN source_files f ON f.id = c.source_file_id
                           JOIN repositories r ON r.id = f.repository_id, to_tsquery('simple', %s) q
                          WHERE c.project_id = %s AND c.tsv @@ q
                          ORDER BY hits DESC, (f.kind = 'CODE') DESC, rank DESC LIMIT %s""",
                      words, tsq, project_id, TOP_K)


def _best_line(content: str, terms: list[str]) -> str:
    for line in content.split("\n"):
        low = line.lower()
        if any(t in low for t in terms if len(t) >= 3) and len(line.strip()) > 6:
            return line.strip()[:160]
    return next((x.strip()[:160] for x in content.split("\n") if x.strip()), "")


def ask(ctx: Context, project_id: int, user_id: int, session_id: int | None, question: str) -> dict:
    access.require(ctx, project_id, user_id, "ask")
    question = (question or "").strip()
    if not question:
        raise BadRequest("Напишите вопрос, например: «Кто использует auth-service?»")
    if len(question) > 2000:
        raise BadRequest("Вопрос слишком длинный (до 2000 символов)")
    run = graph_service.require_run(ctx, project_id)
    sid = _session(ctx, project_id, user_id, session_id, question)
    ctx.db.run("INSERT INTO chat_messages(session_id, role, content) VALUES (%s, 'USER', %s)", sid, question)

    terms = query_terms(question)
    english = list(dict.fromkeys(en for t in terms for k, ens in SYNONYMS.items() if t.startswith(k) for en in ens))
    terms = terms + [e for e in english if e not in terms]
    entities = _find_entities(ctx, run["id"], question, terms)
    intent = next((name for name, rx in INTENTS if rx.search(question)), None)
    parts: list[str] = []
    citations: list[dict] = []
    confidence = 0.0
    files = {(r["name"], r["path"]): r["id"] for r in ctx.db.all(
        "SELECT f.id, f.path, r.name FROM source_files f JOIN repositories r ON r.id = f.repository_id WHERE r.project_id = %s", project_id)}

    def cite_evidence(ev: dict):
        fid = files.get((ev.get("repo"), ev.get("path")))
        if fid and not any(c["file_id"] == fid and c["start_line"] == ev.get("line") for c in citations):
            citations.append({"file_id": fid, "path": f"{ev['repo']}/{ev['path']}", "start_line": ev.get("line") or 1,
                              "end_line": ev.get("line") or 1, "label": ev.get("rule")})

    # ---- 1. ответ по графу
    if STORAGE.search(question) and (english or entities):
        keys = english or [e["name"].lower() for e in entities]
        stores = ctx.db.all("""SELECT n.id, n.type, n.name, n.metadata, n.source_file_id, n.start_line, n.end_line, r.name AS repo_name, f.path
                                 FROM graph_nodes n LEFT JOIN repositories r ON r.id = n.repository_id
                                 LEFT JOIN source_files f ON f.id = n.source_file_id
                                WHERE n.run_id = %s AND n.type IN ('ENTITY', 'DATABASE')
                                  AND EXISTS (SELECT 1 FROM unnest(%s::text[]) k WHERE lower(n.name) LIKE '%%' || k || '%%')
                                ORDER BY n.type DESC, n.name""", run["id"], keys)
        if stores:
            lines = []
            for n in stores:
                if n["type"] == "ENTITY":
                    table = (n["metadata"] or {}).get("table")
                    lines.append(f"- сущность **{n['name']}**" + (f" (таблица `{table}`)" if table else "") +
                                 f" в {n['repo_name']} – {n['path']}:{n['start_line']}")
                    citations.append({"file_id": n["source_file_id"], "path": f"{n['repo_name']}/{n['path']}",
                                      "start_line": n["start_line"] or 1, "end_line": n["end_line"] or 1, "label": n["name"]})
                else:
                    users = ctx.db.all("""SELECT s.name, e.confidence, e.evidence FROM graph_edges e JOIN graph_nodes s ON s.id = e.source_node_id
                                           WHERE e.target_node_id = %s AND NOT e.rejected""", n["id"])
                    engine = (n["metadata"] or {}).get("engine")
                    lines.append(f"- база данных **{n['name']}**" + (f" ({engine})" if engine else "") + " – работает с ней "
                                 + ", ".join(f"**{u['name']}**" for u in users))
                    for u in users:
                        for ev in u["evidence"][:1]:
                            cite_evidence(ev)
            parts.append("Где хранятся данные:\n" + "\n".join(lines))
            confidence = 0.8
    if entities and not parts:
        main = entities[0]
        if intent == "dependents" or (intent is None and re.search(r"использ|зависит|вызыва|подпис", question, re.I)):
            rows = ctx.db.all("""SELECT e.type, e.confidence, e.verified, e.evidence, s.name, s.type AS stype
                                   FROM graph_edges e JOIN graph_nodes s ON s.id = e.source_node_id
                                  WHERE e.target_node_id = %s AND NOT e.rejected AND e.type <> 'IMPORTS'
                                  ORDER BY e.confidence DESC""", main["id"])
            if main["type"] == "MESSAGE_QUEUE":
                pubs = ctx.db.all("""SELECT s.name, e.confidence, e.evidence FROM graph_edges e JOIN graph_nodes s ON s.id = e.source_node_id
                                      WHERE e.target_node_id = %s AND e.type = 'PUBLISHES' AND NOT e.rejected""", main["id"])
                cons = [r for r in rows if r["type"] == "CONSUMES"]
                parts.append(f"В топик **{main['name']}** публикует: " + (", ".join(f"**{p['name']}**" for p in pubs) or "не найдено") +
                             ". Подписчики: " + (", ".join(f"**{c['name']}** (уверенность {c['confidence']:.2f})" for c in cons) or "не найдены") + ".")
                for r in pubs + cons:
                    for ev in r["evidence"][:2]:
                        cite_evidence(ev)
            elif rows:
                lines = [f"- **{r['name']}** – {EDGE_PHRASE.get(r['type'], r['type'])}, уверенность {r['confidence']:.2f}"
                         + (" (подтверждено архитектором)" if r["verified"] else " – нужна проверка" if r["confidence"] < 0.7 else "")
                         for r in rows]
                parts.append(f"От **{main['name']}** зависят {len(rows)} компонент(а):\n" + "\n".join(lines))
                for r in rows:
                    for ev in r["evidence"][:2]:
                        cite_evidence(ev)
            else:
                parts.append(f"В графе нет компонентов, которые зависят от **{main['name']}**.")
            confidence = 0.85
        elif intent == "dependencies":
            rows = ctx.db.all("""SELECT e.type, e.confidence, e.verified, e.evidence, t.name, t.type AS ttype
                                   FROM graph_edges e JOIN graph_nodes t ON t.id = e.target_node_id
                                  WHERE e.source_node_id = %s AND NOT e.rejected AND e.type <> 'IMPORTS'
                                  ORDER BY e.confidence DESC""", main["id"])
            if rows:
                lines = [f"- **{r['name']}** ({graph_service.TYPE_RU.get(r['ttype'], r['ttype']).lower()}) – "
                         f"{EDGE_PHRASE.get(r['type'], r['type'])}, уверенность {r['confidence']:.2f}" for r in rows]
                parts.append(f"**{main['name']}** зависит от {len(rows)} компонент(ов):\n" + "\n".join(lines))
                for r in rows:
                    for ev in r["evidence"][:2]:
                        cite_evidence(ev)
            else:
                parts.append(f"У **{main['name']}** не найдено внешних зависимостей.")
            confidence = 0.85
        else:
            desc = main["description"] or "описание не найдено"
            kind = graph_service.TYPE_RU.get(main["type"], main["type"]).lower()
            parts.append(f"**{main['name']}** ({kind}" + (f", репозиторий {main['repo_name']}" if main.get("repo_name") and main["repo_name"] != main["name"] else "")
                         + f"): {desc}")
            confidence = 0.7

    # ---- 2. поиск по коду
    hits = _search(ctx, project_id, terms + ([e["name"].lower() for e in entities] if entities else []))
    used = 0
    if hits:
        best_hits = hits[0]["hits"]
        code_lines = []
        for h in hits[:5]:
            loc = f"{h['repo_name']}/{h['path']}:{h['start_line']}–{h['end_line']}"
            what = f"`{h['symbol']}`" if h["symbol"] else ("документация" if h["kind"] in ("README", "DOCUMENTATION") else "фрагмент")
            code_lines.append(f"- {what} – {loc}\n  `{_best_line(h['content'], terms)}`")
            citations.append({"file_id": h["file_id"], "path": f"{h['repo_name']}/{h['path']}", "start_line": h["start_line"],
                              "end_line": h["end_line"], "label": h["symbol"] or h["kind"].lower()})
            used += 1
        title = "Где это в коде:" if parts else "Нашёл в коде и документации проекта:"
        parts.append(title + "\n" + "\n".join(code_lines))
        coverage = best_hits / max(1, len([t for t in terms if len(t) >= 2]))
        search_conf = min(0.75, 0.3 + 0.45 * coverage)
        confidence = max(confidence, search_conf)
    if not parts:
        parts.append("В проиндексированных материалах проекта нет данных для ответа на этот вопрос. "
                     "Попробуйте назвать сервис, класс или топик, например: «Кто использует auth-service?»")
        confidence = 0.1
    text = "\n\n".join(parts)
    if confidence < MIN_CONFIDENCE:
        text += "\n\n⚠ Ответ основан на неполных данных – проверьте указанные источники."
    seen, uniq = set(), []
    for c in citations:
        k = (c["file_id"], c["start_line"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    msg = ctx.db.one("""INSERT INTO chat_messages(session_id, role, content, citations, confidence)
                        VALUES (%s, 'ASSISTANT', %s, %s, %s) RETURNING id, session_id, role, content, citations, confidence, created_at""",
                     sid, text, Json(uniq[:12]), round(confidence, 2))
    msg["mode_note"] = MODE_NOTE
    msg["entities"] = [{"id": e["id"], "name": e["name"], "type": e["type"]} for e in entities]
    return msg


def sessions(ctx: Context, project_id: int, user_id: int) -> list[dict]:
    access.require(ctx, project_id, user_id)
    return ctx.db.all("""SELECT s.id, s.title, s.created_at, (SELECT count(*) FROM chat_messages m WHERE m.session_id = s.id) AS messages
                           FROM chat_sessions s WHERE s.project_id = %s AND s.user_id = %s ORDER BY s.created_at DESC LIMIT 50""",
                      project_id, user_id)


def messages(ctx: Context, project_id: int, user_id: int, session_id: int) -> list[dict]:
    access.require(ctx, project_id, user_id)
    if not ctx.db.scalar("SELECT 1 FROM chat_sessions WHERE id = %s AND project_id = %s AND user_id = %s", session_id, project_id, user_id):
        raise NotFound("Диалог не найден")
    return ctx.db.all("SELECT id, role, content, citations, confidence, created_at FROM chat_messages WHERE session_id = %s ORDER BY id",
                      session_id)
