"""Lakeflow / DLT silver recipe. Workspace-only — not executed locally.

Per-row expects use IDs from conf/dq_rules.yaml. Uniqueness and FK checks are
set-level; do not implement them as per-row expects. Run those rule SQLs as a
materialized view / expectation query in the workspace, the same way DuckDB
writes silver.dq_violations locally.
"""

from __future__ import annotations

import re

import _bootstrap  # noqa: F401  — repo root on sys.path

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
