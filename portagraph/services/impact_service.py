"""Impact analysis (UC-11): отчёт о влиянии изменения и история отчётов."""
from __future__ import annotations

from ..core import impact
from ..db import Json
from . import access, graph_service
from .context import Context
from .errors import BadRequest, NotFound

RISK_RU = {"LOW": "Низкий", "MEDIUM": "Средний", "HIGH": "Высокий", "CRITICAL": "Критический"}
IMPACT_TYPES = ("SERVICE", "REPOSITORY", "DATABASE", "MESSAGE_QUEUE", "EXTERNAL_SYSTEM", "CLASS", "ENTITY", "FUNCTION", "MODULE")


def _recommendation(risk: str, changed: list[dict], affected: list[dict]) -> str:
    direct = [a for a in affected if a["distance"] == 1]
    services = [a for a in affected if a["type"] == "SERVICE"]
    weak = [a for a in affected if a["confidence"] < 0.7]
    async_ = [a for a in affected if a["via"] in ("PUBLISHES", "CONSUMES")]
    lines = []
    head = {"CRITICAL": "Изменение затрагивает ключевой компонент. Согласуйте его с владельцами всех зависимых сервисов и выпускайте поэтапно.",
            "HIGH": "Изменение затрагивает несколько сервисов. Запланируйте совместное тестирование и сохраните обратную совместимость контракта.",
            "MEDIUM": "Влияние ограничено. Достаточно прогнать тесты затронутых компонентов.",
            "LOW": "Зависимых компонентов не найдено. Проверьте, что граф актуален, и выпускайте как обычно."}[risk]
    lines.append(head)
    if direct:
        lines.append("Сначала проверьте прямых потребителей: " + ", ".join(a["name"] for a in direct[:8]) + ".")
    if services:
        lines.append("Сервисы, которым нужен регрессионный прогон: " + ", ".join(a["name"] for a in services[:10]) + ".")
    if async_:
        lines.append("Есть асинхронные связи через очереди — проверьте формат событий и совместимость схемы сообщений.")
    if any(c["type"] in ("DATABASE", "ENTITY") for c in changed):
        lines.append("Меняется схема данных — подготовьте миграцию с откатом.")
    if weak:
        lines.append("Связи с уверенностью ниже 0,7 (" + ", ".join(a["name"] for a in weak[:6]) +
                     ") выведены по косвенным признакам — подтвердите их у владельцев.")
    return "\n".join(lines)


