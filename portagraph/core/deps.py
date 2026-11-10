"""Поиск связей между репозиториями по коду и конфигурации.

Каждая найденная связь — кандидат с уверенностью и доказательством (файл, строка,
фрагмент). Несколько независимых доказательств одной связи объединяются:

    уверенность = 1 − Π(1 − cᵢ), но не выше 0,98

Правила и их базовая уверенность:

=============================  =========  ===============================================
Правило                        Уверенность Пример
=============================  =========  ===============================================
URL сервиса в коде             0,90       ``http://auth-service:8080/api/users``
URL сервиса в конфигурации     0,85       ``auth.url: http://auth-service:8080``
Feign/HTTP-клиент по имени     0,90       ``@FeignClient(name = "auth-service")``
Публикация в топик             0,90       ``kafkaTemplate.send("orders.created", …)``
Подписка на топик              0,90       ``@KafkaListener(topics = "orders.created")``
Подключение к БД               0,85       ``jdbc:postgresql://db:5432/orders``
Зависимость на артефакт        0,95       ``<artifactId>common-dto</artifactId>``
depends_on в docker-compose    0,60       ``depends_on: [auth-service]``
Имя переменной окружения       0,50       ``AUTH_SERVICE_URL`` без адреса
Внешний API в коде             0,75       ``https://api.yookassa.ru/v3``
=============================  =========  ===============================================
"""
from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass, field

try:  # PyYAML необязателен: на новых версиях Python у него может не быть готовой сборки
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

C_HTTP_CODE, C_HTTP_CONFIG, C_CLIENT, C_TOPIC, C_DB, C_ARTIFACT, C_COMPOSE, C_ENV, C_EXTERNAL = (
    0.90, 0.85, 0.90, 0.90, 0.85, 0.95, 0.60, 0.50, 0.75)


@dataclass
class Evidence:
    repo: str
    path: str
    line: int
    snippet: str
    rule: str

    def as_dict(self) -> dict:
        return {"repo": self.repo, "path": self.path, "line": self.line, "snippet": self.snippet[:240], "rule": self.rule}


@dataclass
class Link:
    """Кандидат связи: из репозитория `source` к цели."""
    source: str
    target_kind: str          # REPOSITORY | TOPIC | DATABASE | EXTERNAL
    target: str               # имя репозитория, топика, БД или хоста
    edge_type: str            # CALLS_HTTP | PUBLISHES | CONSUMES | READS_WRITES | DEPENDS_ON
    confidence: float
    evidence: Evidence
    meta: dict = field(default_factory=dict)


@dataclass
class RepoInput:
    name: str
    files: list[tuple[str, str, str | None, str]]   # (path, kind, language, content)
    aliases: set[str] = field(default_factory=set)


IGNORED_HOSTS = re.compile(
    r"(^|\.)(localhost|example\.(com|org)|w3\.org|apache\.org|maven\.org|springframework\.org|github\.com|githubusercontent\.com|"
    r"npmjs\.(com|org)|json-schema\.org|schema\.org|python\.org|pypi\.org|mozilla\.org|googleapis\.com|gstatic\.com|"
    r"opensource\.org|creativecommons\.org|reactjs\.org|nextjs\.org|docker\.com|docker\.io|gitlab\.com|bitbucket\.org|"
    r"jetbrains\.com|oracle\.com|java\.com|sun\.com|xmlsoap\.org|openapis\.org|swagger\.io|yaml\.org|ietf\.org|"
    r"microsoft\.com|w3schools\.com|stackoverflow\.com|wikipedia\.org|hashicorp\.com|terraform\.io|kubernetes\.io|"
    r"helm\.sh|k8s\.io|shields\.io|img\.shields\.io|badge\.fury\.io|travis-ci\.(org|com)|codecov\.io)$", re.I)
