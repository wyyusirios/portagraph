"""Демонстрационные данные: пользователи команды и проанализированный проект ShopFlow.

Создаются один раз при первом запуске (PORTAGRAPH_DEMO_SEED=1, по умолчанию включено).
"""
from __future__ import annotations

import logging

from . import assistant, auth, docs_service, impact_service, projects, repos
from .context import Context

log = logging.getLogger(__name__)

DEMO_PASSWORD = "portagraph"
OWNER_EMAIL = "anastasia@portagraph.local"
USERS = [
    (OWNER_EMAIL, "Анастасия Казанкова", "OWNER"),
    ("maxim@portagraph.local", "Максим Чиженко", "DEVELOPER"),
    ("guest@portagraph.local", "Гость PortaGraph", "VIEWER"),
]
PROJECT = ("ShopFlow", "Учебный интернет-магазин из 9 репозиториев: шлюз, авторизация, каталог, заказы, биллинг, "
                       "уведомления, общая библиотека DTO, веб-фронтенд и инфраструктура.")


def run(ctx: Context, pipeline) -> bool:
    if ctx.db.scalar("SELECT 1 FROM users WHERE email = %s", OWNER_EMAIL):
        return False
    log.info("Создаю демонстрационные данные ShopFlow")
    ids = {}
    for email, name, _ in USERS:
        ids[email] = auth.register(ctx, email, DEMO_PASSWORD, name)["id"]
    owner = ids[OWNER_EMAIL]
    p = projects.create(ctx, owner, *PROJECT)
    for email, _, role in USERS[1:]:
        projects.add_member(ctx, p["id"], owner, email, role)
    repos.connect_demo(ctx, p["id"], owner)
    pipeline.enqueue(p["id"], "MANUAL", owner, wait=True)
    try:
        docs_service.generate(ctx, p["id"], owner, "ARCHITECTURE_OVERVIEW")
        auth_node = ctx.db.one("SELECT id FROM graph_nodes WHERE project_id = %s AND qualified_name = 'service:auth-service'", p["id"])
        if auth_node:
            impact_service.run(ctx, p["id"], owner, [auth_node["id"]], 3,
                               "Меняем формат ответа /api/auth/validate: роли передаются списком")
        assistant.ask(ctx, p["id"], ids["maxim@portagraph.local"], None, "Кто использует auth-service?")
    except Exception:  # noqa: BLE001 – демо-данные не должны мешать запуску
        log.exception("Не удалось подготовить часть демонстрационных данных")
    return True
