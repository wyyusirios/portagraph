"""Чтение графа, режимы визуализации (UC-08, UC-09), подтверждение выводов (UC-13)."""
from __future__ import annotations

from collections import defaultdict

from ..core.graph import ArchitectureGraph, Edge, Node
from . import access
from .context import Context
from .errors import BadRequest, NotFound

OVERVIEW_TYPES = {"SERVICE", "DATABASE", "MESSAGE_QUEUE", "EXTERNAL_SYSTEM"}
CODE_TYPES = ("CLASS", "ENTITY", "FUNCTION")
TYPE_RU = {"SYSTEM": "Система", "REPOSITORY": "Репозиторий", "SERVICE": "Сервис", "MODULE": "Модуль", "CLASS": "Класс",
           "FUNCTION": "Функция", "ENTITY": "Сущность", "DATABASE": "База данных", "MESSAGE_QUEUE": "Топик",
           "EXTERNAL_SYSTEM": "Внешняя система", "API_ENDPOINT": "API"}
EDGE_RU = {"CALLS_HTTP": "вызывает по HTTP", "PUBLISHES": "публикует в", "CONSUMES": "читает из", "READS_WRITES": "читает и пишет",
           "DEPENDS_ON": "зависит от", "IMPORTS": "использует", "CONTAINS": "содержит"}


def latest_run(ctx: Context, project_id: int) -> dict | None:
    return ctx.db.one("SELECT * FROM analysis_runs WHERE project_id = %s AND status = 'COMPLETED' ORDER BY finished_at DESC, id DESC LIMIT 1",
                      project_id)


def require_run(ctx: Context, project_id: int) -> dict:
    run = latest_run(ctx, project_id)
    if not run:
        raise BadRequest("Для проекта ещё нет завершённого анализа — запустите его на странице репозиториев")
    return run


def _rows(ctx: Context, run_id: int):
    nodes = ctx.db.all("""SELECT n.id, n.type, n.name, n.qualified_name, n.parent_id, n.repository_id, n.source_file_id,
                                 n.start_line, n.end_line, n.description, n.confidence, n.verified, n.metadata,
                                 r.name AS repo_name, r.detected_role AS repo_role
                            FROM graph_nodes n LEFT JOIN repositories r ON r.id = n.repository_id WHERE n.run_id = %s""", run_id)
    edges = ctx.db.all("""SELECT id, source_node_id, target_node_id, type, confidence, verified, rejected,
                                 jsonb_array_length(evidence) AS evidence_count
                            FROM graph_edges WHERE run_id = %s""", run_id)
    return nodes, edges


def load(ctx: Context, project_id: int) -> tuple[ArchitectureGraph, dict[int, dict], list[dict], dict]:
    run = require_run(ctx, project_id)
    nodes, edges = _rows(ctx, run["id"])
    g = ArchitectureGraph()
    by_id = {n["id"]: n for n in nodes}
    for n in nodes:
        g.add_node(Node(n["id"], n["type"], n["name"], n["parent_id"]))
    for e in edges:
        if not e["rejected"]:
            g.add_edge(Edge(e["source_node_id"], e["target_node_id"], e["type"], e["confidence"]))
    return g, by_id, edges, run


def _node_json(n: dict) -> dict:
    meta = n["metadata"] or {}
    return {"id": n["id"], "type": n["type"], "type_ru": TYPE_RU.get(n["type"], n["type"]), "label": n["name"],
            "description": n["description"], "confidence": n["confidence"], "verified": n["verified"],
            "repo": n.get("repo_name"), "repo_id": n.get("repository_id"), "role": meta.get("role"), "stack": meta.get("stack"), "engine": meta.get("engine"),
            "broker": meta.get("broker"), "endpoints": len(meta.get("endpoints") or []), "kind": meta.get("kind"),
            "stereotype": meta.get("stereotype"), "group": meta.get("group")}


def _component_of(by_id: dict[int, dict], nid: int) -> int | None:
    cur, guard = by_id.get(nid), 0
    while cur and guard < 32:
        if cur["type"] in OVERVIEW_TYPES or (cur["type"] == "REPOSITORY" and cur.get("repo_role") == "LIBRARY"):
            return cur["id"]
        cur = by_id.get(cur["parent_id"]) if cur["parent_id"] else None
        guard += 1
    return None


