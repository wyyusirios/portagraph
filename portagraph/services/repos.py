"""Подключение репозиториев к проекту (UC-03). Роли пользователь не указывает."""
from __future__ import annotations

import pathlib
import re
import secrets
import tempfile

from ..db import UniqueViolation
from . import access, gitops
from .context import Context
from .errors import AppError, BadRequest, NotFound

MAX_URLS = 50


def repo_dir(ctx: Context, project_id: int, repo_id: int) -> pathlib.Path:
    return ctx.settings.data_dir / "repos" / str(project_id) / str(repo_id)


def workdir(ctx: Context, repo: dict) -> pathlib.Path:
    """Каталог с исходниками репозитория."""
    if repo["source_kind"] == "local":
        return pathlib.Path(repo["local_path"])
    return repo_dir(ctx, repo["project_id"], repo["id"])


def list_repos(ctx: Context, project_id: int, user_id: int) -> list[dict]:
    access.require(ctx, project_id, user_id)
    return ctx.db.all("""SELECT r.id, r.name, r.url, r.provider, r.source_kind, r.default_branch, r.detected_role,
                                r.role_confidence, r.purpose_summary, r.status, r.status_message, r.last_commit_sha,
                                r.last_synced_at, r.created_at, r.credential_id IS NOT NULL AS has_token,
                                (SELECT count(*) FROM source_files f WHERE f.repository_id = r.id) AS file_count
                           FROM repositories r WHERE r.project_id = %s ORDER BY r.name""", project_id)


def _unique_name(ctx: Context, project_id: int, name: str) -> str:
    base, n = re.sub(r"[^\w.\-]", "-", name)[:180] or "repo", 1
    cand = base
    while ctx.db.scalar("SELECT 1 FROM repositories WHERE project_id = %s AND name = %s", project_id, cand):
        n += 1
        cand = f"{base}-{n}"
    return cand


def connect_git(ctx: Context, project_id: int, user_id: int, urls: list[str], token: str | None) -> list[dict]:
    """Проверяет доступ к каждому адресу и сохраняет подключённые. Ошибка по одному адресу
    не мешает подключить остальные."""
    access.require(ctx, project_id, user_id, "manage_repos")
    clean = list(dict.fromkeys(u.strip() for u in urls if u and u.strip()))
    if not clean:
        raise BadRequest("Укажите хотя бы один адрес репозитория")
    if len(clean) > MAX_URLS:
        raise BadRequest(f"Не более {MAX_URLS} адресов за один раз")
    token = (token or "").strip() or None
    results, cred_id = [], None
    for raw in clean:
        try:
            git = gitops.parse_url(raw)
            if ctx.db.scalar("SELECT 1 FROM repositories WHERE project_id = %s AND url = %s", project_id, git.url):
                results.append({"url": raw, "ok": False, "message": "Уже подключён"})
                continue
            branch = gitops.check_access(git, token)
            if token and cred_id is None:
                cred_id = ctx.db.scalar("INSERT INTO repo_credentials(project_id, provider, encrypted_token) "
                                        "VALUES (%s, %s, %s) RETURNING id", project_id, git.provider, ctx.encrypt(token))
            repo = ctx.db.one("""INSERT INTO repositories(project_id, source_kind, provider, url, name, default_branch,
                                                          credential_id, webhook_secret)
                                 VALUES (%s, 'git', %s, %s, %s, %s, %s, %s) RETURNING id, name""",
                              project_id, git.provider, git.url, _unique_name(ctx, project_id, git.name), branch,
                              cred_id, secrets.token_hex(24))
            results.append({"url": raw, "ok": True, "message": f"Подключён · ветка {branch or 'по умолчанию'}",
                            "repository_id": repo["id"], "name": repo["name"]})
        except AppError as e:
            results.append({"url": raw, "ok": False, "message": e.message})
        except UniqueViolation:
            results.append({"url": raw, "ok": False, "message": "Уже подключён"})
    return results


