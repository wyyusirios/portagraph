"""Запуск PortaGraph: python run.py  →  http://localhost:8000"""
from __future__ import annotations

import logging
import os
import sys


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from portagraph import create_app
    from portagraph.db import DatabaseError, InterfaceError

    for attempt in range(4):
        try:
            app = create_app()
            break
        except DatabaseError as e:
            if e.sqlstate in ("28P01", "28000") and attempt < 3 and sys.stdin and sys.stdin.isatty():
                if not ask_password():
                    sys.exit(1)
                continue
            fail(e)
        except (InterfaceError, OSError) as e:
            fail(e)
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"\n  PortaGraph запущен: http://localhost:{port}\n  Демо-вход: anastasia@portagraph.local / portagraph\n")
    try:
        from waitress import serve  # необязательный production-сервер
        serve(app, host=host, port=port, threads=8)
    except ImportError:
        app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)


def fail(e) -> None:
    print("\nНе удалось подключиться к PostgreSQL:", e)
    if isinstance(e, OSError) or "refused" in str(e).lower() or "10061" in str(e):
        print("Похоже, PostgreSQL не запущен. Откройте «Службы» (Win+R → services.msc),")
        print("найдите postgresql-x64-… и нажмите «Запустить».")
    else:
        print("Проверьте DATABASE_URL в файле .env рядом с run.py.")
    print("(по умолчанию postgresql://postgres:postgres@127.0.0.1:5432/portagraph)\n")
    sys.exit(1)


def ask_password() -> bool:
    """Неверный пароль: спрашиваем пароль пользователя postgres и сохраняем его в .env."""
    import getpass
    import pathlib
    import re
    from urllib.parse import quote, urlsplit, urlunsplit

    from portagraph.config import ROOT
    print("\nPostgreSQL не принял пароль пользователя postgres.")
    pwd = getpass.getpass("Введите пароль, который вы задавали при установке PostgreSQL (ввод не отображается): ")
    if not pwd:
        return False
    current = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/portagraph")
    parts = urlsplit(current)
    user = parts.username or "postgres"
    host = f"{parts.hostname or '127.0.0.1'}:{parts.port or 5432}"
    dsn = urlunsplit(parts._replace(netloc=f"{quote(user, safe='')}:{quote(pwd, safe='')}@{host}"))
    os.environ["DATABASE_URL"] = dsn
    env = pathlib.Path(ROOT) / ".env"
    text = env.read_text(encoding="utf-8") if env.exists() else ""
    line = f"DATABASE_URL={dsn}"
    text = re.sub(r"(?m)^DATABASE_URL=.*$", line, text) if re.search(r"(?m)^DATABASE_URL=", text) else (text + ("\n" if text and not text.endswith("\n") else "") + line + "\n")
    env.write_text(text, encoding="utf-8")
    print("Пароль сохранён в файл .env — в следующий раз вводить не нужно.\n")
    return True


if __name__ == "__main__":
    main()