_URL = re.compile(r"\b(?:https?|grpc|ws|wss)://([A-Za-z0-9][A-Za-z0-9.\-_]*)(?::(\d{2,5}))?(/[\w\-./{}$%?=&]*)?")
_FEIGN = re.compile(r"@FeignClient\s*\([^)]*?(?:name|value)\s*=\s*\"([\w\-]+)\"")
_ENV_SVC = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*)_(?:SERVICE_)?(?:URL|URI|HOST|ADDR|ENDPOINT|BASE_URL)\b")
_JDBC = re.compile(r"jdbc:(postgresql|mysql|mariadb|sqlserver|oracle:thin)://?@?([\w.\-]+)(?::\d+)?[/:;](?:databaseName=)?([\w\-]+)")
_DB_URL = re.compile(r"\b(postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)(?:\+\w+)?://(?:[^@\s/'\"]*@)?([\w.\-]+)(?::\d+)?(?:/([\w\-]+))?")
_KAFKA_SEND = re.compile(r"\b(?:kafkaTemplate|kafka|template|producer|kafkaProducer|publisher)\s*\.\s*(?:send|produce|publish)\s*\(\s*(?:\{\s*topic\s*:\s*)?(?:\"([\w.\-]+)\"|'([\w.\-]+)'|([A-Z][A-Z0-9_]+))")
_KAFKA_LISTEN = re.compile(r"@KafkaListener\s*\([^)]*?topics\s*=\s*[\{\[]?\s*((?:\"[\w.\-]+\"\s*,?\s*)+|[A-Z][A-Z0-9_]+)")
_PY_CONSUMER = re.compile(r"\b(?:KafkaConsumer|AIOKafkaConsumer)\s*\(\s*((?:['\"][\w.\-]+['\"]\s*,?\s*)+)|\.subscribe\s*\(\s*(?:\{\s*topics?\s*:\s*)?\[?\s*((?:['\"][\w.\-]+['\"]\s*,?\s*)+)")
_RABBIT_LISTEN = re.compile(r"@RabbitListener\s*\([^)]*?queues\s*=\s*\{?\s*\"([\w.\-]+)\"")
_RABBIT_SEND = re.compile(r"rabbitTemplate\s*\.\s*convertAndSend\s*\(\s*\"([\w.\-]+)\"")
_CONST = re.compile(r"\b(?:static\s+final\s+String|const(?:\s+val)?|final\s+String|val)\s+([A-Z][A-Z0-9_]+)\s*(?::\s*String)?\s*=\s*\"([\w.\-]+)\"")
_PY_CONST = re.compile(r"^([A-Z][A-Z0-9_]+)\s*=\s*['\"]([\w.\-]+)['\"]", re.M)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _line_snip(text: str, offset: int) -> tuple[int, str]:
    line = text.count("\n", 0, offset) + 1
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    return line, text[start: end if end >= 0 else len(text)].strip()


