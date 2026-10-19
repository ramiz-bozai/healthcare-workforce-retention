"""Lakeflow / DLT silver recipe. Workspace-only — not executed locally.

Per-row expects use IDs from conf/dq_rules.yaml. Uniqueness and FK checks are
set-level; do not implement them as per-row expects. Run those rule SQLs as a
materialized view / expectation query in the workspace, the same way DuckDB
writes silver.dq_violations locally.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def _ensure_repo_on_path() -> None:
    """Lakeflow isolates each notebook. Sibling `import _bootstrap` will not work."""
    conf_root = ""
    try:
        conf_root = str(spark.conf.get("repo_root", "") or "")  # noqa: F821
    except Exception:
        conf_root = ""
    try:
        file_path = Path(__file__).resolve()
    except NameError:
        file_path = None
    seen: set[Path] = set()
    ordered: list[Path] = []

    def _add(raw: object) -> None:
        if not raw:
            return
        path = Path(str(raw))
        try:
            path = path.expanduser().resolve()
        except OSError:
            pass
        for item in (path, *path.parents):
            if item not in seen:
                seen.add(item)
                ordered.append(item)

    _add(conf_root)
    _add(file_path)
    _add(Path.cwd())
    for item in ordered:
        if (item / "src").is_dir() and (item / "data_generation").is_dir():
            text = str(item)
            if text not in sys.path:
                sys.path.insert(0, text)
            return
    raise ModuleNotFoundError(
        "Could not find repo root (src/ and data_generation/). "
        "Set pipeline configuration repo_root to the Git folder path, "
        "for example /Workspace/Users/<you>/healthcare-workforce-retention"
    )


_ensure_repo_on_path()

try:
    import dlt
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pipelines/carestaff_insight is the Databricks path. Run `python -m src.pipeline` locally."
    ) from exc

from data_generation.schema import TABLE_ORDER
from src.silver.rules import load_rules, spark_row_expectations
from src.silver.standardize import staging_sql

AS_OF = "2026-09-01"
HISTORY_START = "2025-09-01"
RULES = load_rules(as_of=AS_OF, history_start=HISTORY_START)


def _from_live_bronze(table: str) -> str:
    sql = staging_sql(table)
    sql = re.sub(
        rf"CREATE OR REPLACE TABLE silver\.stg_{re.escape(table)} AS",
        "",
        sql,
        count=1,
        flags=re.IGNORECASE,
    )
    return sql.replace(f"FROM bronze.{table}", f"FROM LIVE.bronze_{table}")


def _register_silver(table_name: str) -> None:
    expects = spark_row_expectations(table_name, RULES)
    query = _from_live_bronze(table_name)

    def _load(_q: str = query):
        return spark.sql(_q)  # noqa: F821

    _load.__name__ = f"silver_{table_name}"
    if expects:
        _load = dlt.expect_all_or_drop(expects)(_load)
    dlt.table(name=f"silver_{table_name}", comment=f"Typed {table_name}; per-row expects share local rule IDs")(_load)


for _table in TABLE_ORDER:
    _register_silver(_table)