def overview(ctx: Context, project_id: int, user_id: int) -> dict:
    """Карта системы: сервисы, библиотеки, базы данных, топики, внешние системы."""
    access.require(ctx, project_id, user_id)
    g, by_id, edges, run = load(ctx, project_id)
    comp = {nid: _component_of(by_id, nid) for nid in by_id}
    visible = {c for c in comp.values() if c is not None}
    agg: dict[tuple[int, int, str], dict] = {}
    for e in edges:
        if e["rejected"]:
            continue
        a, b = comp.get(e["source_node_id"]), comp.get(e["target_node_id"])
        if a is None or b is None or a == b:
            continue
        key = (a, b, e["type"])
        cur = agg.get(key)
        direct = e["type"] != "IMPORTS"
        if cur is None:
            agg[key] = {"id": e["id"] if direct else f"code-{a}-{b}", "source": a, "target": b, "type": e["type"],
                        "confidence": e["confidence"], "verified": e["verified"], "evidence_count": e["evidence_count"],
                        "edge_id": e["id"] if direct else None, "count": 1}
        else:
            cur["count"] += 1
            cur["evidence_count"] += e["evidence_count"]
    # связь «использует код» не дублирует уже известную связь той же пары
    pairs = {(k[0], k[1]) for k in agg if k[2] != "IMPORTS"}
    out_edges = []
    for (a, b, t), v in agg.items():
        if t == "IMPORTS":
            if (a, b) in pairs:
                continue
            v["label"] = f"использует код ({v['count']})"
        out_edges.append(v)
    other = [{"id": n["id"], "name": n["name"], "role": n.get("repo_role"), "description": n["description"]}
             for n in by_id.values() if n["type"] == "REPOSITORY" and n.get("repo_role") not in ("LIBRARY", "SERVICE", "FRONTEND")]
    repo_health, comp_health = health(ctx, project_id, by_id, visible, out_edges)
    nodes = []
    for i in visible:
        j = _node_json(by_id[i])
        j["health"] = comp_health.get(i)
        j["links"] = len({e["target"] if e["source"] == i else e["source"] for e in out_edges if i in (e["source"], e["target"])})
        nodes.append(j)
    for o in other:
        o["health"] = repo_health.get(by_id[o["id"]]["repository_id"])
    return {"nodes": nodes, "edges": out_edges, "other_repositories": other, "repo_health": repo_health,
            "run": {"id": run["id"], "finished_at": run["finished_at"], "stats": run["stats"]}}


HEALTH_OK, HEALTH_WARN = 80, 50
_TEST_RX = r"(^|/)(tests?|__tests__|spec|specs)/|(^|/)test_[^/]*$|_test\.[a-z]+$|Tests?\.(java|kt|cs|scala)$|\.(spec|test)\.[jt]sx?$"


