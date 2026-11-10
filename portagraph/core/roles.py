"""Определение роли репозитория и его технологического стека по файлам.

Пользователь не назначает роли вручную: эвристика выдаёт роль, уверенность и
причины, по которым она так решила (их видно в интерфейсе).
"""
from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass, field

ROLES = ("SERVICE", "FRONTEND", "LIBRARY", "INFRASTRUCTURE", "DOCUMENTATION", "UNKNOWN")


@dataclass
class Classification:
    role: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    stack: list[str] = field(default_factory=list)


_ENTRY = re.compile(r"(application|main|app|server|program|manage|wsgi|asgi)\.(java|kt|py|go|cs|ts|js)$", re.I)


def detect_stack(files: dict[str, str]) -> list[str]:
    """Технологии по сборочным файлам и коду: {путь: содержимое}."""
    stack: list[str] = []

    def add(x):
        if x not in stack:
            stack.append(x)

    for path, text in files.items():
        name = posixpath.basename(path).lower()
        low = text.lower() if text else ""
        if name == "pom.xml" or name.startswith("build.gradle"):
            add("Java" if "kotlin" not in low else "Kotlin")
            if "spring-boot" in low:
                add("Spring Boot")
            if "kafka" in low:
                add("Kafka")
            if "postgresql" in low:
                add("PostgreSQL")
        elif name == "package.json":
            try:
                pj = json.loads(text)
            except ValueError:
                pj = {}
            deps = {**pj.get("dependencies", {}), **pj.get("devDependencies", {})}
            add("TypeScript" if "typescript" in deps else "JavaScript")
            for key, label in (("next", "Next.js"), ("react", "React"), ("vue", "Vue"), ("@angular/core", "Angular"),
                               ("express", "Express"), ("@nestjs/core", "NestJS"), ("kafkajs", "Kafka")):
                if key in deps:
                    add(label)
        elif name in ("requirements.txt", "pyproject.toml", "setup.py", "pipfile"):
            add("Python")
            for key, label in (("fastapi", "FastAPI"), ("flask", "Flask"), ("django", "Django"),
                               ("kafka", "Kafka"), ("sqlalchemy", "SQLAlchemy"), ("celery", "Celery")):
                if key in low:
                    add(label)
        elif name == "go.mod":
            add("Go")
        elif name.endswith(".tf"):
            add("Terraform")
        elif "chart.yaml" == name or "/helm/" in path.lower():
            add("Helm")
        elif name == "dockerfile":
            add("Docker")
        elif name.startswith("docker-compose") or name.startswith("compose."):
            add("Docker Compose")
    return stack


def classify(paths: list[str], files: dict[str, str] | None = None) -> Classification:
    files = files or {}
    if not paths:
        return Classification("UNKNOWN", 0.0, ["репозиторий пуст"])
    lower = [p.lower() for p in paths]
    names = [posixpath.basename(p) for p in lower]
    total = len(paths)
    docs = sum(1 for p in lower if p.endswith((".md", ".adoc", ".rst")))
    infra = sum(1 for p in lower if p.endswith((".tf", ".tfvars", ".hcl")) or "/helm/" in p or p.startswith(("helm/", "k8s/", "ansible/", "terraform/"))
                or "/k8s/" in p or "/terraform/" in p or "chart.yaml" in p)
    code = [p for p in lower if re.search(r"\.(java|kt|py|go|cs|ts|tsx|js|jsx|rb|php|rs|scala)$", p)]
    entry = [paths[i] for i, n in enumerate(names) if _ENTRY.search(n)]
    controllers = [p for p in lower if re.search(r"(controller|/routes?/|/handlers?/|/api/|router)", p)]
    dockerfile = any(n == "dockerfile" for n in names)
    openapi = any(n.startswith(("openapi", "swagger")) for n in names)
    frontend = [p for p in lower if re.search(r"(next\.config|vite\.config|angular\.json|nuxt\.config|svelte\.config)", p)
                or re.search(r"(^|/)(src/)?(app|pages)/.*\.(tsx|jsx|vue)$", p)]
    pkg = files.get("package.json", "")
    publishes = any(n in ("setup.py", "pyproject.toml") for n in names) or '"main"' in pkg or "<packaging>jar</packaging>" in files.get("pom.xml", "")
    stack = detect_stack(files)
    reasons: list[str] = []

    if total and docs / total > 0.7 and not code:
        return Classification("DOCUMENTATION", 0.85, [f"{docs} из {total} файлов — документация"], stack)
    if infra and (infra / total > 0.3 or not code):
        return Classification("INFRASTRUCTURE", 0.85, [f"{infra} файлов Terraform/Helm/Kubernetes"], stack)
    if frontend:
        reasons.append("конфигурация фронтенд-фреймворка или страницы приложения")
        if "Next.js" in stack or "React" in stack or "Vue" in stack or "Angular" in stack:
            reasons.append("зависимости: " + ", ".join(s for s in stack if s in ("Next.js", "React", "Vue", "Angular")))
            return Classification("FRONTEND", 0.92, reasons, stack)
        return Classification("FRONTEND", 0.8, reasons, stack)
    score = 0.0
    if entry:
        score += 0.45
        reasons.append(f"точка входа: {posixpath.basename(entry[0])}")
    if controllers or openapi:
        score += 0.3
        reasons.append("HTTP-контроллеры или API-спецификация" if controllers else "OpenAPI-спецификация")
    if dockerfile:
        score += 0.2
        reasons.append("Dockerfile")
    if score >= 0.45:
        return Classification("SERVICE", round(min(0.95, 0.35 + score), 2), reasons, stack)
    if code and (publishes or not dockerfile):
        reasons.append("код без точки входа и Dockerfile")
        if publishes:
            reasons.append("собирается как библиотека")
        return Classification("LIBRARY", 0.75 if publishes else 0.55, reasons, stack)
    return Classification("UNKNOWN", 0.2, ["недостаточно признаков"], stack)
