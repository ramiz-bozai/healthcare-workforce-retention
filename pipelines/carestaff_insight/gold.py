"""Lakeflow gold recipe. Workspace-only — not executed locally.

Reuses `src/gold/sql.py` after Spark dialect rewrite. Same tokens as DuckDB:
as_of, coverage 0.90, open-shift 0.10, 90-day attrition, 14/28-day shortage.
"""

from __future__ import annotations

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
