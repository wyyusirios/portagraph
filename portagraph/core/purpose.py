"""Краткое назначение репозитория без языковой модели.

Порядок источников: первый содержательный абзац README → описание в
package.json / pom.xml / pyproject.toml → сводка по роли, стеку и API.
"""
from __future__ import annotations

import json
import re

MAX_LEN = 320


def _clean_md(line: str) -> str:
    line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)          # картинки и бейджи
    line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)        # ссылки → текст
    line = re.sub(r"[*_`]{1,3}([^*_`]+)[*_`]{1,3}", r"\1", line)
    line = re.sub(r"<[^>]+>", "", line)
    return line.strip()


def from_readme(text: str) -> str | None:
    if not text:
        return None
    paragraph: list[str] = []
    in_code = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            if paragraph:
                break
            continue
        if in_code:
            continue
        if not line:
            if paragraph:
                break
            continue
        if line.startswith(("#", "|", ">", "---", "===", "-", "*", "+")) or re.match(r"^\d+\.", line):
            if paragraph:
                break
            continue
        cleaned = _clean_md(line)
        if cleaned and len(cleaned) > 3:
            paragraph.append(cleaned)
    text = " ".join(paragraph).strip()
    if len(text) < 12:
        return None
    if len(text) > MAX_LEN:
        cut = text[:MAX_LEN]
        text = cut[: cut.rfind(" ")].rstrip(",;:") + "…"
    return text


def from_manifests(files: dict[str, str]) -> str | None:
    pj = files.get("package.json")
    if pj:
        try:
            d = json.loads(pj).get("description")
            if d:
                return str(d)[:MAX_LEN]
        except ValueError:
            pass
    pom = files.get("pom.xml")
    if pom:
        m = re.search(r"<description>([^<]{8,})</description>", pom)
        if m:
            return m.group(1).strip()[:MAX_LEN]
    pp = files.get("pyproject.toml")
    if pp:
        m = re.search(r'^description\s*=\s*"([^"]{8,})"', pp, re.M)
        if m:
            return m.group(1)[:MAX_LEN]
    return None


ROLE_RU = {"SERVICE": "Сервис", "FRONTEND": "Фронтенд-приложение", "LIBRARY": "Библиотека",
           "INFRASTRUCTURE": "Инфраструктурный репозиторий", "DOCUMENTATION": "Документация", "UNKNOWN": "Репозиторий"}


def summarize(role: str, stack: list[str], endpoints: int, readme: str | None, files: dict[str, str]) -> tuple[str, str]:
    """Возвращает (назначение, источник)."""
    r = from_readme(readme or "")
    if r:
        return r, "README"
    m = from_manifests(files)
    if m:
        return m, "манифест"
    parts = [ROLE_RU.get(role, "Репозиторий")]
    if stack:
        parts.append("на " + ", ".join(stack[:3]))
    text = " ".join(parts)
    if endpoints:
        text += f"; {endpoints} HTTP-эндпоинт" + ("ов" if endpoints % 10 in (0, 5, 6, 7, 8, 9) or 11 <= endpoints % 100 <= 14 else "а" if endpoints % 10 in (2, 3, 4) else "")
    return text + ". Описание сформировано автоматически: README не найден.", "структура"
