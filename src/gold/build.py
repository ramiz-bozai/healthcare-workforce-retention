"""Build gold tables from silver using tokenized SQL."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pandas as pd

from src.gold.contract import GOLD_TABLES
from src.gold.sql import STATEMENTS


@dataclass(frozen=True)
class GoldResult:
    counts: dict[str, int]
    kpis: pd.DataFrame


def render_sql(
    sql: str,
    *,
    as_of: str,
    history_start: str,
    future_end: str,
    coverage_threshold: float,
    open_shift_threshold: float,
    attrition_horizon: int,
    shortage_primary: int,
    shortage_secondary: int,
) -> str:
    return (
        sql.replace("__AS_OF__", as_of)
        .replace("__HISTORY_START__", history_start)
        .replace("__FUTURE_END__", future_end)
        .replace("__COVERAGE_THRESHOLD__", str(coverage_threshold))
        .replace("__OPEN_SHIFT_THRESHOLD__", str(open_shift_threshold))
        .replace("__ATTRITION_HORIZON__", str(attrition_horizon))
        .replace("__SHORTAGE_PRIMARY__", str(shortage_primary))
        .replace("__SHORTAGE_SECONDARY__", str(shortage_secondary))
    )


def build_gold(
    con: duckdb.DuckDBPyConnection,
    *,
    as_of: str,
    history_start: str,
    future_end: str,
    coverage_threshold: float,
    open_shift_threshold: float,
    attrition_horizon: int,
    shortage_primary: int,
    shortage_secondary: int,
) -> GoldResult:
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    counts: dict[str, int] = {}
    for name, sql in STATEMENTS:
        rendered = render_sql(
            sql,
            as_of=as_of,
            history_start=history_start,
            future_end=future_end,
            coverage_threshold=coverage_threshold,
            open_shift_threshold=open_shift_threshold,
            attrition_horizon=attrition_horizon,
            shortage_primary=shortage_primary,
            shortage_secondary=shortage_secondary,
        )
        con.execute(rendered)
        counts[name] = int(con.execute(f"SELECT COUNT(*) FROM gold.{name}").fetchone()[0])
    missing = set(GOLD_TABLES) - set(counts)
    if missing:
        raise RuntimeError(f"Gold build missing tables: {sorted(missing)}")
    kpis = con.execute("SELECT * FROM gold.executive_kpis").fetchdf()
    return GoldResult(counts=counts, kpis=kpis)
