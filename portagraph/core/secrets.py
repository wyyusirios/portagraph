"""Поиск и маскирование секретов перед индексацией.

Секреты не должны попадать в индекс, в поиск и тем более в запросы к языковой
модели. Найденное значение заменяется маркером ``[REDACTED:тип]``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    type: str
    line: int


@dataclass(frozen=True)
class ScanResult:
    sanitized: str
    findings: tuple[Finding, ...]

    @property
    def has_secrets(self) -> bool:
        return bool(self.findings)


_RULES = [
    ("PRIVATE_KEY", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("AWS_ACCESS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("BITBUCKET_APP_PASSWORD", re.compile(r"\bATBB[A-Za-z0-9_\-]{24,}\b")),
    ("SLACK_TOKEN", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("CONNECTION_STRING_PASSWORD", re.compile(r"(?<=://)([^\s:/@]{1,64}):([^\s@/]{3,})(?=@)")),
    ("GENERIC_SECRET", re.compile(
        r"(?i)((?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)"
        r"[\"']?\s{0,3}[:=]\s{0,3}[\"']?)(?!\[REDACTED|\$\{|<|%\(|[\w.]*\(|(?:os|process|System|env|settings|config)\.)([^\s\"'#,;()]{6,})")),
]

_SECRET_FILE = re.compile(r"(^|/)(\.env(\..+)?|id_rsa|id_ed25519|.+\.(pem|p12|pfx|jks|keystore|key))$", re.I)
_ALLOWED_ENV_TEMPLATES = re.compile(r"(^|/)\.env\.(example|sample|template)$", re.I)


def is_secret_file(path: str) -> bool:
    """Файлы, которые никогда не индексируются (ключи, .env)."""
    return bool(_SECRET_FILE.search(path)) and not _ALLOWED_ENV_TEMPLATES.search(path)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan(text: str) -> ScanResult:
    if not text:
        return ScanResult(text or "", ())
    findings: list[Finding] = []
    result = text
    for kind, rx in _RULES:
        out, last = [], 0
        for m in rx.finditer(result):
            findings.append(Finding(kind, _line_of(result, m.start())))
            if kind == "CONNECTION_STRING_PASSWORD":
                repl = f"{m.group(1)}:[REDACTED:{kind}]"
            elif kind == "GENERIC_SECRET":
                repl = f"{m.group(1)}[REDACTED:{kind}]"
            else:
                repl = f"[REDACTED:{kind}]"
            out.append(result[last:m.start()])
            out.append(repl)
            last = m.end()
        if out:
            out.append(result[last:])
            result = "".join(out)
    findings.sort(key=lambda f: f.line)
    return ScanResult(result, tuple(findings))
