"""Определение типа и языка файла, правила пропуска каталогов."""
from __future__ import annotations

import posixpath

MAX_FILE_BYTES = 512 * 1024
MAX_FILES_PER_REPO = 6000

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "target", "build", "dist", "out", ".next", ".nuxt", "vendor",
    "__pycache__", ".venv", "venv", "env", ".idea", ".vscode", ".gradle", "coverage", ".pytest_cache",
    ".mypy_cache", "bin", "obj", ".terraform", "bower_components", ".cache",
}

LANGUAGES = {
    "java": "java", "kt": "kotlin", "kts": "kotlin", "scala": "scala", "ts": "typescript", "tsx": "typescript",
    "js": "javascript", "jsx": "javascript", "mjs": "javascript", "cjs": "javascript", "py": "python",
    "go": "go", "cs": "csharp", "rb": "ruby", "php": "php", "rs": "rust", "swift": "swift", "sql": "sql",
    "vue": "vue", "svelte": "svelte", "c": "c", "h": "c", "cpp": "cpp", "hpp": "cpp", "sh": "shell",
    "tf": "terraform", "proto": "protobuf", "graphql": "graphql", "gql": "graphql",
}

BUILD_FILES = {"pom.xml", "package.json", "build.gradle", "build.gradle.kts", "settings.gradle", "go.mod",
               "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "pipfile", "cargo.toml",
               "composer.json", "gemfile", "makefile", "csproj"}
CONFIG_EXT = {"yml", "yaml", "properties", "toml", "ini", "conf", "cfg", "env", "json", "xml", "tfvars", "hcl"}
BINARY_EXT = {"png", "jpg", "jpeg", "gif", "webp", "ico", "svg", "pdf", "zip", "gz", "tar", "jar", "war", "class",
              "exe", "dll", "so", "dylib", "woff", "woff2", "ttf", "otf", "eot", "mp4", "mp3", "lock", "bin",
              "pyc", "db", "sqlite", "parquet", "min.js", "map"}


def ext_of(path: str) -> str:
    name = posixpath.basename(path).lower()
    return name.rsplit(".", 1)[1] if "." in name else ""


def language_of(path: str) -> str | None:
    name = posixpath.basename(path).lower()
    if name == "dockerfile" or name.startswith("dockerfile."):
        return "docker"
    return LANGUAGES.get(ext_of(path))


def kind_of(path: str) -> str | None:
    """Тип файла: CODE, README, API_SPEC, DOCUMENTATION, BUILD_SCRIPT, CONFIG или None (пропустить)."""
    p = path.lower()
    name = posixpath.basename(p)
    ext = ext_of(p)
    if name.endswith(".min.js") or name.endswith(".map") or ext in BINARY_EXT:
        return None
    if name in ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "go.sum"):
        return None
    if name.startswith("readme"):
        return "README"
    if name.startswith(("openapi", "swagger")) or ext in ("proto", "graphql", "gql") or "/openapi/" in p:
        return "API_SPEC"
    if ext in ("md", "adoc", "rst", "txt") and name not in ("requirements.txt",):
        return "DOCUMENTATION"
    if name in BUILD_FILES or ext == "csproj":
        return "BUILD_SCRIPT"
    if name == "dockerfile" or name.startswith("docker-compose") or name.startswith("compose.") or ext in CONFIG_EXT:
        return "CONFIG"
    if ext in LANGUAGES:
        return "CODE"
    return None


def should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or (name.startswith(".") and name not in (".github", ".gitlab"))
