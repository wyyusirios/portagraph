"""Извлечение структуры кода: символы (классы, интерфейсы, функции), импорты,
пакет файла, HTTP-эндпоинты и признаки сущностей БД.

Python разбирается встроенным модулем ``ast``. Для Java, Kotlin, C#, Scala,
TypeScript/JavaScript и Go используется лексический разбор: объявления находятся
регулярными выражениями, а границы тела – по балансу фигурных скобок без учёта
строк и комментариев.
"""
from __future__ import annotations

import ast
import posixpath
import re
from dataclasses import dataclass, field

from .chunker import SymbolSpan


@dataclass
class FileStructure:
    language: str | None
    package: str | None = None
    symbols: list[SymbolSpan] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    endpoints: list[dict] = field(default_factory=list)   # {"method","path","symbol","line"}
    entities: dict[str, str] = field(default_factory=dict)  # имя класса → таблица
    stereotypes: dict[str, str] = field(default_factory=dict)  # имя класса → controller/service/…


# ------------------------------------------------------------------ вспомогательное
def _strip_code(text: str) -> str:
    """Заменяет содержимое строк и комментариев пробелами, сохраняя длину и переводы строк."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        elif c in "\"'`":
            q = c
            if text.startswith(q * 3, i) and q in "\"'":
                end = text.find(q * 3, i + 3)
                end = n if end < 0 else end + 3
            else:
                end = i + 1
                while end < n and text[end] != q:
                    if text[end] == "\\":
                        end += 1
                    elif text[end] == "\n" and q != "`":
                        break
                    end += 1
                end = min(n, end + 1)
            for k in range(i + 1, end - 1):
                if out[k] != "\n":
                    out[k] = " "
            i = end
        else:
            i += 1
    return "".join(out)


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for i, c in enumerate(text):
        if c == "\n":
            starts.append(i + 1)
    return starts


def _line_at(starts: list[int], offset: int) -> int:
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def _block_end(clean: str, start: int) -> int | None:
    """Смещение закрывающей скобки тела, начинающегося после `start`, или None, если тела нет."""
    i, n = start, len(clean)
    paren = 0
    while i < n:
        c = clean[i]
        if c == "(":
            paren += 1
        elif c == ")":
            paren -= 1
        elif c == "{" and paren <= 0:
            depth = 0
            for j in range(i, n):
                if clean[j] == "{":
                    depth += 1
                elif clean[j] == "}":
                    depth -= 1
                    if depth == 0:
                        return j
            return n - 1
        elif c in ";=" and paren <= 0 and c != "=":
            return None
        elif c == "\n" and paren <= 0 and clean[start:i].strip().endswith(")"):
            # объявление без тела (data class X(val a: Int))
            nxt = clean[i:i + 200].lstrip()
            if not nxt.startswith(("{", ":")):
                return None
        i += 1
    return None


# ------------------------------------------------------------------ языки с фигурными скобками
_JVM_DECL = re.compile(
    r"^[ \t]*(?:@\w+(?:\([^)\n]*\))?\s+)*(?:(?:public|private|protected|internal|abstract|final|static|sealed|open|"
    r"data|inner|enum|annotation|value|partial|readonly|override)\s+)*"
    r"(class|interface|enum|record|object|@interface|struct)\s+([A-Za-z_]\w*)", re.M)
_TS_DECL = re.compile(
    r"^[ \t]*(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
    r"(class|interface|function\*?|enum)\s+([A-Za-z_$][\w$]*)", re.M)
_TS_ARROW = re.compile(
    r"^[ \t]*(?:export\s+)?(?:const|let)\s+([A-Za-z_$][\w$]*)\s*(?::[^=\n]+)?=\s*(?:async\s+)?"
    r"(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?::[^=\n]+)?=>", re.M)
_GO_DECL = re.compile(r"^(?:func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(|type\s+([A-Za-z_]\w*)\s+(struct|interface)\b)", re.M)


def _brace_symbols(text: str, language: str) -> list[SymbolSpan]:
    clean = _strip_code(text)
    starts = _line_starts(text)
    found: list[SymbolSpan] = []

    def add(name: str, kind: str, m_start: int, body_from: int):
        end = _block_end(clean, body_from)
        a = _line_at(starts, m_start)
        b = _line_at(starts, end) if end is not None else a
        found.append(SymbolSpan(name, kind, a, max(a, b)))

    if language in ("java", "kotlin", "csharp", "scala"):
        for m in _JVM_DECL.finditer(clean):
            kind = {"@interface": "annotation", "record": "class", "object": "class", "struct": "class"}.get(m.group(1), m.group(1))
            add(m.group(2), kind, m.start(2), m.end())
    elif language in ("typescript", "javascript", "vue", "svelte"):
        for m in _TS_DECL.finditer(clean):
            kind = "function" if m.group(1).startswith("function") else m.group(1)
            add(m.group(2), kind, m.start(2), m.end())
        for m in _TS_ARROW.finditer(clean):
            add(m.group(1), "function", m.start(1), m.end())
    elif language == "go":
        for m in _GO_DECL.finditer(clean):
            if m.group(1):
                add(m.group(1), "function", m.start(1), m.end())
            else:
                add(m.group(2), "class" if m.group(3) == "struct" else "interface", m.start(2), m.end())
    found.sort(key=lambda s: (s.start_line, -s.end_line))
    # убираем дубли одного символа
    uniq, seen = [], set()
    for s in found:
        key = (s.name, s.start_line)
        if key not in seen:
            seen.add(key)
            uniq.append(s)
    return uniq


_JVM_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+?)(?:\.\*)?\s*;?\s*$", re.M)
_JVM_PACKAGE = re.compile(r"^\s*(?:package|namespace)\s+([\w.]+)", re.M)
_CS_USING = re.compile(r"^\s*using\s+([\w.]+)\s*;", re.M)
_TS_IMPORT = re.compile(r"""(?:import|export)\s[^;'"]*?from\s*['"]([^'"]+)['"]|import\s*['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)""")
_GO_IMPORT_BLOCK = re.compile(r"import\s*\(([^)]*)\)", re.S)
_GO_IMPORT_ONE = re.compile(r'import\s+(?:\w+\s+)?"([^"]+)"')
_GO_PACKAGE = re.compile(r"^package\s+(\w+)", re.M)

# HTTP-эндпоинты
_SPRING_MAP = re.compile(r"@(Get|Post|Put|Delete|Patch|Request)Mapping\s*(?:\(\s*(?:value\s*=\s*|path\s*=\s*)?\{?\s*\"([^\"]*)\")?")
_EXPRESS = re.compile(r"\b(?:app|router|server)\.(get|post|put|delete|patch)\(\s*['\"`]([^'\"`]+)['\"`]")
_PY_ROUTE = re.compile(r"@\w+\.(get|post|put|delete|patch|route)\(\s*['\"]([^'\"]+)['\"](?:[^)]*methods\s*=\s*\[([^\]]*)\])?")
_SPRING_STEREO = re.compile(r"@(RestController|Controller|Service|Repository|Component|Configuration|Entity|SpringBootApplication|KafkaListener)\b")
_TABLE = re.compile(r"@Table\s*\(\s*name\s*=\s*\"(\w+)\"")


def _jvm_extra(text: str, st: FileStructure):
    starts = _line_starts(text)
    class_spans = [s for s in st.symbols if s.kind in ("class", "interface")]

    def owner(line: int) -> str | None:
        best = None
        for s in class_spans:
            if s.start_line <= line <= s.end_line and (best is None or s.start_line >= best.start_line):
                best = s
        return best.name if best else None

    base: dict[str, str] = {}
    for m in _SPRING_MAP.finditer(text):
        line = _line_at(starts, m.start())
        cls = owner(line)
        verb, path = m.group(1), m.group(2) or ""
        # @RequestMapping перед объявлением класса задаёт префикс
        if verb == "Request" and cls and any(s.name == cls and line <= s.start_line + 1 for s in class_spans):
            base[cls] = path
            continue
        nxt = next((s for s in class_spans if s.start_line > line), None)
        if verb == "Request" and nxt and cls is None:
            base[nxt.name] = path
            continue
        method = "ANY" if verb == "Request" else verb.upper()
        st.endpoints.append({"method": method, "path": path, "symbol": cls, "line": line})
    for ep in st.endpoints:
        if ep["symbol"] in base:
            ep["path"] = (base[ep["symbol"]].rstrip("/") + "/" + ep["path"].lstrip("/")).rstrip("/") or "/"
    for m in _SPRING_STEREO.finditer(text):
        line = _line_at(starts, m.start())
        nxt = next((s for s in class_spans if s.start_line >= line), None)
        if nxt and nxt.start_line - line <= 6:
            kind = m.group(1)
            if kind == "Entity":
                tm = _TABLE.search(text, m.start(), starts[min(len(starts) - 1, nxt.start_line)] if nxt.start_line < len(starts) else len(text))
                st.entities[nxt.name] = tm.group(1) if tm else _snake(nxt.name)
            elif kind != "KafkaListener":
                st.stereotypes.setdefault(nxt.name, {"RestController": "controller", "Controller": "controller",
                                                     "SpringBootApplication": "application"}.get(kind, kind.lower()))


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower() + "s"


# ------------------------------------------------------------------ Python
def _python(text: str, path: str, st: FileStructure):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return
    st.package = module_of_python(path)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            st.symbols.append(SymbolSpan(node.name, "class", node.lineno, getattr(node, "end_lineno", node.lineno)))
            for stmt in node.body:
                if (isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in stmt.targets)
                        and isinstance(stmt.value, ast.Constant)):
                    st.entities[node.name] = str(stmt.value.value)
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name) and dec.id == "dataclass":
                    st.stereotypes[node.name] = "dataclass"
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            st.symbols.append(SymbolSpan(node.name, "function", node.lineno, getattr(node, "end_lineno", node.lineno)))
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.args \
                        and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                    verb = dec.func.attr.lower()
                    if verb in ("get", "post", "put", "delete", "patch", "route"):
                        method = "GET" if verb == "route" else verb.upper()
                        for kw in dec.keywords:
                            if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)) and kw.value.elts:
                                first = kw.value.elts[0]
                                if isinstance(first, ast.Constant):
                                    method = str(first.value).upper()
                        st.endpoints.append({"method": method, "path": dec.args[0].value, "symbol": node.name, "line": dec.lineno})
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            st.imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                pkg = (st.package or "").split(".")
                pkg = pkg[: max(0, len(pkg) - node.level)]
                base = ".".join([*pkg, base] if base else pkg)
            for a in node.names:
                st.imports.append(f"{base}.{a.name}" if base else a.name)


def module_of_python(path: str) -> str:
    p = path[:-3] if path.endswith(".py") else path
    parts = [x for x in p.split("/") if x]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if parts and parts[0] in ("src", "app") and len(parts) > 1 and parts[0] == "src":
        parts = parts[1:]
    return ".".join(parts)


# ------------------------------------------------------------------ точка входа
def analyze_file(path: str, text: str, language: str | None) -> FileStructure:
    st = FileStructure(language)
    if not text or language is None:
        return st
    if language == "python":
        _python(text, path, st)
        return st
    st.symbols = _brace_symbols(text, language)
    if language in ("java", "kotlin", "scala", "csharp"):
        pm = _JVM_PACKAGE.search(text)
        st.package = pm.group(1) if pm else None
        st.imports = [m.group(1) for m in _JVM_IMPORT.finditer(text)]
        if language == "csharp":
            st.imports += [m.group(1) for m in _CS_USING.finditer(text)]
        _jvm_extra(text, st)
    elif language in ("typescript", "javascript", "vue", "svelte"):
        st.package = path
        st.imports = [next(g for g in m.groups() if g) for m in _TS_IMPORT.finditer(text)]
        starts = _line_starts(text)
        for m in _EXPRESS.finditer(text):
            st.endpoints.append({"method": m.group(1).upper(), "path": m.group(2), "symbol": None,
                                 "line": _line_at(starts, m.start())})
        # маршруты Next.js: app/**/route.ts и pages/api/**
        nm = re.search(r"(?:^|/)app/(.*)/route\.[jt]sx?$", path) or re.search(r"(?:^|/)pages/(api/.*)\.[jt]sx?$", path)
        if nm:
            for s in st.symbols:
                if s.name in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    st.endpoints.append({"method": s.name, "path": "/" + nm.group(1), "symbol": s.name, "line": s.start_line})
    elif language == "go":
        pm = _GO_PACKAGE.search(text)
        st.package = pm.group(1) if pm else None
        for block in _GO_IMPORT_BLOCK.findall(text):
            st.imports += re.findall(r'"([^"]+)"', block)
        st.imports += _GO_IMPORT_ONE.findall(text)
    return st


def resolve_ts_import(from_path: str, spec: str, known_paths: set[str]) -> str | None:
    """Путь файла, на который указывает относительный импорт TypeScript/JavaScript."""
    if not spec.startswith("."):
        return None
    base = posixpath.normpath(posixpath.join(posixpath.dirname(from_path), spec))
    for cand in (base, *(base + e for e in (".ts", ".tsx", ".js", ".jsx", ".mjs")),
                 *(posixpath.join(base, "index" + e) for e in (".ts", ".tsx", ".js", ".jsx"))):
        if cand in known_paths:
            return cand
    return None
