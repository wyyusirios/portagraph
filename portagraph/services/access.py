"""Роли в проекте и проверка прав (изоляция данных по проектам).

* VIEWER – только просмотр карты, графа и документов;
* DEVELOPER – плюс AI-ассистент, impact analysis, формирование документов;
* ARCHITECT – плюс запуск анализа, подтверждение выводов, утверждение документов;
* OWNER – плюс репозитории, участники, удаление проекта.
"""
from __future__ import annotations

from .context import Context
from .errors import Forbidden, NotFound

ROLES = ("VIEWER", "DEVELOPER", "ARCHITECT", "OWNER")
RANK = {r: i for i, r in enumerate(ROLES)}
ROLE_RU = {"VIEWER": "Наблюдатель", "DEVELOPER": "Разработчик", "ARCHITECT": "Архитектор", "OWNER": "Владелец"}

ACTION_ROLE = {
    "view": "VIEWER",
    "ask": "DEVELOPER",
    "impact": "DEVELOPER",
    "generate_docs": "DEVELOPER",
    "analyze": "ARCHITECT",
    "verify": "ARCHITECT",
    "approve_docs": "ARCHITECT",
    "manage_repos": "OWNER",
    "manage_members": "OWNER",
    "delete_project": "OWNER",
}
ACTION_RU = {
    "ask": "задавать вопросы ассистенту", "impact": "запускать impact analysis", "generate_docs": "формировать документы",
    "analyze": "запускать анализ", "verify": "подтверждать выводы", "approve_docs": "утверждать документы",
    "manage_repos": "управлять репозиториями", "manage_members": "управлять участниками",
    "delete_project": "архивировать проект",
}


def role_in(ctx: Context, project_id: int, user_id: int) -> str | None:
    return ctx.db.scalar(
        "SELECT m.role FROM project_members m JOIN projects p ON p.id = m.project_id "
        "WHERE m.project_id = %s AND m.user_id = %s AND p.status = 'ACTIVE'", project_id, user_id)


def require(ctx: Context, project_id: int, user_id: int, action: str = "view") -> str:
    role = role_in(ctx, project_id, user_id)
    if role is None:
        raise NotFound("Проект не найден или у вас нет к нему доступа")
    if RANK[role] < RANK[ACTION_ROLE[action]]:
        raise Forbidden(f"Роль «{ROLE_RU[role]}» не позволяет {ACTION_RU.get(action, action)}. "
                        f"Нужна роль «{ROLE_RU[ACTION_ROLE[action]]}» или выше.")
    return role


def can(role: str | None, action: str) -> bool:
    return role is not None and RANK[role] >= RANK[ACTION_ROLE[action]]


def permissions(role: str | None) -> dict[str, bool]:
    return {a: can(role, a) for a in ACTION_ROLE}