def run(ctx: Context, project_id: int, user_id: int, node_ids: list[int], depth: int, description: str) -> dict:
    access.require(ctx, project_id, user_id, "impact")
    description = (description or "").strip()
    if not description:
        raise BadRequest("Опишите изменение, например: «меняем формат ответа /api/auth/validate»")
    try:
        depth = int(depth)
        node_ids = [int(n) for n in node_ids]
    except (TypeError, ValueError):
        raise BadRequest("Некорректные параметры анализа") from None
    if not node_ids:
        raise BadRequest("Выберите хотя бы один изменяемый компонент")
    g, by_id, edges, run_row = graph_service.load(ctx, project_id)
    missing = [n for n in node_ids if n not in by_id]
    if missing:
        raise NotFound("Выбранные компоненты отсутствуют в текущем графе — обновите страницу")
    # изменение сервиса/репозитория = изменение всех его вложенных элементов
    expanded = set(node_ids)
    children = {}
    for n in by_id.values():
        children.setdefault(n["parent_id"], []).append(n["id"])
    stack = list(node_ids)
    while stack:
        for ch in children.get(stack.pop(), []):
            if ch not in expanded:
                expanded.add(ch)
                stack.append(ch)
    try:
        res = impact.analyze(g, sorted(expanded), depth)
    except ValueError as e:
        raise BadRequest(str(e)) from None
    edge_conf = {}
    for e in edges:
        if not e["rejected"]:
            edge_conf[(e["source_node_id"], e["target_node_id"])] = max(e["confidence"], edge_conf.get((e["source_node_id"], e["target_node_id"]), 0))
            edge_conf[(e["target_node_id"], e["source_node_id"])] = max(e["confidence"], edge_conf.get((e["target_node_id"], e["source_node_id"]), 0))

    # отчёт показываем на уровне компонентов, без вложенных классов изменяемого сервиса
    affected = []
    for a in res.affected:
        n = by_id[a.node.id]
        if n["type"] not in IMPACT_TYPES:
            continue
        last = a.path[-2], a.path[-1]
        affected.append({"id": n["id"], "name": n["name"], "type": n["type"], "type_ru": graph_service.TYPE_RU.get(n["type"], n["type"]),
                         "repo": n.get("repo_name"), "distance": a.distance, "score": round(a.score, 3), "via": a.via,
                         "confidence": round(edge_conf.get(last, 1.0), 2),
                         "path": [by_id[p]["name"] for p in a.path]})
    # сворачиваем классы в их сервисы, чтобы список был обозримым
    comp = {nid: graph_service._component_of(by_id, nid) for nid in by_id}
    changed_comps = {comp.get(n) for n in node_ids} | set(node_ids)
    summary: dict[int, dict] = {}
    for a in affected:
        c = comp.get(a["id"]) or a["id"]
        if c in changed_comps:
            continue
        cur = summary.get(c)
        if cur is None or a["score"] > cur["score"]:
            cn = by_id[c]
            summary[c] = {**a, "id": c, "name": cn["name"], "type": cn["type"],
                          "type_ru": graph_service.TYPE_RU.get(cn["type"], cn["type"]),
                          "via_element": a["name"] if c != a["id"] else None}
    components = sorted(summary.values(), key=lambda x: (-x["score"], x["distance"], x["name"]))
    direct_services = sum(1 for c in components if c["distance"] == 1 and c["type"] == "SERVICE")
    total = round(sum(c["score"] for c in components), 3)
    risk = impact.assess_risk(direct_services, total, len(components))
    changed = [{"id": n, "name": by_id[n]["name"], "type": by_id[n]["type"]} for n in node_ids]
    rec = _recommendation(risk, changed, components)
    row = ctx.db.one("""INSERT INTO impact_reports(project_id, run_id, author_id, change_description, changed_nodes, max_depth,
                                                   affected, risk_level, total_weight, recommendation)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, created_at""",
                     project_id, run_row["id"], user_id, description[:2000], Json(changed), depth,
                     Json({"components": components, "elements": affected[:300]}), risk, total, rec)
    return get(ctx, project_id, user_id, row["id"])


def get(ctx: Context, project_id: int, user_id: int, report_id: int) -> dict:
    access.require(ctx, project_id, user_id)
    r = ctx.db.one("""SELECT i.*, u.full_name AS author FROM impact_reports i JOIN users u ON u.id = i.author_id
                       WHERE i.id = %s AND i.project_id = %s""", report_id, project_id)
    if not r:
        raise NotFound("Отчёт не найден")
    r["risk_ru"] = RISK_RU[r["risk_level"]]
    r["components"] = r["affected"].get("components", [])
    r["elements"] = r["affected"].get("elements", [])
    latest = graph_service.latest_run(ctx, project_id)
    r["stale"] = bool(latest and r["run_id"] != latest["id"])
    return r


def history(ctx: Context, project_id: int, user_id: int) -> list[dict]:
    access.require(ctx, project_id, user_id)
    rows = ctx.db.all("""SELECT i.id, i.change_description, i.risk_level, i.total_weight, i.max_depth, i.created_at, i.changed_nodes,
                                jsonb_array_length(i.affected->'components') AS affected_count, u.full_name AS author
                           FROM impact_reports i JOIN users u ON u.id = i.author_id
                          WHERE i.project_id = %s ORDER BY i.created_at DESC LIMIT 50""", project_id)
    for r in rows:
        r["risk_ru"] = RISK_RU[r["risk_level"]]
    return rows