class LinkExtractor:
    def __init__(self, repos: list[RepoInput]):
        self.repos = repos
        # имя/псевдоним (нормализованный) → репозиторий
        self.alias: dict[str, str] = {}
        for r in repos:
            for a in {r.name, *r.aliases}:
                if a and len(_norm(a)) >= 3:
                    self.alias.setdefault(_norm(a), r.name)

    def repo_for_host(self, host: str) -> str | None:
        h = host.lower()
        first = h.split(".")[0]
        for cand in (h, first, first.replace("-svc", "-service"), first + "service", first.removesuffix("-svc")):
            r = self.alias.get(_norm(cand))
            if r:
                return r
        return None

    # ------------------------------------------------------------------ главное
    def extract(self) -> list[Link]:
        links: list[Link] = []
        for repo in self.repos:
            for path, kind, lang, text in repo.files:
                if not text:
                    continue
                name = posixpath.basename(path).lower()
                if kind == "BUILD_SCRIPT":
                    links += self._artifacts(repo, path, name, text)
                    continue
                if kind == "CONFIG" and (name.startswith("docker-compose") or name.startswith("compose.")):
                    links += self._compose(repo, path, text)
                    continue
                if kind not in ("CODE", "CONFIG", "API_SPEC"):
                    continue
                links += self._http(repo, path, kind, text)
                links += self._databases(repo, path, kind, text)
                if kind == "CODE":
                    links += self._messaging(repo, path, lang, text)
                    links += self._clients(repo, path, text)
        return [lk for lk in links if not (lk.target_kind == "REPOSITORY" and lk.target == lk.source)]

    # ------------------------------------------------------------------ HTTP
    def _http(self, repo: RepoInput, path: str, kind: str, text: str) -> list[Link]:
        out = []
        for m in _URL.finditer(text):
            host = m.group(1).rstrip(".")
            line, snip = _line_snip(text, m.start())
            if re.search(r"xmlns|schemaLocation|@see|license", snip, re.I):
                continue
            target = self.repo_for_host(host)
            if target:
                c = C_HTTP_CODE if kind == "CODE" else C_HTTP_CONFIG
                out.append(Link(repo.name, "REPOSITORY", target, "CALLS_HTTP", c,
                                Evidence(repo.name, path, line, snip, "URL сервиса"), {"path": m.group(3) or "/"}))
            elif "." in host and not re.match(r"^[\d.]+$", host) and not IGNORED_HOSTS.search(host) \
                    and kind in ("CODE", "CONFIG") and not host.endswith((".local", ".internal", ".svc", ".cluster.local")) \
                    and re.search(r"\.[a-z]{2,}$", host):
                out.append(Link(repo.name, "EXTERNAL", host.lower(), "CALLS_HTTP", C_EXTERNAL,
                                Evidence(repo.name, path, line, snip, "внешний API")))
        for m in _ENV_SVC.finditer(text):
            words = m.group(1).lower().replace("_", "-")
            target = self.repo_for_host(words) or self.repo_for_host(words + "-service")
            if target:
                line, snip = _line_snip(text, m.start())
                if _URL.search(snip):   # адрес уже учтён правилом URL
                    continue
                out.append(Link(repo.name, "REPOSITORY", target, "CALLS_HTTP", C_ENV,
                                Evidence(repo.name, path, line, snip, "имя переменной окружения")))
        return out

    def _clients(self, repo: RepoInput, path: str, text: str) -> list[Link]:
        out = []
        for m in _FEIGN.finditer(text):
            target = self.repo_for_host(m.group(1))
            if target:
                line, snip = _line_snip(text, m.start())
                out.append(Link(repo.name, "REPOSITORY", target, "CALLS_HTTP", C_CLIENT,
                                Evidence(repo.name, path, line, snip, "HTTP-клиент")))
        return out

    # ------------------------------------------------------------------ сообщения
    def _messaging(self, repo: RepoInput, path: str, lang: str | None, text: str) -> list[Link]:
        consts = {m.group(1): m.group(2) for m in _CONST.finditer(text)}
        if lang == "python":
            consts.update({m.group(1): m.group(2) for m in _PY_CONST.finditer(text)})
        out = []

        def topic_of(literal: str | None, const: str | None) -> tuple[str | None, float]:
            if literal:
                return literal, C_TOPIC
            if const and const in consts:
                return consts[const], C_TOPIC - 0.05
            return None, 0

        for m in _KAFKA_SEND.finditer(text):
            topic, c = topic_of(m.group(1) or m.group(2), m.group(3))
            if topic:
                line, snip = _line_snip(text, m.start())
                out.append(Link(repo.name, "TOPIC", topic, "PUBLISHES", c, Evidence(repo.name, path, line, snip, "публикация в топик"),
                                {"broker": "Kafka"}))
        for m in _KAFKA_LISTEN.finditer(text):
            raw = m.group(1)
            topics = re.findall(r"\"([\w.\-]+)\"", raw) or ([consts[raw.strip()]] if raw.strip() in consts else [])
            line, snip = _line_snip(text, m.start())
            for t in topics:
                out.append(Link(repo.name, "TOPIC", t, "CONSUMES", C_TOPIC, Evidence(repo.name, path, line, snip, "подписка на топик"),
                                {"broker": "Kafka"}))
        for m in _PY_CONSUMER.finditer(text):
            line, snip = _line_snip(text, m.start())
            for t in re.findall(r"['\"]([\w.\-]+)['\"]", m.group(1) or m.group(2)):
                out.append(Link(repo.name, "TOPIC", t, "CONSUMES", C_TOPIC, Evidence(repo.name, path, line, snip, "подписка на топик"),
                                {"broker": "Kafka"}))
        for rx, et in ((_RABBIT_LISTEN, "CONSUMES"), (_RABBIT_SEND, "PUBLISHES")):
            for m in rx.finditer(text):
                line, snip = _line_snip(text, m.start())
                out.append(Link(repo.name, "TOPIC", m.group(1), et, C_TOPIC,
                                Evidence(repo.name, path, line, snip, "очередь RabbitMQ"), {"broker": "RabbitMQ"}))
        return out

    # ------------------------------------------------------------------ базы данных
    def _databases(self, repo: RepoInput, path: str, kind: str, text: str) -> list[Link]:
        out, seen = [], set()
        for m in _JDBC.finditer(text):
            engine = "PostgreSQL" if m.group(1) == "postgresql" else m.group(1).split(":")[0].capitalize()
            db = m.group(3)
            if (engine, db) in seen:
                continue
            seen.add((engine, db))
            line, snip = _line_snip(text, m.start())
            out.append(Link(repo.name, "DATABASE", db, "READS_WRITES", C_DB, Evidence(repo.name, path, line, snip, "подключение к БД"),
                            {"engine": engine, "host": m.group(2)}))
        for m in _DB_URL.finditer(text):
            scheme, host, db = m.group(1), m.group(2), m.group(3)
            engine = {"postgres": "PostgreSQL", "postgresql": "PostgreSQL", "mysql": "MySQL", "redis": "Redis"}.get(
                scheme, "MongoDB")
            name = db or host
            if engine == "Redis":
                name = host
            if (engine, name) in seen or self.repo_for_host(host):
                continue
            seen.add((engine, name))
            line, snip = _line_snip(text, m.start())
            out.append(Link(repo.name, "DATABASE", name, "READS_WRITES", C_DB, Evidence(repo.name, path, line, snip, "подключение к БД"),
                            {"engine": engine, "host": host}))
        return out

    # ------------------------------------------------------------------ артефакты
    def _artifacts(self, repo: RepoInput, path: str, name: str, text: str) -> list[Link]:
        out = []

        def add(dep: str, offset: int):
            target = self.alias.get(_norm(dep))
            if target and target != repo.name:
                line, snip = _line_snip(text, offset)
                out.append(Link(repo.name, "REPOSITORY", target, "DEPENDS_ON", C_ARTIFACT,
                                Evidence(repo.name, path, line, snip, "зависимость на артефакт")))

        if name == "pom.xml":
            deps_start = text.find("<dependencies>")
            for m in re.finditer(r"<artifactId>([\w.\-]+)</artifactId>", text):
                if deps_start >= 0 and m.start() > deps_start:
                    add(m.group(1), m.start())
        elif name == "package.json":
            try:
                pj = json.loads(text)
            except ValueError:
                return out
            for dep in {**pj.get("dependencies", {}), **pj.get("devDependencies", {})}:
                add(dep.split("/")[-1], max(0, text.find(f'"{dep}"')))
        elif name in ("requirements.txt", "pyproject.toml", "setup.py"):
            for m in re.finditer(r"^\s*['\"]?([A-Za-z][\w.\-]+)", text, re.M):
                add(m.group(1), m.start())
        elif name.startswith("build.gradle"):
            for m in re.finditer(r"project\(['\"]:([\w\-]+)['\"]\)|['\"][\w.\-]+:([\w\-]+):[\w.\-]+['\"]", text):
                add(m.group(1) or m.group(2), m.start())
        elif name == "go.mod":
            for m in re.finditer(r"^\s*(?:require\s+)?([\w.\-/]+)\s+v[\d.]+", text, re.M):
                add(m.group(1).rsplit("/", 1)[-1], m.start())
        return out

    # ------------------------------------------------------------------ docker-compose
    def _compose(self, repo: RepoInput, path: str, text: str) -> list[Link]:
        out = []
        try:
            doc = (yaml.safe_load(text) if yaml else mini_yaml(text)) or {}
        except Exception:  # noqa: BLE001 — битый YAML просто пропускаем
            return out
        if not isinstance(doc, dict):
            return out
        services = doc.get("services") or {}
        if not isinstance(services, dict):
            return out

        def svc_repo(sname: str, spec: dict) -> str | None:
            build = spec.get("build")
            ctx = build.get("context") if isinstance(build, dict) else build if isinstance(build, str) else None
            for cand in (sname, posixpath.basename(str(ctx).rstrip("/")) if ctx else None,
                         str(spec.get("image", "")).split("/")[-1].split(":")[0] or None):
                if cand:
                    r = self.repo_for_host(cand)
                    if r:
                        return r
            return None

        def pos(key: str) -> int:
            i = text.find(key)
            return max(0, i)

        db_by_service: dict[str, tuple[str, str]] = {}
        for sname, spec in services.items():
            if not isinstance(spec, dict):
                continue
            image = str(spec.get("image", "")).lower()
            env = spec.get("environment") or {}
            if isinstance(env, list):
                env = dict(e.split("=", 1) if "=" in e else (e, "") for e in env)
            if "postgres" in image:
                db_by_service[sname] = ("PostgreSQL", str(env.get("POSTGRES_DB") or sname))
            elif "mysql" in image or "mariadb" in image:
                db_by_service[sname] = ("MySQL", str(env.get("MYSQL_DATABASE") or sname))
            elif "mongo" in image:
                db_by_service[sname] = ("MongoDB", sname)

        for sname, spec in services.items():
            if not isinstance(spec, dict):
                continue
            src = svc_repo(sname, spec)
            if not src:
                continue
            deps = spec.get("depends_on") or []
            if isinstance(deps, dict):
                deps = list(deps)
            for d in deps:
                line, snip = _line_snip(text, pos(f"{d}"))
                if d in db_by_service:
                    engine, dbname = db_by_service[d]
                    out.append(Link(src, "DATABASE", dbname, "READS_WRITES", C_COMPOSE,
                                    Evidence(repo.name, path, line, f"{sname} → depends_on: {d}", "depends_on в docker-compose"),
                                    {"engine": engine, "host": d}))
                    continue
                target = self.repo_for_host(d)
                if target:
                    out.append(Link(src, "REPOSITORY", target, "DEPENDS_ON", C_COMPOSE,
                                    Evidence(repo.name, path, line, f"{sname} → depends_on: {d}", "depends_on в docker-compose")))
            env = spec.get("environment") or {}
            values = env.values() if isinstance(env, dict) else [e.split("=", 1)[-1] for e in env]
            for v in values:
                for m in _URL.finditer(str(v)):
                    target = self.repo_for_host(m.group(1))
                    if target and target != src:
                        line, snip = _line_snip(text, pos(str(v)))
                        out.append(Link(src, "REPOSITORY", target, "CALLS_HTTP", C_HTTP_CONFIG,
                                        Evidence(repo.name, path, line, f"{sname}: {snip}", "URL сервиса")))
                    elif m.group(1) in db_by_service:
                        engine, dbname = db_by_service[m.group(1)]
                        line, snip = _line_snip(text, pos(str(v)))
                        out.append(Link(src, "DATABASE", dbname, "READS_WRITES", C_DB,
                                        Evidence(repo.name, path, line, f"{sname}: {snip}", "подключение к БД"), {"engine": engine}))
        return out