def health(ctx: Context, project_id: int, by_id: dict[int, dict], visible: set[int], edges: list[dict]):
    """Оценка «здоровья» репозитория 0–100: от 100 отнимаются баллы за найденные проблемы.

    ≥ 80 — норма, 50–79 — требует внимания, < 50 — плохо. Каждая причина видна пользователю.
    """
    repos = ctx.db.all(f"""SELECT r.id, r.name, r.status, r.role_confidence, r.detected_role,
                                  coalesce(sum(f.secrets_found), 0) AS secrets, count(f.id) AS files,
                                  coalesce(bool_or(f.path ~ '{_TEST_RX}'), false) AS has_tests,
                                  coalesce(bool_or(f.kind = 'README'), false) AS has_readme
                             FROM repositories r LEFT JOIN source_files f ON f.repository_id = r.id
                            WHERE r.project_id = %s GROUP BY r.id""", project_id)
    comp_of_repo = {}
    for cid in visible:
        n = by_id[cid]
        if n["type"] in ("SERVICE", "REPOSITORY") and n["repository_id"]:
            comp_of_repo[n["repository_id"]] = cid
    names = {cid: by_id[cid]["name"] for cid in visible}
    repo_h, comp_h = {}, {}
    for r in repos:
        score, reasons = 100, []

        def minus(points, text):
            nonlocal score
            score -= points
            reasons.append({"points": -points, "text": text})

        if r["status"] == "ERROR":
            minus(50, "Не удалось загрузить исходники")
        if r["files"] == 0:
            minus(30, "Нет проиндексированных файлов")
        if r["role_confidence"] < 0.7:
            minus(15, f"Роль определена неуверенно ({r['role_confidence']:.2f})")
        if r["secrets"]:
            minus(min(30, 10 * r["secrets"]), f"Секреты в коде: {r['secrets']} (скрыты при индексации, но их надо убрать из репозитория)")
        if not r["has_tests"] and r["detected_role"] in ("SERVICE", "FRONTEND", "LIBRARY"):
            minus(10, "Не найдено автотестов")
        if not r["has_readme"]:
            minus(5, "Нет README — назначение выведено из кода")
        cid = comp_of_repo.get(r["id"])
        if cid:
            mine = [e for e in edges if cid in (e["source"], e["target"])]
            low = [e for e in mine if e["confidence"] < 0.7 and not e["verified"]]
            if low:
                minus(min(30, 10 * len(low)), f"Связей с уверенностью ниже 0,7: {len(low)} — нужна проверка архитектора")
            dependents = {e["source"] for e in edges if e["target"] == cid}
            if len(dependents) >= 4:
                minus(10, f"От него зависят {len(dependents)} компонентов — изменения рискованны")
            outs = {e["target"] for e in edges if e["source"] == cid}
            for other in sorted({e["source"] for e in edges if e["target"] == cid} & outs):
                minus(15, f"Циклическая зависимость с {names.get(other, other)}")
        score = max(0, min(100, score))
        h = {"score": score, "level": "ok" if score >= HEALTH_OK else "warn" if score >= HEALTH_WARN else "bad", "reasons": reasons}
        repo_h[r["id"]] = h
        if cid:
            comp_h[cid] = h
    return repo_h, comp_h


def repo_health(ctx: Context, project_id: int, user_id: int) -> dict[int, dict]:
    if not latest_run(ctx, project_id):
        return {}
    return overview(ctx, project_id, user_id)["repo_health"]


def detailed(ctx: Context, project_id: int, user_id: int, repository_id: int | None = None,
             focus: int | None = None, depth: int = 2, limit: int = 160) -> dict:
    """Граф зависимостей кода выбранного репозитория (или окрестность класса)."""
    access.require(ctx, project_id, user_id)
    g, by_id, edges, run = load(ctx, project_id)
    code = {nid for nid, n in by_id.items() if n["type"] in CODE_TYPES}
    imports = [e for e in edges if e["type"] == "IMPORTS" and not e["rejected"]]
    if focus:
        if focus not in by_id:
            raise NotFound("Узел не найден")
        repository_id = by_id[focus]["repository_id"]
        keep, frontier = {focus}, {focus}
        adj = defaultdict(set)
        for e in imports:
            adj[e["source_node_id"]].add(e["target_node_id"])
            adj[e["target_node_id"]].add(e["source_node_id"])
        for _ in range(max(1, min(depth, 4))):
            frontier = {y for x in frontier for y in adj[x]} - keep
            keep |= frontier
    else:
        if repository_id is None:
            repos = ctx.db.all("SELECT r.id FROM repositories r WHERE r.project_id = %s "
                               "ORDER BY (r.detected_role = 'SERVICE') DESC, r.name", project_id)
            counts = defaultdict(int)
            for nid in code:
                counts[by_id[nid]["repository_id"]] += 1
            repository_id = max((r["id"] for r in repos), key=lambda rid: counts.get(rid, 0), default=None)
        own = {nid for nid in code if by_id[nid]["repository_id"] == repository_id}
        keep = set(own)
        for e in imports:  # классы других репозиториев, которые использует выбранный
            if e["source_node_id"] in own:
                keep.add(e["target_node_id"])
            if e["target_node_id"] in own:
                keep.add(e["source_node_id"])
    keep = set(sorted(keep, key=lambda i: (by_id[i]["repository_id"] != repository_id, by_id[i]["name"]))[:limit])
    nodes = []
    for nid in keep:
        n = by_id[nid]
        j = _node_json(n)
        parent = by_id.get(n["parent_id"])
        j["group"] = (n.get("repo_name") or "") + (" / " + parent["name"] if parent and parent["type"] == "MODULE" else "")
        j["external"] = repository_id is not None and n["repository_id"] != repository_id
        nodes.append(j)
    out_edges = [{"id": e["id"], "source": e["source_node_id"], "target": e["target_node_id"], "type": e["type"],
                  "confidence": e["confidence"], "verified": e["verified"], "edge_id": e["id"], "evidence_count": e["evidence_count"]}
                 for e in imports if e["source_node_id"] in keep and e["target_node_id"] in keep]
    return {"nodes": nodes, "edges": out_edges, "repository_id": repository_id, "focus": focus, "truncated": len(keep) >= limit}


