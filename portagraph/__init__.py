"""PortaGraph — карта архитектуры распределённых систем по исходному коду."""
from __future__ import annotations

import logging
import threading

from flask import Flask

__version__ = "1.0.0"
log = logging.getLogger("portagraph")


def create_app(settings=None, *, start_seed: bool = True) -> Flask:
    from .config import ROOT, Settings
    from .db import Database
    from .services import seed
    from .services.analysis import AnalysisPipeline
    from .services.context import Context
    from .web import register

    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(SECRET_KEY=settings.secret_key, MAX_CONTENT_LENGTH=(settings.max_upload_mb + 5) * 1024 * 1024,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 14,
                      TESTING=settings.testing, JSON_AS_ASCII=False, TEMPLATES_AUTO_RELOAD=True)
    app.json.ensure_ascii = False

    db = Database(settings.database_url)
    db.migrate()
    ctx = Context(db, settings)
    pipeline = AnalysisPipeline(ctx)
    interrupted = pipeline.recover_interrupted()
    if interrupted:
        log.warning("Помечено прерванных анализов: %s", interrupted)
    app.extensions["portagraph"] = {"ctx": ctx, "pipeline": pipeline, "root": ROOT, "seeding": False}

    if settings.demo_seed and start_seed:
        def _seed():
            app.extensions["portagraph"]["seeding"] = True
            try:
                seed.run(ctx, pipeline)
            except Exception:  # noqa: BLE001
                log.exception("Не удалось создать демонстрационные данные")
            finally:
                app.extensions["portagraph"]["seeding"] = False
        if settings.testing:
            _seed()
        else:
            threading.Thread(target=_seed, name="demo-seed", daemon=True).start()

    register(app)
    return app
