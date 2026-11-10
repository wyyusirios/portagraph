"""Конвейер анализа проекта (UC-04 – UC-07).

QUEUED → FETCHING → INDEXING → ANALYZING → BUILDING_GRAPH → COMPLETED (или FAILED).
Выполняется в фоновом потоке; прогресс и журнал пишутся в analysis_runs, экран
«Прогресс анализа» опрашивает их раз в секунду.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import os
import pathlib
import posixpath
import re
import time
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from ..core import deps as deplib
from ..core import languages, purpose, roles, secrets, symbols
from ..core.chunker import CodeChunker
from ..core.text import expand_for_index
from ..db import Json
from . import access, gitops, repos as repolib
from .context import Context
from .errors import BadRequest, Conflict

log = logging.getLogger(__name__)

ACTIVE = ("QUEUED", "FETCHING", "INDEXING", "ANALYZING", "BUILDING_GRAPH")
ALLOWED = {
    "QUEUED": {"FETCHING", "CANCELLED", "FAILED"},
    "FETCHING": {"INDEXING", "FAILED", "CANCELLED"},
    "INDEXING": {"ANALYZING", "FAILED", "CANCELLED"},
    "ANALYZING": {"BUILDING_GRAPH", "FAILED", "CANCELLED"},
    "BUILDING_GRAPH": {"COMPLETED", "FAILED"},
    "COMPLETED": set(), "FAILED": set(), "CANCELLED": set(),
}
MIN_EDGE_CONFIDENCE = 0.35
COMPONENT_ROLES = ("SERVICE", "FRONTEND")
_chunker = CodeChunker(60, 10)


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Cancelled(Exception):
    pass


class AnalysisPipeline:
    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.pool = ThreadPoolExecutor(max_workers=max(1, ctx.settings.workers), thread_name_prefix="analysis")

    # ------------------------------------------------------------------ управление
    def recover_interrupted(self) -> int:
        return self.ctx.db.run(
            "UPDATE analysis_runs SET status = 'FAILED', finished_at = now(), "
            "error_message = 'Анализ прерван перезапуском сервера — запустите его снова' WHERE status = ANY(%s)", list(ACTIVE))

    def enqueue(self, project_id: int, trigger: str = "MANUAL", user_id: int | None = None, *, wait: bool = False) -> dict:
        if user_id is not None:
            access.require(self.ctx, project_id, user_id, "analyze")
        if not self.ctx.db.scalar("SELECT count(*) FROM repositories WHERE project_id = %s", project_id):
            raise BadRequest("Подключите хотя бы один репозиторий")
        with self.ctx.db.transaction() as c:
            c.execute("SELECT id FROM projects WHERE id = %s FOR UPDATE", (project_id,))
            if c.execute("SELECT 1 FROM analysis_runs WHERE project_id = %s AND status = ANY(%s)", (project_id, list(ACTIVE))).one():
                raise Conflict("Анализ проекта уже выполняется")
            run = c.execute("INSERT INTO analysis_runs(project_id, trigger_type, stage_message) VALUES (%s, %s, %s) RETURNING *",
                            (project_id, trigger, "В очереди")).one()
        if wait:
            self.execute(run["id"])
        else:
            self.pool.submit(self.execute, run["id"])
        return run

    def cancel(self, project_id: int, user_id: int) -> bool:
        access.require(self.ctx, project_id, user_id, "analyze")
        return self.ctx.db.run(
            "UPDATE analysis_runs SET status = 'CANCELLED', finished_at = now(), stage_message = 'Отменено пользователем' "
            "WHERE project_id = %s AND status = ANY(%s)", project_id, ["QUEUED", "FETCHING", "INDEXING", "ANALYZING"]) > 0

    # ------------------------------------------------------------------ состояние задачи
    def _status(self, run_id: int) -> str:
        return self.ctx.db.scalar("SELECT status FROM analysis_runs WHERE id = %s", run_id)

    def _move(self, run_id: int, nxt: str, progress: int | None = None, message: str | None = None):
        cur = self._status(run_id)
        if cur == "CANCELLED":
            raise Cancelled()
        if nxt not in ALLOWED[cur]:
            raise RuntimeError(f"Недопустимый переход {cur} → {nxt}")
        sets, params = ["status = %s"], [nxt]
        if cur == "QUEUED" and nxt == "FETCHING":
            sets.append("started_at = now()")
        if nxt in ("COMPLETED", "FAILED", "CANCELLED"):
            sets.append("finished_at = now()")
        if progress is not None:
            sets.append("progress = %s")
            params.append(progress)
        if message is not None:
            sets.append("stage_message = %s")
            params.append(message)
        self.ctx.db.run(f"UPDATE analysis_runs SET {', '.join(sets)} WHERE id = %s", *params, run_id)

    def _progress(self, run_id: int, progress: int, message: str | None = None):
        if self._status(run_id) == "CANCELLED":
            raise Cancelled()
        self.ctx.db.run("UPDATE analysis_runs SET progress = %s, stage_message = coalesce(%s, stage_message) WHERE id = %s",
                        progress, message, run_id)

    def _log(self, run_id: int, text: str, level: str = "info"):
        entry = [{"t": now().strftime("%H:%M:%S"), "level": level, "text": text[:400]}]
        self.ctx.db.run("UPDATE analysis_runs SET log = log || %s::jsonb WHERE id = %s", Json(entry), run_id)

    # ------------------------------------------------------------------ запуск
    def execute(self, run_id: int) -> None:
        ctx = self.ctx
        run = ctx.db.one("SELECT * FROM analysis_runs WHERE id = %s", run_id)
        pid = run["project_id"]
        t0 = time.time()
        try:
            self._move(run_id, "FETCHING", 3, "Загрузка исходников")
            repos = ctx.db.all("SELECT * FROM repositories WHERE project_id = %s ORDER BY name", pid)
            fetched = self._fetch_all(run_id, repos)
            if not fetched:
                raise BadRequest("Не удалось получить исходники ни одного репозитория")

            self._move(run_id, "INDEXING", 15, "Индексация кода и документации")
            idx = {"indexed": 0, "unchanged": 0, "skipped": 0, "secrets": 0, "removed": 0}
            for i, repo in enumerate(fetched):
                s = self._index_repo(pid, repo)
                for k in idx:
                    idx[k] += s[k]
                self._log(run_id, f"{repo['name']}: проиндексировано {s['indexed']}, без изменений {s['unchanged']}"
                                  + (f", скрыто секретов: {s['secrets']}" if s["secrets"] else ""))
                self._progress(run_id, 15 + int(35 * (i + 1) / len(fetched)))

            self._move(run_id, "ANALYZING", 52, "Анализ назначения репозиториев")
            model = self._analyze(run_id, pid, fetched)

            self._move(run_id, "BUILDING_GRAPH", 76, "Построение единого графа")
            gstats = self._build_graph(run_id, pid, model)

            ctx.db.run("DELETE FROM graph_nodes WHERE project_id = %s AND run_id <> %s", pid, run_id)
            outdated = ctx.db.run("UPDATE generated_documents SET status = 'OUTDATED' "
                                  "WHERE project_id = %s AND status <> 'OUTDATED' AND coalesce(run_id, 0) <> %s", pid, run_id)
            for r in fetched:
                ctx.db.run("UPDATE repositories SET status = 'READY', status_message = NULL, last_synced_at = now() WHERE id = %s", r["id"])
            stats = {"repositories": len(fetched), "files_indexed": idx["indexed"], "files_unchanged": idx["unchanged"],
                     "files_skipped": idx["skipped"], "secrets_redacted": idx["secrets"], **gstats,
                     "documents_outdated": outdated, "duration_sec": round(time.time() - t0, 1)}
            ctx.db.run("UPDATE analysis_runs SET stats = %s WHERE id = %s", Json(stats), run_id)
            self._log(run_id, f"Готово за {stats['duration_sec']} с: узлов {gstats['nodes']}, связей {gstats['edges']}, "
                              f"межрепозиторных {gstats['cross_repo_links']}")
            self._move(run_id, "COMPLETED", 100, "Анализ завершён")
        except Cancelled:
            self._log(run_id, "Анализ отменён", "warn")
        except Exception as e:  # noqa: BLE001 — любая ошибка должна перевести задачу в FAILED
            msg = getattr(e, "message", None) or f"{type(e).__name__}: {e}"
            log.error("Анализ %s завершился ошибкой\n%s", run_id, traceback.format_exc())
            try:
                self._log(run_id, msg, "error")
                if self._status(run_id) in ACTIVE:
                    self._move(run_id, "FAILED", None, "Ошибка анализа")
                    ctx.db.run("UPDATE analysis_runs SET error_message = %s WHERE id = %s", msg[:2000], run_id)
            except Exception:  # noqa: BLE001
                log.exception("Не удалось записать ошибку анализа")

    # ------------------------------------------------------------------ FETCHING
    def _fetch_all(self, run_id: int, repos: list[dict]) -> list[dict]:
        ok = []
        for i, repo in enumerate(repos):
            try:
                sha = self._fetch(repo)
                self.ctx.db.run("UPDATE repositories SET status = 'INDEXING', status_message = NULL, last_commit_sha = %s WHERE id = %s",
                                sha, repo["id"])
                repo["last_commit_sha"] = sha
                ok.append(repo)
                self._log(run_id, f"{repo['name']}: исходники получены" + (f" (коммит {sha[:8]})" if sha and len(sha) >= 8 and repo['source_kind'] == 'git' else ""))
            except Exception as e:  # noqa: BLE001
                msg = getattr(e, "message", str(e))
                self.ctx.db.run("UPDATE repositories SET status = 'ERROR', status_message = %s WHERE id = %s", msg[:500], repo["id"])
                self._log(run_id, f"{repo['name']}: {msg}", "error")
            self._progress(run_id, 3 + int(12 * (i + 1) / max(1, len(repos))))
        return ok

    def _fetch(self, repo: dict) -> str | None:
        dest = repolib.repo_dir(self.ctx, repo["project_id"], repo["id"])
        kind = repo["source_kind"]
        if kind == "git":
            git = gitops.parse_url(repo["url"])
            return gitops.clone_or_pull(git, dest, repolib.token_for(self.ctx, repo), repo.get("default_branch"))
        if kind == "demo":
            gitops.copy_demo(repo["url"].rsplit("/", 1)[-1], dest)
            return "demo"
        if kind == "zip":
            if not dest.is_dir():
                raise BadRequest("Распакованный архив не найден — загрузите ZIP заново")
            return "zip"
        if kind == "local":
            if not pathlib.Path(repo["local_path"]).is_dir():
                raise BadRequest(f"Папка недоступна: {repo['local_path']}")
            return "local"
        raise BadRequest(f"Неизвестный источник {kind}")

    # ------------------------------------------------------------------ INDEXING
    def _walk(self, root: pathlib.Path):
        count = 0
        for d, dirs, files in os.walk(root):
            dirs[:] = sorted(x for x in dirs if not languages.should_skip_dir(x))
            for fn in sorted(files):
                full = pathlib.Path(d) / fn
                rel = full.relative_to(root).as_posix()
                yield rel, full
                count += 1
                if count >= languages.MAX_FILES_PER_REPO:
                    return

    def _index_repo(self, project_id: int, repo: dict) -> dict:
        db = self.ctx.db
        root = repolib.workdir(self.ctx, repo)
        existing = {r["path"]: r for r in db.all("SELECT id, path, content_sha FROM source_files WHERE repository_id = %s", repo["id"])}
        seen: set[str] = set()
        st = {"indexed": 0, "unchanged": 0, "skipped": 0, "secrets": 0, "removed": 0}
        for rel, full in self._walk(root):
            kind = languages.kind_of(rel)
            if kind is None or secrets.is_secret_file(rel):
                st["skipped"] += 1
                continue
            try:
                if full.is_symlink() or full.stat().st_size > languages.MAX_FILE_BYTES:
                    st["skipped"] += 1
                    continue
                raw = full.read_bytes()
            except OSError:
                st["skipped"] += 1
                continue
            if b"\x00" in raw[:4096]:
                st["skipped"] += 1
                continue
            seen.add(rel)
            sha = hashlib.sha1(raw).hexdigest()
            prev = existing.get(rel)
            if prev and prev["content_sha"] == sha:
                st["unchanged"] += 1
                continue
            text = raw.decode("utf-8", errors="replace")
            scan = secrets.scan(text)
            st["secrets"] += len(scan.findings)
            lang = languages.language_of(rel)
            content = scan.sanitized
            with db.transaction() as c:
                f = c.execute("""INSERT INTO source_files(repository_id, path, language, kind, content_sha, size_bytes,
                                                         line_count, content, secrets_found, updated_at)
                                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                                 ON CONFLICT (repository_id, path) DO UPDATE SET language = EXCLUDED.language, kind = EXCLUDED.kind,
                                    content_sha = EXCLUDED.content_sha, size_bytes = EXCLUDED.size_bytes, line_count = EXCLUDED.line_count,
                                    content = EXCLUDED.content, secrets_found = EXCLUDED.secrets_found, updated_at = now()
                                 RETURNING id""",
                              (repo["id"], rel, lang, kind, sha, len(raw), content.count("\n") + 1, content, len(scan.findings))).one()
                c.execute("DELETE FROM code_chunks WHERE source_file_id = %s", (f["id"],))
                spans = symbols.analyze_file(rel, content, lang).symbols if kind == "CODE" else None
                for ch in _chunker.chunk(content, spans):
                    head = f"{repo['name']} {rel} {ch.symbol or ''}"
                    c.execute("""INSERT INTO code_chunks(source_file_id, project_id, start_line, end_line, symbol, search_text, content)
                                 VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                              (f["id"], project_id, ch.start_line, ch.end_line, ch.symbol,
                               f"{head} {expand_for_index(head + ' ' + ch.content)} {ch.content}", ch.content))
            st["indexed"] += 1
        gone = [r["id"] for p, r in existing.items() if p not in seen]
        if gone:
            st["removed"] = db.run("DELETE FROM source_files WHERE id = ANY(%s)", gone)
        return st

    # ------------------------------------------------------------------ ANALYZING
    def _analyze(self, run_id: int, project_id: int, repos: list[dict]) -> dict:
        db = self.ctx.db
        model = {"repos": {}, "files": {}}
        rows = db.all("""SELECT f.id, f.repository_id, f.path, f.kind, f.language, f.content
                           FROM source_files f JOIN repositories r ON r.id = f.repository_id
                          WHERE r.project_id = %s AND r.id = ANY(%s)""", project_id, [r["id"] for r in repos])
        by_repo: dict[int, list[dict]] = defaultdict(list)
        for f in rows:
            by_repo[f["repository_id"]].append(f)
        for i, repo in enumerate(repos):
            files = by_repo.get(repo["id"], [])
            manifests = {f["path"].lower(): f["content"] for f in files if "/" not in f["path"]}
            readme = next((f["content"] for f in sorted(files, key=lambda x: x["path"].count("/"))
                           if f["kind"] == "README"), None)
            structures = {}
            endpoints = 0
            for f in files:
                if f["kind"] == "CODE":
                    s = symbols.analyze_file(f["path"], f["content"], f["language"])
                    structures[f["id"]] = s
                    endpoints += len(s.endpoints)
            cl = roles.classify([f["path"] for f in files], manifests)
            text, source = purpose.summarize(cl.role, cl.stack, endpoints, readme, manifests)
            db.run("UPDATE repositories SET detected_role = %s, role_confidence = %s, purpose_summary = %s WHERE id = %s",
                   cl.role, cl.confidence, text, repo["id"])
            model["repos"][repo["id"]] = {
                "repo": repo, "files": files, "structures": structures, "classification": cl, "purpose": text,
                "purpose_source": source, "aliases": deplib.repo_aliases(repo["name"], manifests), "endpoints": endpoints,
                "loc": sum(f["content"].count("\n") + 1 for f in files if f["kind"] == "CODE"),
            }
            for f in files:
                model["files"][f["id"]] = f
            self._log(run_id, f"{repo['name']} → {cl.role} ({cl.confidence:.2f}) «{text[:90]}{'…' if len(text) > 90 else ''}»")
            self._progress(run_id, 52 + int(22 * (i + 1) / len(repos)))
        return model

    # ------------------------------------------------------------------ BUILDING_GRAPH
    def _build_graph(self, run_id: int, project_id: int, model: dict) -> dict:
        db = self.ctx.db
        verif = {(v["subject"], v["key"]): v for v in db.all("SELECT * FROM verifications WHERE project_id = %s", project_id)}
        qn_to_id: dict[str, int] = {}
        stats = {"nodes": 0, "edges": 0, "cross_repo_links": 0, "code_links": 0, "endpoints": 0, "low_confidence_links": 0}
        project = db.one("SELECT name FROM projects WHERE id = %s", project_id)

        def node(type_, name, qn, parent=None, repo_id=None, file_id=None, lines=None, desc=None, conf=1.0, meta=None):
            v = verif.get(("NODE", qn))
            verified = bool(v and v["decision"] == "CONFIRM")
            if v and v.get("description"):
                desc = v["description"]
            nid = db.scalar("""INSERT INTO graph_nodes(project_id, run_id, type, name, qualified_name, repository_id, source_file_id,
                                                        start_line, end_line, parent_id, description, confidence, verified, metadata)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                            project_id, run_id, type_, name[:300], qn[:1000], repo_id, file_id,
                            lines[0] if lines else None, lines[1] if lines else None, parent, (desc or None) and desc[:2000],
                            1.0 if verified else round(conf, 3), verified, Json(meta or {}))
            qn_to_id[qn] = nid
            stats["nodes"] += 1
            return nid

        edges: dict[tuple[int, int, str], dict] = {}

        def edge(src_qn, tgt_qn, type_, conf, evidence):
            s, t = qn_to_id.get(src_qn), qn_to_id.get(tgt_qn)
            if s is None or t is None or s == t:
                return
            key = (s, t, type_)
            e = edges.setdefault(key, {"src_qn": src_qn, "tgt_qn": tgt_qn, "confs": [], "evidence": []})
            e["confs"].append(conf)
            e["evidence"].extend(evidence)

        system = node("SYSTEM", project["name"], "system")
        component_qn: dict[str, str] = {}
        repo_by_name = {m["repo"]["name"]: m for m in model["repos"].values()}

        # ---- репозитории, сервисы, модули, классы
        symbol_index: dict[str, str] = {}        # fqn → qn узла
        package_members: dict[str, dict[str, str]] = defaultdict(dict)
        file_symbols: dict[int, list[tuple]] = {}
        for rid, m in model["repos"].items():
            repo, cl = m["repo"], m["classification"]
            all_eps = [dict(ep, file=m_f["path"]) for fid, s in m["structures"].items() for ep in s.endpoints
                       for m_f in [model["files"][fid]]]
            stats["endpoints"] += len(all_eps)
            rmeta = {"role": cl.role, "reasons": cl.reasons, "stack": cl.stack, "source_kind": repo["source_kind"],
                     "url": repo["url"], "purpose_source": m["purpose_source"], "files": len(m["files"]), "loc": m["loc"]}
            rqn = f"repo:{repo['name']}"
            r_id = node("REPOSITORY", repo["name"], rqn, system, rid, desc=m["purpose"], conf=cl.confidence, meta=rmeta)
            comp_qn = rqn
            comp_id = r_id
            if cl.role in COMPONENT_ROLES:
                comp_qn = f"service:{repo['name']}"
                comp_id = node("SERVICE", repo["name"], comp_qn, r_id, rid, desc=m["purpose"], conf=cl.confidence,
                               meta={**rmeta, "endpoints": all_eps[:200]})
            component_qn[repo["name"]] = comp_qn

            # модули: пакет (JVM) или каталог файла
            pkgs = [s.package for s in m["structures"].values() if s.package and s.language in ("java", "kotlin", "scala", "csharp")]
            common = _common_prefix([p.split(".") for p in pkgs]) if pkgs else []
            module_ids: dict[str, int] = {}

            def module_for(f, s) -> int:
                if s.package and s.language in ("java", "kotlin", "scala", "csharp"):
                    rest = s.package.split(".")[len(common):]
                    mname = rest[0] if rest else (s.package.split(".")[-1] if s.package else "(корень)")
                else:
                    parts = f["path"].split("/")[:-1]
                    parts = [p for p in parts if p not in ("src", "main", "lib", "java", "kotlin")] or ["(корень)"]
                    mname = "/".join(parts[:2])
                if mname not in module_ids:
                    module_ids[mname] = node("MODULE", mname, f"module:{repo['name']}:{mname}", comp_id, rid,
                                             meta={"language": s.language})
                return module_ids[mname]

            for fid, s in sorted(m["structures"].items(), key=lambda kv: model["files"][kv[0]]["path"]):
                f = model["files"][fid]
                tops = [x for x in s.symbols if not any(o is not x and o.start_line <= x.start_line and x.end_line <= o.end_line
                                                        and (o.end_line - o.start_line) > (x.end_line - x.start_line) for o in s.symbols)]
                if s.language in ("java", "kotlin", "scala", "csharp"):
                    tops = [x for x in tops if x.kind != "function"]
                if not tops:
                    continue
                mod_id = module_for(f, s)
                lst = []
                for sym in tops:
                    is_entity = sym.name in s.entities
                    ntype = "ENTITY" if is_entity else ("FUNCTION" if sym.kind == "function" else "CLASS")
                    qn = f"class:{repo['name']}:{f['path']}#{sym.name}"
                    eps = [ep for ep in s.endpoints if ep.get("symbol") == sym.name]
                    meta = {"kind": sym.kind, "language": s.language, "path": f["path"]}
                    if s.stereotypes.get(sym.name):
                        meta["stereotype"] = s.stereotypes[sym.name]
                    if is_entity:
                        meta["table"] = s.entities[sym.name]
                    if eps:
                        meta["endpoints"] = eps
                    node(ntype, sym.name, qn, mod_id, rid, fid, (sym.start_line, sym.end_line), meta=meta)
                    lst.append((sym, qn))
                    if s.package:
                        fq = f"{s.package}.{sym.name}" if s.language != "typescript" and s.language != "javascript" else f"{f['path']}#{sym.name}"
                        symbol_index[fq] = qn
                        package_members[s.package][sym.name] = qn
                file_symbols[fid] = lst

        # ---- связи между классами по импортам и использованию имён
        path_index = {(model["files"][fid]["repository_id"], model["files"][fid]["path"]): fid for fid in file_symbols}
        for rid, m in model["repos"].items():
            repo_paths = {model["files"][fid]["path"] for fid in file_symbols if model["files"][fid]["repository_id"] == rid}
            for fid, s in m["structures"].items():
                if fid not in file_symbols:
                    continue
                f = model["files"][fid]
                visible: dict[str, str] = {}
                if s.language in ("java", "kotlin", "scala", "csharp"):
                    visible.update(package_members.get(s.package or "", {}))
                    for imp in s.imports:
                        if imp in symbol_index:
                            visible[imp.rsplit(".", 1)[-1]] = symbol_index[imp]
                        elif imp in package_members:
                            visible.update(package_members[imp])
                        else:  # импорт вложенного типа: a.b.Outer.Inner → Outer
                            head = imp.rsplit(".", 1)[0]
                            if head in symbol_index:
                                visible[head.rsplit(".", 1)[-1]] = symbol_index[head]
                elif s.language == "python":
                    for imp in s.imports:
                        if imp in symbol_index:
                            visible[imp.rsplit(".", 1)[-1]] = symbol_index[imp]
                        elif imp in package_members:
                            visible.update(package_members[imp])
                    visible.update({k: v for k, v in package_members.get(s.package or "", {}).items()})
                elif s.language in ("typescript", "javascript"):
                    for imp in s.imports:
                        target = symbols.resolve_ts_import(f["path"], imp, repo_paths)
                        tf = path_index.get((rid, target)) if target else None
                        if tf:
                            for sym, qn in file_symbols[tf]:
                                visible[sym.name] = qn
                if not visible:
                    continue
                lines = f["content"].split("\n")
                names = list(visible.items())[:300]
                for sym, sqn in file_symbols[fid]:
                    body = "\n".join(lines[sym.start_line - 1: sym.end_line])
                    for name, tqn in names:
                        if tqn == sqn or name == sym.name:
                            continue
                        mm = re.search(rf"(?<![\w$]){re.escape(name)}(?![\w$])", body)
                        if mm:
                            ln = sym.start_line + body.count("\n", 0, mm.start())
                            edge(sqn, tqn, "IMPORTS", 1.0, [{"repo": m["repo"]["name"], "path": f["path"], "line": ln,
                                                             "snippet": lines[ln - 1].strip()[:240], "rule": "использование класса"}])

        # ---- межрепозиторные связи
        inputs = [deplib.RepoInput(m["repo"]["name"],
                                   [(f["path"], f["kind"], f["language"], f["content"]) for f in m["files"]],
                                   m["aliases"]) for m in model["repos"].values()]
        links = deplib.LinkExtractor(inputs).extract()
        grouped: dict[tuple, list] = defaultdict(list)
        for lk in links:
            grouped[(lk.source, lk.edge_type, lk.target_kind, lk.target)].append(lk)
        extra_nodes: dict[str, str] = {}

        def target_node(kind: str, target: str, meta: dict) -> str | None:
            if kind == "REPOSITORY":
                return component_qn.get(target)
            if kind == "TOPIC":
                qn = f"topic:{target}"
                if qn not in qn_to_id:
                    node("MESSAGE_QUEUE", target, qn, system, desc=f"Топик {meta.get('broker', 'брокера сообщений')}",
                         meta={"broker": meta.get("broker")})
                return qn
            if kind == "DATABASE":
                engine = meta.get("engine", "БД")
                qn = f"db:{target}"
                if qn not in qn_to_id:
                    node("DATABASE", target, qn, system, desc=f"База данных {engine}", meta={"engine": engine, "host": meta.get("host")})
                return qn
            if kind == "EXTERNAL":
                qn = f"ext:{target}"
                if qn not in qn_to_id:
                    node("EXTERNAL_SYSTEM", target, qn, system, desc="Внешняя система (вызов по HTTPS)")
                return qn
            return None

        compose_only: list[tuple] = []
        for (src, etype, tkind, target), items in grouped.items():
            sqn = component_qn.get(src)
            tqn = target_node(tkind, target, items[0].meta)
            if not sqn or not tqn:
                continue
            ev = [lk.evidence.as_dict() for lk in items]
            if etype == "DEPENDS_ON" and all(lk.evidence.rule == "depends_on в docker-compose" for lk in items):
                compose_only.append((sqn, tqn, items, ev))
                continue
            edge(sqn, tqn, etype, None, ev)
            edges[(qn_to_id[sqn], qn_to_id[tqn], etype)]["link_confs"] = [lk.confidence for lk in items]
        # depends_on из docker-compose усиливает уже найденную связь той же пары, а не дублирует её
        for sqn, tqn, items, ev in compose_only:
            s, t = qn_to_id[sqn], qn_to_id[tqn]
            same = [k for k in edges if k[0] == s and k[1] == t]
            if same:
                e = edges[same[0]]
                e.setdefault("link_confs", []).extend(lk.confidence for lk in items)
                e["evidence"].extend(ev)
            else:
                edge(sqn, tqn, "DEPENDS_ON", None, ev)
                edges[(s, t, "DEPENDS_ON")]["link_confs"] = [lk.confidence for lk in items]

        # ---- запись рёбер
        for (s, t, etype), e in edges.items():
            if "link_confs" in e:
                conf = deplib.combine(e["link_confs"])
            else:
                conf = deplib.combine([c for c in e["confs"] if c is not None]) if etype != "IMPORTS" else 1.0
            if conf < MIN_EDGE_CONFIDENCE:
                continue
            key = f"{e['src_qn']}|{etype}|{e['tgt_qn']}"
            v = verif.get(("EDGE", key))
            verified = bool(v and v["decision"] == "CONFIRM")
            rejected = bool(v and v["decision"] == "REJECT")
            db.run("""INSERT INTO graph_edges(project_id, run_id, source_node_id, target_node_id, type, confidence, verified, rejected, evidence)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                   project_id, run_id, s, t, etype, 1.0 if verified else conf, verified, rejected, Json(e["evidence"][:25]))
            stats["edges"] += 1
            if etype == "IMPORTS":
                stats["code_links"] += 1
            else:
                stats["cross_repo_links"] += 1
                if conf < 0.7 and not verified:
                    stats["low_confidence_links"] += 1
        self._log(run_id, f"Связей между компонентами: {stats['cross_repo_links']} "
                          f"(требуют проверки: {stats['low_confidence_links']}), связей в коде: {stats['code_links']}")
        self._progress(run_id, 96, "Сохранение графа")
        return stats


def _common_prefix(lists: list[list[str]]) -> list[str]:
    if not lists:
        return []
    out = []
    for parts in zip(*lists):
        if all(p == parts[0] for p in parts):
            out.append(parts[0])
        else:
            break
    # общий префикс пакета не должен съедать весь пакет единственного класса
    shortest = min(len(x) for x in lists)
    return out[: max(0, min(len(out), shortest - 1))]
