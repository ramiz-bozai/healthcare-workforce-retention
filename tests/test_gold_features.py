from __future__ import annotations

import pytest

from data_generation.schema import FORBIDDEN_COLUMN_SUBSTRINGS
from src.gold.contract import (
    EMPLOYEE_MONTH_COLUMNS,
    EXEC_KPI_COLUMNS,
    UNIT_DAY_COLUMNS,
    UNIT_WEEK_COLUMNS,
)
from src.pipeline.local_run import run_local


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    pipeline = run_local(
        include_fixtures=False,
        duckdb_path=tmp_path_factory.mktemp("gold_build") / "carestaff.duckdb",
    )
    yield pipeline
    pipeline.con.close()


def test_gold_grains_unique(run):
    con = run.con
    assert con.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT employee_id || CAST(snapshot_date AS VARCHAR)) FROM gold.employee_month_features"
    ).fetchone()[0] == 0
    assert con.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT department_id || CAST(coverage_date AS VARCHAR)) FROM gold.unit_day_coverage"
    ).fetchone()[0] == 0
    assert con.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT department_id || CAST(week_start AS VARCHAR)) FROM gold.unit_week_features"
    ).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM gold.executive_kpis").fetchone()[0] == 1


def test_gold_columns_match_contract(run):
    con = run.con
    emp_cols = [r[0] for r in con.execute("DESCRIBE gold.employee_month_features").fetchall()]
    assert tuple(emp_cols) == EMPLOYEE_MONTH_COLUMNS
    day_cols = [r[0] for r in con.execute("DESCRIBE gold.unit_day_coverage").fetchall()]
    assert tuple(day_cols) == UNIT_DAY_COLUMNS
    week_cols = [r[0] for r in con.execute("DESCRIBE gold.unit_week_features").fetchall()]
    assert tuple(week_cols) == UNIT_WEEK_COLUMNS
    kpi_cols = [r[0] for r in con.execute("DESCRIBE gold.executive_kpis").fetchall()]
    assert tuple(kpi_cols) == EXEC_KPI_COLUMNS


def test_no_protected_or_individual_pay_on_employee_features(run):
    cols = [r[0] for r in run.con.execute("DESCRIBE gold.employee_month_features").fetchall()]
    for col in cols:
        lowered = col.lower()
        for token in FORBIDDEN_COLUMN_SUBSTRINGS:
            if token in ("salary", "wage", "pay_rate"):
                assert token not in lowered
            else:
                assert token not in lowered, col


def test_inference_snapshot_is_frozen_as_of(run):
    row = run.con.execute(
        """
        SELECT COUNT(*), MIN(snapshot_date), MAX(snapshot_date)
        FROM gold.snapshot_calendar
        WHERE is_inference_snapshot
        """
    ).fetchone()
    assert row[0] == 1
    assert str(row[1]) == "2026-09-01"
    active = run.con.execute(
        """
        SELECT COUNT(*) FROM gold.employee_month_features
        WHERE is_inference_snapshot
        """
    ).fetchone()[0]
    assert active == 180


def test_attrition_label_is_voluntary_90d_only(run):
    con = run.con
    # Labels at as_of must match voluntary events in the next 90 days.
    mismatch = con.execute(
        """
        WITH expected AS (
            SELECT employee_id
            FROM silver.attrition_events
            WHERE separation_type = 'voluntary'
              AND separation_date > DATE '2026-09-01'
              AND separation_date <= DATE '2026-09-01' + INTERVAL 90 DAY
        )
        SELECT COUNT(*)
        FROM gold.employee_month_features f
        WHERE f.is_inference_snapshot
          AND f.label_voluntary_90d = 1
          AND f.employee_id NOT IN (SELECT employee_id FROM expected)
        """
    ).fetchone()[0]
    assert mismatch == 0
    involuntary_as_positive = con.execute(
        """
        SELECT COUNT(*)
        FROM gold.employee_month_features f
        JOIN silver.attrition_events a
          ON f.employee_id = a.employee_id
         AND f.is_inference_snapshot
        WHERE f.label_voluntary_90d = 1
          AND a.separation_type = 'involuntary'
          AND a.separation_date > DATE '2026-09-01'
          AND a.separation_date <= DATE '2026-09-01' + INTERVAL 90 DAY
          AND f.employee_id NOT IN (
              SELECT employee_id FROM silver.attrition_events
              WHERE separation_type = 'voluntary'
                AND separation_date > DATE '2026-09-01'
                AND separation_date <= DATE '2026-09-01' + INTERVAL 90 DAY
          )
        """
    ).fetchone()[0]
    assert involuntary_as_positive == 0
    assert con.execute(
        "SELECT MIN(CAST(label_window_complete AS INTEGER)) FROM gold.employee_month_features"
    ).fetchone()[0] == 1