def connect_zip(ctx: Context, project_id: int, user_id: int, filename: str, stream, name: str | None) -> dict:
    access.require(ctx, project_id, user_id, "manage_repos")
    stem = (name or "").strip() or re.sub(r"\.zip$", "", pathlib.Path(filename or "archive.zip").name, flags=re.I)
    repo = ctx.db.one("""INSERT INTO repositories(project_id, source_kind, url, name, webhook_secret)
                         VALUES (%s, 'zip', %s, %s, %s) RETURNING *""",
                      project_id, f"zip://{secrets.token_hex(6)}/{stem}", _unique_name(ctx, project_id, stem), secrets.token_hex(24))
    limit = ctx.settings.max_upload_mb * 1024 * 1024
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            size = 0
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise BadRequest(f"Архив больше {ctx.settings.max_upload_mb} МБ")
                tmp.write(chunk)
        gitops.extract_zip(pathlib.Path(tmp.name), repo_dir(ctx, project_id, repo["id"]), limit * 4)
    except Exception:
        ctx.db.run("DELETE FROM repositories WHERE id = %s", repo["id"])
        raise
    finally:
        pathlib.Path(tmp.name).unlink(missing_ok=True)
    return repo


def connect_local(ctx: Context, project_id: int, user_id: int, path: str) -> dict:
    access.require(ctx, project_id, user_id, "manage_repos")
    if not ctx.settings.allow_local_paths:
        raise BadRequest("Подключение локальных папок отключено настройкой ALLOW_LOCAL_PATHS")
    p = pathlib.Path((path or "").strip().strip('"')).expanduser()
    if not p.is_dir():
        raise BadRequest(f"Папка не найдена: {path}")
    p = p.resolve()
    try:
        return ctx.db.one("""INSERT INTO repositories(project_id, source_kind, url, name, local_path, webhook_secret)
                             VALUES (%s, 'local', %s, %s, %s, %s) RETURNING *""",
                          project_id, p.as_uri(), _unique_name(ctx, project_id, p.name), str(p), secrets.token_hex(24))
    except UniqueViolation:
        raise BadRequest("Эта папка уже подключена") from None


def connect_demo(ctx: Context, project_id: int, user_id: int) -> list[dict]:
    """Подключает 9 репозиториев демо-системы ShopFlow (работает без интернета)."""
    access.require(ctx, project_id, user_id, "manage_repos")
    out = []
    for name in gitops.demo_repositories():
        url = f"demo://shopflow/{name}"
        if ctx.db.scalar("SELECT 1 FROM repositories WHERE project_id = %s AND url = %s", project_id, url):
            continue
        repo = ctx.db.one("""INSERT INTO repositories(project_id, source_kind, url, name, webhook_secret)
                             VALUES (%s, 'demo', %s, %s, %s) RETURNING id, name""",
                          project_id, url, _unique_name(ctx, project_id, name), secrets.token_hex(24))
        out.append(repo)
    return out


def disconnect(ctx: Context, project_id: int, user_id: int, repo_id: int) -> None:
    access.require(ctx, project_id, user_id, "manage_repos")
    repo = ctx.db.one("SELECT * FROM repositories WHERE id = %s AND project_id = %s", repo_id, project_id)
    if not repo:
        raise NotFound("Репозиторий не найден")
    ctx.db.run("DELETE FROM repositories WHERE id = %s", repo_id)
    if repo["source_kind"] != "local":
        import shutil
        shutil.rmtree(repo_dir(ctx, project_id, repo_id), ignore_errors=True)


def token_for(ctx: Context, repo: dict) -> str | None:
    if not repo.get("credential_id"):
        return None
    data = ctx.db.scalar("SELECT encrypted_token FROM repo_credentials WHERE id = %s", repo["credential_id"])
    return ctx.decrypt(data) if data else None