def combine(confidences: list[float]) -> float:
    """Независимые доказательства усиливают друг друга: 1 − Π(1 − c)."""
    p = 1.0
    for c in confidences:
        p *= (1 - max(0.0, min(1.0, c)))
    return round(min(0.98, 1 - p), 3)


def repo_aliases(name: str, files: dict[str, str]) -> set[str]:
    """Другие имена репозитория: artifactId, имя пакета npm/Python, модуль Go."""
    out = {name}
    pom = files.get("pom.xml")
    if pom:
        body = re.sub(r"<parent>.*?</parent>", "", pom, flags=re.S)
        m = re.search(r"<artifactId>([\w.\-]+)</artifactId>", body)
        if m:
            out.add(m.group(1))
    pj = files.get("package.json")
    if pj:
        try:
            n = json.loads(pj).get("name")
            if n:
                out.add(n.split("/")[-1])
        except ValueError:
            pass
    pp = files.get("pyproject.toml") or files.get("setup.py") or ""
    m = re.search(r"""name\s*=\s*['"]([\w.\-]+)['"]""", pp)
    if m:
        out.add(m.group(1))
    gm = files.get("go.mod")
    if gm:
        m = re.search(r"^module\s+(\S+)", gm, re.M)
        if m:
            out.add(m.group(1).rsplit("/", 1)[-1])
    return out


