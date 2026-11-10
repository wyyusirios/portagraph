"""Проекты и участники (UC-02, UC-15)."""
from __future__ import annotations

from ..db import UniqueViolation
from . import access
from .context import Context
from .errors import BadRequest, Conflict, NotFound


def create(ctx: Context, user_id: int, name: str, description: str | None) -> dict:
    name = (name or "").strip()
    if not name:
        raise BadRequest("Название проекта обязательно")
    if len(name) > 120:
        raise BadRequest("Название проекта — не длиннее 120 символов")
    with ctx.db.transaction() as c:
        p = c.execute("INSERT INTO projects(name, description, owner_id) VALUES (%s, %s, %s) RETURNING *",
                      (name, (description or "").strip()[:2000] or None, user_id)).one()
        c.execute("INSERT INTO project_members(project_id, user_id, role) VALUES (%s, %s, 'OWNER')", (p["id"], user_id))
    return p


def list_for_user(ctx: Context, user_id: int) -> list[dict]:
    return ctx.db.all("""
        SELECT p.id, p.name, p.description, p.created_at, m.role,
               (SELECT count(*) FROM repositories r WHERE r.project_id = p.id) AS repo_count,
               (SELECT count(*) FROM source_files f JOIN repositories r ON r.id = f.repository_id WHERE r.project_id = p.id) AS file_count,
               (SELECT count(*) FROM project_members x WHERE x.project_id = p.id) AS member_count,
               lr.status AS run_status, lr.progress AS run_progress, lr.finished_at AS run_finished, lr.error_message AS run_error,
               (SELECT count(*) FROM repositories r WHERE r.project_id = p.id AND r.status = 'ERROR') AS repo_errors,
               (SELECT coalesce(json_agg(DISTINCT r.detected_role), '[]'::json) FROM repositories r WHERE r.project_id = p.id) AS roles
          FROM projects p
          JOIN project_members m ON m.project_id = p.id AND m.user_id = %s
          LEFT JOIN LATERAL (SELECT * FROM analysis_runs a WHERE a.project_id = p.id ORDER BY a.id DESC LIMIT 1) lr ON true
         WHERE p.status = 'ACTIVE'
         ORDER BY p.created_at DESC""", user_id)


def get(ctx: Context, project_id: int, user_id: int) -> dict:
    role = access.require(ctx, project_id, user_id)
    p = ctx.db.one("SELECT * FROM projects WHERE id = %s", project_id)
    p["role"] = role
    p["permissions"] = access.permissions(role)
    return p


def update(ctx: Context, project_id: int, user_id: int, name: str, description: str | None) -> dict:
    access.require(ctx, project_id, user_id, "manage_members")
    name = (name or "").strip()
    if not name:
        raise BadRequest("Название проекта обязательно")
    return ctx.db.one("UPDATE projects SET name = %s, description = %s WHERE id = %s RETURNING *",
                      name[:120], (description or "").strip()[:2000] or None, project_id)


def archive(ctx: Context, project_id: int, user_id: int) -> None:
    access.require(ctx, project_id, user_id, "delete_project")
    ctx.db.run("UPDATE projects SET status = 'ARCHIVED' WHERE id = %s", project_id)


def members(ctx: Context, project_id: int, user_id: int) -> list[dict]:
    access.require(ctx, project_id, user_id)
    return ctx.db.all("""SELECT m.id, m.role, m.joined_at, u.id AS user_id, u.email, u.full_name
                           FROM project_members m JOIN users u ON u.id = m.user_id
                          WHERE m.project_id = %s ORDER BY array_position(ARRAY['OWNER','ARCHITECT','DEVELOPER','VIEWER'], m.role::text), u.full_name""",
                      project_id)


def add_member(ctx: Context, project_id: int, actor_id: int, email: str, role: str) -> dict:
    access.require(ctx, project_id, actor_id, "manage_members")
    if role not in ("ARCHITECT", "DEVELOPER", "VIEWER"):
        raise BadRequest("Можно назначить роль архитектора, разработчика или наблюдателя: владелец у проекта один")
    user = ctx.db.one("SELECT id FROM users WHERE email = %s", (email or "").strip().lower())
    if not user:
        raise NotFound(f"Пользователь {email} не зарегистрирован в PortaGraph")
    try:
        return ctx.db.one("INSERT INTO project_members(project_id, user_id, role) VALUES (%s, %s, %s) RETURNING *",
                          project_id, user["id"], role)
    except UniqueViolation:
        raise Conflict("Пользователь уже участник проекта") from None


def change_role(ctx: Context, project_id: int, actor_id: int, member_id: int, role: str) -> None:
    access.require(ctx, project_id, actor_id, "manage_members")
    if role not in ("ARCHITECT", "DEVELOPER", "VIEWER"):
        raise BadRequest("Недопустимая роль")
    m = ctx.db.one("SELECT * FROM project_members WHERE id = %s AND project_id = %s", member_id, project_id)
    if not m:
        raise NotFound("Участник не найден")
    if m["role"] == "OWNER":
        raise BadRequest("Роль владельца изменить нельзя")
    ctx.db.run("UPDATE project_members SET role = %s WHERE id = %s", role, member_id)


def remove_member(ctx: Context, project_id: int, actor_id: int, member_id: int) -> None:
    access.require(ctx, project_id, actor_id, "manage_members")
    m = ctx.db.one("SELECT * FROM project_members WHERE id = %s AND project_id = %s", member_id, project_id)
    if not m:
        raise NotFound("Участник не найден")
    if m["role"] == "OWNER":
        raise BadRequest("Владельца нельзя удалить из проекта")
    ctx.db.run("DELETE FROM project_members WHERE id = %s", member_id)
