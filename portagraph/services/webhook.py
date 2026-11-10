"""Синхронизация с репозиториями (UC-14): веб-хуки GitHub / GitLab / Bitbucket и ручная синхронизация.

* подпись GitHub ``X-Hub-Signature-256`` (HMAC-SHA256 от тела) или токен GitLab ``X-Gitlab-Token``;
* идемпотентность: повторная доставка с тем же идентификатором не запускает анализ;
* события не для ветки по умолчанию игнорируются;
* если анализ проекта уже идёт, событие сохраняется и обрабатывается следующим запуском.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from . import access
from .context import Context
from .errors import BadRequest, Conflict, Forbidden, NotFound


def verify_signature(secret: str, body: bytes, headers) -> bool:
    sig = headers.get("X-Hub-Signature-256") or headers.get("X-Hub-Signature")
    if sig:
        algo, _, value = sig.partition("=")
        fn = hashlib.sha256 if algo == "sha256" else hashlib.sha1
        expected = hmac.new(secret.encode(), body, fn).hexdigest()
        return hmac.compare_digest(expected, value)
    token = headers.get("X-Gitlab-Token")
    if token:
        return hmac.compare_digest(token, secret)
    return False


def _parse(headers, payload: dict) -> tuple[str, str | None, str | None, str]:
    event = headers.get("X-GitHub-Event") or headers.get("X-Gitlab-Event") or headers.get("X-Event-Key") or "push"
    delivery = (headers.get("X-GitHub-Delivery") or headers.get("X-Gitlab-Event-UUID") or headers.get("X-Request-UUID")
                or hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:40])
    ref = payload.get("ref") or ""
    branch = ref.rsplit("/", 1)[-1] if ref.startswith("refs/heads/") else None
    sha = payload.get("after") or payload.get("checkout_sha")
    if not branch and "push" in payload:  # Bitbucket
        changes = payload["push"].get("changes") or []
        new = (changes[0] or {}).get("new") if changes else None
        if new:
            branch = new.get("name")
            sha = (new.get("target") or {}).get("hash")
    return event.lower(), branch, sha, delivery


def handle(ctx: Context, pipeline, repo_id: int, body: bytes, headers) -> dict:
    repo = ctx.db.one("SELECT * FROM repositories WHERE id = %s", repo_id)
    if not repo or not repo["webhook_secret"]:
        raise NotFound("Репозиторий не найден")
    if not verify_signature(repo["webhook_secret"], body, headers):
        raise Forbidden("Неверная подпись веб-хука")
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        raise BadRequest("Тело веб-хука должно быть JSON") from None
    event, branch, sha, delivery = _parse(headers, payload)
    if "ping" in event:
        return {"status": "pong"}
    if not ctx.db.scalar("""INSERT INTO webhook_events(repository_id, delivery_id, event_type, branch, commit_sha)
                            VALUES (%s,%s,%s,%s,%s) ON CONFLICT (repository_id, delivery_id) DO NOTHING RETURNING id""",
                         repo_id, delivery[:100], event[:50], branch, sha):
        return {"status": "duplicate"}
    if "push" not in event:
        return {"status": "ignored", "reason": f"событие {event} не требует анализа"}
    if repo["default_branch"] and branch and branch != repo["default_branch"]:
        return {"status": "ignored", "reason": f"ветка {branch} не основная"}
    try:
        run = pipeline.enqueue(repo["project_id"], "WEBHOOK")
    except Conflict:
        return {"status": "queued_later", "reason": "анализ уже выполняется – изменения попадут в следующий запуск"}
    ctx.db.run("UPDATE webhook_events SET processed = true, run_id = %s WHERE repository_id = %s AND delivery_id = %s",
               run["id"], repo_id, delivery[:100])
    return {"status": "accepted", "run_id": run["id"]}


def sync(ctx: Context, pipeline, project_id: int, user_id: int) -> dict:
    access.require(ctx, project_id, user_id, "analyze")
    return pipeline.enqueue(project_id, "SYNC")


def webhook_info(ctx: Context, project_id: int, user_id: int, repo_id: int) -> dict:
    access.require(ctx, project_id, user_id, "manage_repos")
    repo = ctx.db.one("SELECT id, name, webhook_secret FROM repositories WHERE id = %s AND project_id = %s", repo_id, project_id)
    if not repo:
        raise NotFound("Репозиторий не найден")
    if not repo["webhook_secret"]:
        repo["webhook_secret"] = uuid.uuid4().hex + uuid.uuid4().hex[:16]
        ctx.db.run("UPDATE repositories SET webhook_secret = %s WHERE id = %s", repo["webhook_secret"], repo_id)
    repo["url"] = f"{ctx.settings.public_url.rstrip('/')}/hooks/repositories/{repo_id}"
    repo["events"] = ctx.db.all("SELECT delivery_id, event_type, branch, commit_sha, received_at, processed, run_id "
                                "FROM webhook_events WHERE repository_id = %s ORDER BY received_at DESC LIMIT 10", repo_id)
    return repo