def _scalar(v: str):
    v = v.strip()
    if not v:
        return None
    if v[0] in "\"'" and v[-1] == v[0] and len(v) >= 2:
        return v[1:-1]
    if v.startswith("[") and v.endswith("]"):
        return [_scalar(x) for x in v[1:-1].split(",") if x.strip()]
    if v.startswith("{") and v.endswith("}"):
        out = {}
        for part in v[1:-1].split(","):
            if ":" in part:
                k, val = part.split(":", 1)
                out[k.strip().strip("\"'")] = _scalar(val)
        return out
    return v


def mini_yaml(text: str):
    """Упрощённый разбор YAML (блочные словари и списки) — запасной вариант без PyYAML,
    достаточный для docker-compose."""
    lines = []
    for raw in text.splitlines():
        stripped = re.sub(r"(^|\s)#.*$", "", raw).rstrip()
        if stripped.strip() and stripped.strip() != "---":
            lines.append((len(stripped) - len(stripped.lstrip()), stripped.strip()))

    def parse(i: int, indent: int):
        if i >= len(lines):
            return None, i
        if lines[i][1].startswith("- ") or lines[i][1] == "-":
            seq = []
            while i < len(lines) and lines[i][0] == indent and (lines[i][1].startswith("- ") or lines[i][1] == "-"):
                item = lines[i][1][1:].strip()
                i += 1
                if not item:
                    val, i = parse(i, lines[i][0]) if i < len(lines) and lines[i][0] > indent else (None, i)
                    seq.append(val)
                elif re.match(r"^[\w.\-\"']+\s*:(\s|$)", item):
                    k, v = item.split(":", 1)
                    d = {k.strip().strip("\"'"): _scalar(v)}
                    if i < len(lines) and lines[i][0] > indent:
                        more, i = parse(i, lines[i][0])
                        if isinstance(more, dict):
                            d.update(more)
                    seq.append(d)
                else:
                    seq.append(_scalar(item))
            return seq, i
        mp = {}
        while i < len(lines) and lines[i][0] == indent:
            line = lines[i][1]
            if ":" not in line:
                i += 1
                continue
            k, v = line.split(":", 1)
            k = k.strip().strip("\"'")
            i += 1
            if v.strip() in ("", "|", ">", "|-", ">-"):
                if i < len(lines) and lines[i][0] > indent:
                    val, i = parse(i, lines[i][0])
                elif i < len(lines) and lines[i][0] == indent and lines[i][1].startswith("-"):
                    val, i = parse(i, indent)
                else:
                    val = None
                mp[k] = val
            else:
                mp[k] = _scalar(v)
        return mp, i

    return parse(0, lines[0][0])[0] if lines else {}
