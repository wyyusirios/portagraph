"""Работа с текстом для поиска: разбиение идентификаторов и выделение слов запроса."""
from __future__ import annotations

import re

_IDENT = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[._\-][A-Za-z0-9]+)*")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
_WORD = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_.\-]*")

STOP = set("""
а и в во на по с со к ко о об от до из у за для при как что это где кто какой какие каком какая ли же
бы не нет да или но то так там тут все всё его её их мне меня мы вы он она они оно есть быть был была
можно нужно надо ли через про над под между чем чтобы если когда тот эта этот эти который которая которые
the a an of to in on for and or is are be by with from at as it this that which what where who how does do
""".split())


def split_identifier(token: str) -> list[str]:
    """OrderEventPublisher → order event publisher; auth-service → auth service."""
    out = []
    for part in re.split(r"[._\-/]", token):
        out += [w.lower() for w in _CAMEL.findall(part)]
    return [w for w in out if len(w) > 1]


def expand_for_index(text: str, limit: int = 4000) -> str:
    """Добавляет к тексту части составных идентификаторов, чтобы «order service» находило OrderService."""
    seen, extra = set(), []
    for m in _IDENT.finditer(text[:200_000]):
        tok = m.group(0)
        if len(tok) < 4:
            continue
        parts = split_identifier(tok)
        if len(parts) > 1:
            key = " ".join(parts)
            if key not in seen:
                seen.add(key)
                extra.append(key)
                if len(extra) >= limit:
                    break
    return " ".join(extra)


def query_terms(question: str) -> list[str]:
    """Значимые слова вопроса + части составных идентификаторов, без стоп-слов."""
    terms: list[str] = []
    for m in _WORD.finditer(question):
        w = m.group(0).strip("._-")
        low = w.lower()
        if len(low) < 2 or low in STOP:
            continue
        terms.append(low)
        if re.search(r"[A-Z]|[._\-]", w) and re.match(r"[A-Za-z]", w):
            terms += [p for p in split_identifier(w) if p not in STOP]
    return list(dict.fromkeys(terms))


def russian_stem(word: str) -> str:
    """Очень простой стеммер для префиксного поиска: «сервисы» → «сервис», «оплаты» → «оплат»."""
    w = word.lower()
    if not re.match(r"[а-яё]", w) or len(w) <= 4:
        return w
    for suf in ("ями", "ами", "ого", "его", "ому", "ему", "ых", "их", "ой", "ей", "ий", "ый", "ая", "яя", "ое", "ее",
                "ов", "ев", "ам", "ям", "ах", "ях", "ом", "ем", "ы", "и", "а", "я", "у", "ю", "е", "о"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w
