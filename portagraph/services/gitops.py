"""Получение исходников: git clone/pull, распаковка ZIP, копия демо, локальная папка.

Токен доступа подставляется в адрес только на время команды git и никогда не
попадает в логи и сообщения об ошибках.
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from urllib.parse import quote, urlparse

from .errors import BadRequest

DEMO_ROOT = pathlib.Path(__file__).resolve().parent.parent / "demo" / "shopflow"
GIT_TIMEOUT = 600


@dataclass
class GitUrl:
    provider: str     # GITHUB | BITBUCKET | GITLAB | GITVERSE | OTHER
    url: str          # нормализованный https-адрес
    name: str         # имя репозитория


_SSH = re.compile(r"^git@([\w.\-]+):([\w.\-/]+?)(?:\.git)?/?$")


def parse_url(raw: str) -> GitUrl:
    s = (raw or "").strip()
    m = _SSH.match(s)
    if m:
        s = f"https://{m.group(1)}/{m.group(2)}"
    if not re.match(r"^https?://", s):
        if re.match(r"^[\w.\-]+\.[a-z]{2,}/", s):
            s = "https://" + s
        else:
            raise BadRequest(f"Не похоже на адрес Git-репозитория: {raw}")
    u = urlparse(s)
    path = u.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2 or not u.hostname:
        raise BadRequest(f"В адресе не хватает владельца и имени репозитория: {raw}")
    host = u.hostname.lower()
    provider = ("GITHUB" if "github" in host else "BITBUCKET" if "bitbucket" in host else
                "GITLAB" if "gitlab" in host else "GITVERSE" if "gitverse" in host else "OTHER")
    if provider in ("GITHUB", "BITBUCKET"):
        parts = parts[:2]
    return GitUrl(provider, f"https://{host}/{'/'.join(parts)}", parts[-1])


def _auth_url(git: GitUrl, token: str | None) -> str:
    if not token:
        return git.url
    user = {"GITHUB": "x-access-token", "BITBUCKET": "x-token-auth", "GITLAB": "oauth2"}.get(git.provider, "oauth2")
    u = urlparse(git.url)
    return f"{u.scheme}://{user}:{quote(token, safe='')}@{u.netloc}{u.path}"


def _redact(text: str, token: str | None) -> str:
    if token:
        text = text.replace(token, "***").replace(quote(token, safe=""), "***")
    return re.sub(r"://[^/@\s]+@", "://***@", text)


def _git(args: list[str], cwd: str | None = None, token: str | None = None, timeout: int = GIT_TIMEOUT) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo", "LC_ALL": "C"}
    try:
        p = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise BadRequest("Git не установлен на сервере PortaGraph") from None
    except subprocess.TimeoutExpired:
        raise BadRequest("Git не ответил вовремя: проверьте адрес и сеть") from None
    if p.returncode != 0:
        err = _redact((p.stderr or p.stdout).strip(), token)
        if re.search(r"Authentication failed|could not read Username|403|401|Repository not found|not found", err, re.I):
            raise BadRequest("Нет доступа к репозиторию: проверьте адрес и токен (нужны права на чтение)")
        if re.search(r"Could not resolve host|unable to access|Failed to connect", err, re.I):
            raise BadRequest("Хостинг недоступен: проверьте подключение к интернету")
        raise BadRequest("Ошибка git: " + err.splitlines()[-1][:300] if err else "Ошибка git")
    return p.stdout


def check_access(git: GitUrl, token: str | None) -> str | None:
    """Проверяет доступ без скачивания. Возвращает основную ветку."""
    out = _git(["ls-remote", "--symref", _auth_url(git, token), "HEAD"], token=token, timeout=90)
    m = re.search(r"ref: refs/heads/(\S+)\s+HEAD", out)
    return m.group(1) if m else None


def clone_or_pull(git: GitUrl, dest: pathlib.Path, token: str | None, branch: str | None) -> str:
    """Клонирует (или обновляет) основную ветку и возвращает SHA коммита."""
    url = _auth_url(git, token)
    if (dest / ".git").exists():
        _git(["remote", "set-url", "origin", url], cwd=str(dest), token=token)
        ref = branch or "HEAD"
        _git(["fetch", "--depth", "1", "origin", ref], cwd=str(dest), token=token)
        _git(["reset", "--hard", "FETCH_HEAD"], cwd=str(dest), token=token)
        _git(["remote", "set-url", "origin", git.url], cwd=str(dest))
    else:
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        args = ["clone", "--depth", "1", "--single-branch"]
        if branch:
            args += ["--branch", branch]
        _git([*args, url, str(dest)], token=token)
        _git(["remote", "set-url", "origin", git.url], cwd=str(dest))   # токен не остаётся в .git/config
    return _git(["rev-parse", "HEAD"], cwd=str(dest)).strip()


def extract_zip(zip_path: pathlib.Path, dest: pathlib.Path, max_bytes: int) -> None:
    """Безопасная распаковка: защита от выхода за пределы каталога и «zip-бомб»."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise BadRequest("Файл не является ZIP-архивом") from None
    with zf:
        total = sum(i.file_size for i in zf.infolist())
        if total > max_bytes:
            raise BadRequest(f"Архив слишком большой после распаковки (лимит {max_bytes // (1024 * 1024)} МБ)")
        names = [i.filename for i in zf.infolist() if not i.is_dir()]
        tops = {n.split("/", 1)[0] for n in names}
        strip = len(tops) == 1 and all("/" in n for n in names)
        root = dest.resolve()
        for info in zf.infolist():
            if info.is_dir() or info.filename.startswith("__MACOSX/"):
                continue
            name = info.filename.split("/", 1)[1] if strip else info.filename
            target = (dest / name).resolve()
            if not str(target).startswith(str(root) + os.sep):
                raise BadRequest("Архив содержит недопустимые пути")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def demo_repositories() -> list[str]:
    return sorted(p.name for p in DEMO_ROOT.iterdir() if p.is_dir())


def copy_demo(name: str, dest: pathlib.Path) -> None:
    src = DEMO_ROOT / name
    if not src.is_dir():
        raise BadRequest(f"Нет демо-репозитория {name}")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