def node_detail(ctx: Context, project_id: int, user_id: int, node_id: int) -> dict:
    access.require(ctx, project_id, user_id)
    n = ctx.db.one("""SELECT n.*, r.name AS repo_name, r.url AS repo_url, f.path AS file_path, f.language
                        FROM graph_nodes n LEFT JOIN repositories r ON r.id = n.repository_id
                        LEFT JOIN source_files f ON f.id = n.source_file_id
                       WHERE n.id = %s AND n.project_id = %s""", node_id, project_id)
    if not n:
        raise NotFound("Узел не найден: возможно, граф обновился — обновите страницу")

    def edge_list(direction: str):
        other = "target_node_id" if direction == "out" else "source_node_id"
        mine = "source_node_id" if direction == "out" else "target_node_id"
        return ctx.db.all(f"""SELECT e.id, e.type, e.confidence, e.verified, e.rejected, e.evidence,
                                     o.id AS node_id, o.name, o.type AS node_type
                                FROM graph_edges e JOIN graph_nodes o ON o.id = e.{other}
                               WHERE e.{mine} = %s ORDER BY e.type <> 'IMPORTS' DESC, e.confidence DESC, o.name""", node_id)

    children = ctx.db.all("SELECT id, type, name FROM graph_nodes WHERE parent_id = %s ORDER BY type, name LIMIT 200", node_id)
    parent = ctx.db.one("SELECT id, type, name FROM graph_nodes WHERE id = %s", n["parent_id"]) if n["parent_id"] else None
    files = {}
    for e in edge_list("out") + edge_list("in"):
        for ev in e["evidence"]:
            files[(ev.get("repo"), ev.get("path"))] = None
    file_ids = {}
    if files:
        for row in ctx.db.all("""SELECT f.id, f.path, r.name FROM source_files f JOIN repositories r ON r.id = f.repository_id
                                  WHERE r.project_id = %s""", project_id):
            if (row["name"], row["path"]) in files:
                file_ids[f"{row['name']}/{row['path']}"] = row["id"]
    out = {k: n[k] for k in ("id", "type", "name", "qualified_name", "description", "confidence", "verified", "metadata",
                             "repo_name", "repo_url", "file_path", "language", "start_line", "end_line", "source_file_id")}
    out["type_ru"] = TYPE_RU.get(n["type"], n["type"])
    out["outgoing"] = edge_list("out")
    out["incoming"] = edge_list("in")
    out["children"] = children
    out["parent"] = parent
    out["file_ids"] = file_ids
    out["edge_ru"] = EDGE_RU
    return out


def search_nodes(ctx: Context, project_id: int, user_id: int, q: str, types: list[str] | None = None, limit: int = 20) -> list[dict]:
    access.require(ctx, project_id, user_id)
    run = require_run(ctx, project_id)
    types = types or ["SERVICE", "REPOSITORY", "DATABASE", "MESSAGE_QUEUE", "EXTERNAL_SYSTEM", "CLASS", "ENTITY", "FUNCTION"]
    q = (q or "").strip()
    return ctx.db.all("""SELECT n.id, n.type, n.name, r.name AS repo_name
                           FROM graph_nodes n LEFT JOIN repositories r ON r.id = n.repository_id
                          WHERE n.run_id = %s AND n.type = ANY(%s) AND (%s = '' OR n.name ILIKE %s OR similarity(n.name, %s) > 0.25)
                          ORDER BY (n.type IN ('SERVICE','DATABASE','MESSAGE_QUEUE','EXTERNAL_SYSTEM')) DESC,
                                   similarity(n.name, %s) DESC, n.name LIMIT %s""",
                      run["id"], types, q, f"%{q}%", q, q, limit)


