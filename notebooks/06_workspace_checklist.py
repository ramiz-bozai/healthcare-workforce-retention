"""Local checklist for the Databricks Git-folder path. Does not deploy.

    uv run python notebooks/06_workspace_checklist.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_generation.schema import TABLE_ORDER
from src.common.paths import SEED_DIR
from src.gold.sql import STATEMENTS
from src.silver.rules import load_rules


def main() -> None:
    recipe = ROOT / "pipelines" / "carestaff_insight"
    print("Repo root:", ROOT)
    print("Recipe:", recipe)
    print("Remote to add as a Git folder: https://github.com/ramiz-bozai/healthcare-workforce-retention.git")
    print()
    print("=== Seed CSVs bronze will read as {volume}/{table}.csv ===")
    missing = []
    for table in TABLE_ORDER:
        path = SEED_DIR / f"{table}.csv"
        ok = path.exists()
        print(f"  {'ok' if ok else 'MISSING':7} {table}.csv")
        if not ok:
            missing.append(table)
    if missing:
        raise SystemExit(f"Missing seed files: {missing}")
    print()
    print("=== Recipe files (self-contained; no src / data_generation imports) ===")
    for name in ("bronze.py", "silver.py", "gold.py"):
        path = recipe / name
        text = path.read_text() if path.exists() else ""
        banned = any(
            token in text
            for token in ("from src", "from data_generation", "import data_generation", "import yaml", "import _bootstrap")
        )
        status = "ok" if path.exists() and not banned else "MISSING" if not path.exists() else "IMPORTS"
        print(f"  {status:7} {name}")
        if banned:
            raise SystemExit(f"{name} still imports a repo package; Lakeflow will MODULE_NOT_FOUND")
    print()
    print("=== Gold tables the Lakeflow gold.py will register ===")
    for name, _ in STATEMENTS:
        print(f"  gold_{name}")
    print()
    rules = load_rules("2026-09-01", "2025-09-01")
    row = [r.id for r in rules if r.row_predicate]
    set_level = [r.id for r in rules if not r.row_predicate]
    print(f"Per-row expects ({len(row)}):", ", ".join(row))
    print(f"Set-level (workspace query, not expect_or_drop) ({len(set_level)}):", ", ".join(set_level))
    print()
    print("This script did not create a pipeline, App, Genie space, or Serving endpoint.")
    print("Follow docs/workspace.md in your workspace. You click Start.")


if __name__ == "__main__":
    main()
