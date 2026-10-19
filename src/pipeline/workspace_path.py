"""Find the Git-folder repo root and put it on sys.path.

Lakeflow runs each pipeline file as an isolated notebook. Sibling imports
such as `import _bootstrap` fail with MODULE_NOT_FOUND. Call this (or the
inlined copy in pipelines/carestaff_insight/*.py) before importing `src`
or `data_generation`.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _looks_like_repo(path: Path) -> bool:
    return (path / "src").is_dir() and (path / "data_generation").is_dir()


def candidate_roots(*, file_path: Path | None = None, cwd: Path | None = None, conf_root: str | None = None) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []

    def add(raw: Path | str | None) -> None:
        if not raw:
            return
        try:
            path = Path(str(raw)).expanduser()
            path = path.resolve() if path.exists() else path
        except OSError:
            path = Path(str(raw))
        for item in [path, *path.parents]:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)

    add(conf_root)
    add(file_path)
    add(cwd if cwd is not None else Path.cwd())
    return out


def find_repo_root(*, file_path: Path | None = None, cwd: Path | None = None, conf_root: str | None = None) -> Path:
    for item in candidate_roots(file_path=file_path, cwd=cwd, conf_root=conf_root):
        if _looks_like_repo(item):
            return item
    raise ModuleNotFoundError(
        "Could not find repo root (need src/ and data_generation/). "
        "In the Lakeflow pipeline configuration add "
        "repo_root = /Workspace/Users/<you>/healthcare-workforce-retention"
    )


def ensure_repo_on_path(*, file_path: Path | None = None, cwd: Path | None = None, conf_root: str | None = None) -> Path:
    root = find_repo_root(file_path=file_path, cwd=cwd, conf_root=conf_root)
    text = str(root)
    if text not in sys.path:
        sys.path.insert(0, text)
    return root
