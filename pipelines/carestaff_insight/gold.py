"""Lakeflow gold recipe. Workspace-only — not executed locally.

Reuses `src/gold/sql.py` after Spark dialect rewrite. Same tokens as DuckDB:
as_of, coverage 0.90, open-shift 0.10, 90-day attrition, 14/28-day shortage.
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  — repo root on sys.path

try:
    import dlt
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pipelines/carestaff_insight is the Databricks path. Run `python -m src.pipeline` locally."
    ) from exc

from data_generation.config import load_config
from src.gold.build import render_sql
from src.gold.spark_sql import to_spark_select
from src.gold.sql import STATEMENTS

_CFG = load_config("seed")
_LABELS = _CFG.raw["labels"]
AS_OF = _CFG.as_of_date.isoformat()
HISTORY_START = _CFG.history_start.isoformat()
FUTURE_END = _CFG.future_end.isoformat()
COVERAGE_THRESHOLD = float(_LABELS["shortage_coverage_ratio_threshold"])
OPEN_SHIFT_THRESHOLD = float(_LABELS["shortage_open_shift_share_threshold"])
ATTRITION_HORIZON = int(_LABELS["attrition_horizon_days"])
SHORTAGE_PRIMARY = int(_LABELS["shortage_primary_horizon_days"])
SHORTAGE_SECONDARY = int(_LABELS["shortage_secondary_horizon_days"])


def _spark_query(sql: str) -> str:
    rendered = render_sql(
        sql,
        as_of=AS_OF,
        history_start=HISTORY_START,
        future_end=FUTURE_END,
        coverage_threshold=COVERAGE_THRESHOLD,
        open_shift_threshold=OPEN_SHIFT_THRESHOLD,
        attrition_horizon=ATTRITION_HORIZON,
        shortage_primary=SHORTAGE_PRIMARY,
        shortage_secondary=SHORTAGE_SECONDARY,
    )
    return to_spark_select(rendered)


def _register_gold(table_name: str, sql: str) -> None:
    query = _spark_query(sql)

    def _load(_q: str = query):
        return spark.sql(_q)  # noqa: F821

    _load.__name__ = f"gold_{table_name}"
    dlt.table(name=f"gold_{table_name}", comment=f"Gold {table_name}; SQL from src/gold/sql.py")(_load)


for _name, _sql in STATEMENTS:
    _register_gold(_name, _sql)