def verify(ctx: Context, project_id: int, user_id: int, subject: str, object_id: int, decision: str, description: str | None) -> dict:
    """Решение архитектора по выводу системы. Сохраняется и применяется при следующих анализах."""
    access.require(ctx, project_id, user_id, "verify")
    if decision not in ("CONFIRM", "REJECT"):
        raise BadRequest("Решение должно быть CONFIRM или REJECT")
    description = (description or "").strip()[:2000] or None
    if subject == "NODE":
        n = ctx.db.one("SELECT * FROM graph_nodes WHERE id = %s AND project_id = %s", object_id, project_id)
        if not n:
            raise NotFound("Узел не найден")
        if decision == "REJECT":
            raise BadRequest("Узел можно подтвердить или исправить описание; отклонить можно только связь")
        key = n["qualified_name"]
        ctx.db.run("UPDATE graph_nodes SET verified = true, confidence = 1, description = coalesce(%s, description) WHERE id = %s",
                   description, object_id)
    elif subject == "EDGE":
        e = ctx.db.one("""SELECT e.*, s.qualified_name AS sqn, t.qualified_name AS tqn FROM graph_edges e
                            JOIN graph_nodes s ON s.id = e.source_node_id JOIN graph_nodes t ON t.id = e.target_node_id
                           WHERE e.id = %s AND e.project_id = %s""", object_id, project_id)
        if not e:
            raise NotFound("Связь не найдена")
        key = f"{e['sqn']}|{e['type']}|{e['tqn']}"
        if decision == "CONFIRM":
            ctx.db.run("UPDATE graph_edges SET verified = true, rejected = false, confidence = 1 WHERE id = %s", object_id)
        else:
            ctx.db.run("UPDATE graph_edges SET rejected = true, verified = false WHERE id = %s", object_id)
    else:
        raise BadRequest("Неизвестный объект")
    ctx.db.run("""INSERT INTO verifications(project_id, subject, key, decision, description, user_id) VALUES (%s,%s,%s,%s,%s,%s)
                  ON CONFLICT (project_id, subject, key) DO UPDATE SET decision = EXCLUDED.decision,
                     description = EXCLUDED.description, user_id = EXCLUDED.user_id, created_at = now()""",
               project_id, subject, key, decision, description, user_id)
    return {"ok": True, "decision": decision}


def get_file(ctx: Context, project_id: int, user_id: int, file_id: int) -> dict:
    access.require(ctx, project_id, user_id)
    f = ctx.db.one("""SELECT f.id, f.path, f.language, f.kind, f.content, f.line_count, f.size_bytes, f.secrets_found, f.updated_at,
                             r.id AS repository_id, r.name AS repo_name, r.url AS repo_url, r.source_kind
                        FROM source_files f JOIN repositories r ON r.id = f.repository_id
                       WHERE f.id = %s AND r.project_id = %s""", file_id, project_id)
    if not f:
        raise NotFound("Файл не найден")
    f["symbols"] = ctx.db.all("SELECT id, type, name, start_line, end_line FROM graph_nodes WHERE source_file_id = %s "
                              "AND run_id = (SELECT max(run_id) FROM graph_nodes WHERE project_id = %s) ORDER BY start_line",
                              file_id, project_id)
    return f


def file_tree(ctx: Context, project_id: int, user_id: int, repository_id: int) -> list[dict]:
    access.require(ctx, project_id, user_id)
    return ctx.db.all("""SELECT f.id, f.path, f.kind, f.language, f.line_count FROM source_files f JOIN repositories r ON r.id = f.repository_id
                          WHERE r.project_id = %s AND r.id = %s ORDER BY f.path""", project_id, repository_id)
