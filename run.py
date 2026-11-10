"""Запуск PortaGraph: python run.py  →  http://localhost:8000"""
from __future__ import annotations

import logging
import os
import sys


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from portagraph import create_app
    from portagraph.db import DatabaseError, InterfaceError

    try:
        app = create_app()
    except (InterfaceError, DatabaseError, OSError) as e:
        print("\nНе удалось подключиться к PostgreSQL:", e)
        print("Проверьте, что PostgreSQL запущен и в .env указан верный DATABASE_URL")
        print("(по умолчанию postgresql://postgres:postgres@127.0.0.1:5432/portagraph).\n")
        sys.exit(1)
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"\n  PortaGraph запущен: http://localhost:{port}\n  Демо-вход: anastasia@portagraph.local / portagraph\n")
    try:
        from waitress import serve  # необязательный production-сервер
        serve(app, host=host, port=port, threads=8)
    except ImportError:
        app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
