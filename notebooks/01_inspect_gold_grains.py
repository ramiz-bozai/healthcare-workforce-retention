"""Inspect gold grains. Runnable locally; paste into a Databricks notebook later.

    uv run python notebooks/01_inspect_gold_grains.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import duckdb

from src.common.paths import DEFAULT_DUCKDB
from src.pipeline.local_run import run_local

GRAINS = (
    ("gold.snapshot_calendar", "snapshot_date", "Frozen as_of plus prior month-ends"),
    ("gold.employee_month_features", "employee_id x snapshot_date", "Attrition model input; label is future voluntary 90d"),
    ("gold.unit_day_coverage", "department_id x coverage_date", "Coverage, OT, open shifts, shortage day flag"),
    ("gold.unit_week_features", "department_id x week_start", "Shortage model input; 14d label only when week_end+14 <= as_of"),
    ("gold.executive_kpis", "one row per as_of", "Operational exec strip. No model scores in Increment 3."),
    ("gold.metric_catalog", "metric_name", "The only list of metric formulas the assistant may cite later"),
    ("gold.role_cost_assumptions", "role_code", "Planning dollars. Not a model feature."),
)


def main() -> None:
    db_path = DEFAULT_DUCKDB if DEFAULT_DUCKDB.exists() else (ROOT / "data" / "generated" / "inspect.duckdb")
    if not DEFAULT_DUCKDB.exists():
        print("DuckDB missing; building pipeline with fixtures into data/generated/inspect.duckdb")
        run = run_local(include_fixtures=True, duckdb_path=db_path)
        run.con.close()
    con = duckdb.connect(str(db_path), read_only=True)
    print("DuckDB:", db_path)
    print()
    print("=== Grains ===")
    for table, grain, meaning in GRAINS:
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:34s}  n={n:7d}  grain={grain}")
        print(f"{'':34s}  {meaning}")
    print()
    print("=== Executive KPIs (cite this table only for exec numbers) ===")
    print(con.execute("SELECT * FROM gold.executive_kpis").fetchdf().T.to_string())
    print()
    print("=== Inference snapshot attrition labels ===")
    print(
        con.execute(
            """
            SELECT label_voluntary_90d, COUNT(*) AS employees
            FROM gold.employee_month_features
            WHERE is_inference_snapshot
            GROUP BY 1
            ORDER BY 1
            """
        ).fetchdf().to_string(index=False)
    )
    print()
    print("=== Shortage weeks with a complete 14-day label window ===")
    print(
        con.execute(
            """
            SELECT is_shortage_week, label_shortage_next_14d, COUNT(*) AS unit_weeks
            FROM gold.unit_week_features
            WHERE label_window_complete_14d
            GROUP BY 1, 2
            ORDER BY 1, 2
            """
        ).fetchdf().to_string(index=False)
    )
    print()
    print("=== Example high-OT employee at as_of (features only; not a model score) ===")
    print(
        con.execute(
            """
            SELECT employee_id, role_code, department_id, tenure_band, primary_shift_code,
                   ot_hours_30d, swap_count_90d, nights_share_90d, unit_vacancy_rate,
                   label_voluntary_90d
            FROM gold.employee_month_features
            WHERE is_inference_snapshot
            ORDER BY ot_hours_30d DESC
            LIMIT 5
            """
        ).fetchdf().to_string(index=False)
    )
    con.close()
    print()
    print("Predictions are not in gold yet. Increment 4 trains the two models.")


if __name__ == "__main__":
    main()
