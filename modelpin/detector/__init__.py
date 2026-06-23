"""Detector — scans a repo for AI model identifier strings. See spec section 4.2."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

# Conservative patterns; extend as providers add families.
MODEL_PATTERNS = [
    re.compile(r"\bgpt-[0-9][\w.\-]*\b"),
    re.compile(r"\bo[0-9][\w.\-]*\b"),
    re.compile(r"\bclaude-[\w.\-]+\b"),
    re.compile(r"\bgemini-[\w.\-]+\b"),
]

DEFAULT_EXTS = {".py", ".env", ".yaml", ".yml", ".json", ".toml", ".js", ".ts"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"}


def _iter_files(root: Path, exts: set[str]) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in exts or p.name == ".env":
            yield p


def scan_repo(root: str | Path = ".", exts: set[str] | None = None) -> list[dict]:
    """Return [{model, file, line}] for every model id found in the repo."""
    root = Path(root)
    exts = exts or DEFAULT_EXTS
    hits: list[dict] = []
    for f in _iter_files(root, exts):
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            for pat in MODEL_PATTERNS:
                for m in pat.findall(line):
                    hits.append({"model": m, "file": str(f.relative_to(root)), "line": i})
    return hits


def models_used(root: str | Path = ".") -> set[str]:
    return {h["model"] for h in scan_repo(root)}