def test_overtime_lookback_does_not_use_future_punches(run):
    con = run.con
    sample = con.execute(
        """
        SELECT employee_id, snapshot_date, ot_hours_30d
        FROM gold.employee_month_features
        WHERE snapshot_date = DATE '2026-06-30'
        LIMIT 8
        """
    ).fetchall()
    assert sample
    for employee_id, snapshot_date, ot_hours in sample:
        recomputed = con.execute(
            """
            SELECT COALESCE(SUM(overtime_hours), 0)
            FROM silver.time_cards
            WHERE employee_id = ?
              AND work_date > CAST(? AS DATE) - INTERVAL 30 DAY
              AND work_date <= CAST(? AS DATE)
            """,
            [employee_id, snapshot_date, snapshot_date],
        ).fetchone()[0]
        assert float(ot_hours) == float(recomputed)


def test_shortage_definition_matches_thresholds(run):
    bad = run.con.execute(
        """
        SELECT COUNT(*) FROM gold.unit_day_coverage
        WHERE is_shortage_day
          AND NOT (
                coverage_ratio < 0.90
                OR open_shift_share > 0.10
          )
        """
    ).fetchone()[0]
    assert bad == 0
    missed = run.con.execute(
        """
        SELECT COUNT(*) FROM gold.unit_day_coverage
        WHERE NOT is_shortage_day
          AND required_hours > 0
          AND (coverage_ratio < 0.90 OR open_shift_share > 0.10)
        """
    ).fetchone()[0]
    assert missed == 0


def test_shortage_14d_label_is_not_complete_after_as_of_minus_14(run):
    incomplete = run.con.execute(
        """
        SELECT COUNT(*) FROM gold.unit_week_features
        WHERE week_end + INTERVAL 14 DAY > DATE '2026-09-01'
          AND label_window_complete_14d
        """
    ).fetchone()[0]
    assert incomplete == 0
    complete_has_realized_window = run.con.execute(
        """
        SELECT COUNT(*) FROM gold.unit_week_features
        WHERE label_window_complete_14d
          AND week_end + INTERVAL 14 DAY > DATE '2026-09-01'
        """
    ).fetchone()[0]
    assert complete_has_realized_window == 0


def test_shortage_weeks_are_mixed_not_all_positive(run):
    true_n, false_n = run.con.execute(
        """
        SELECT
          SUM(CASE WHEN is_shortage_week THEN 1 ELSE 0 END),
          SUM(CASE WHEN is_shortage_week THEN 0 ELSE 1 END)
        FROM gold.unit_week_features
        WHERE label_window_complete_14d
        """
    ).fetchone()
    assert true_n >= 10
    assert false_n >= 10


def test_executive_kpis_are_operational_and_labeled(run):
    kpi = run.gold.kpis.iloc[0]
    assert str(kpi["as_of_date"])[:10] == "2026-09-01"
    assert int(kpi["active_headcount"]) == 180
    assert 0 <= float(kpi["vacancy_rate"]) <= 1
    assert 0.70 <= float(kpi["coverage_ratio_7d"]) <= 1.25
    assert float(kpi["overtime_hours_30d"]) >= 0
    assert float(kpi["trailing_coverage_gap_hours_14d"]) >= 0
    assert float(kpi["planning_open_salary_exposure_usd"]) >= 0
    note = str(kpi["assumption_note"]).lower()
    assert "planning" in note
    assert "salary" not in [c.lower() for c in run.gold.kpis.columns if c != "planning_open_salary_exposure_usd"]
    # Predictions are not in this table yet.
    cols = {c.lower() for c in run.gold.kpis.columns}
    assert "predicted_attrition_rate_90d" not in cols


def test_spark_gold_sql_drops_duckdb_only_tokens():
    from src.gold.build import render_sql
    from src.gold.spark_sql import to_spark_select
    from src.gold.sql import STATEMENTS

    for name, sql in STATEMENTS:
        spark_sql = to_spark_select(
            render_sql(
                sql,
                as_of="2026-09-01",
                history_start="2025-09-01",
                future_end="2026-11-30",
                coverage_threshold=0.90,
                open_shift_threshold=0.10,
                attrition_horizon=90,
                shortage_primary=14,
                shortage_secondary=28,
            )
        )
        assert "generate_series" not in spark_sql.lower(), name
        assert "date_diff" not in spark_sql.lower(), name
        assert "CREATE OR REPLACE" not in spark_sql.upper(), name
        assert "bronze." not in spark_sql
        if "silver." in sql:
            assert "LIVE.silver_" in spark_sql, name
        if name in {"unit_week_features", "employee_month_features", "executive_kpis"}:
            assert "LIVE.gold_" in spark_sql, name


def test_metric_catalog_has_no_model_metrics_yet(run):
    models = run.con.execute(
        "SELECT COUNT(*) FROM gold.metric_catalog WHERE includes_model = 1"
    ).fetchone()[0]
    assert models == 0
