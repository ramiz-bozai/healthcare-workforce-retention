from __future__ import annotations

from pathlib import Path

from src.common.paths import SEED_DIR
from src.pipeline.local_run import run_local
from src.silver.rules import load_rules, spark_row_expectations


def _seed_rows(table: str) -> int:
    path = SEED_DIR / f"{table}.csv"
    return sum(1 for _ in path.open()) - 1

FIXTURE_EMPLOYEES = {f"EMP-FIX00{i}" for i in range(1, 8)}


def test_seed_without_fixtures_has_no_error_violations(tmp_path: Path):
    run = run_local(
        include_fixtures=False,
        duckdb_path=tmp_path / "clean.duckdb",
    )
    try:
        assert run.bronze_counts["employees"] == _seed_rows("employees")
        assert run.silver.silver_counts["employees"] == _seed_rows("employees")
        assert run.silver.violation_counts == {}
        assert len(run.silver.violations) == 0
        active = run.con.execute(
            "SELECT COUNT(*) FROM silver.employees WHERE employment_status = 'active'"
        ).fetchone()[0]
        assert active == 180
    finally:
        run.con.close()


def test_fixtures_are_quarantined_and_seed_rows_remain(tmp_path: Path):
    run = run_local(
        include_fixtures=True,
        duckdb_path=tmp_path / "fx.duckdb",
    )
    try:
        assert run.bronze_counts["employees"] == _seed_rows("employees") + 8
        assert run.bronze_counts["staffing_requirements"] == _seed_rows("staffing_requirements") + 1
        assert run.bronze_counts["time_cards"] == _seed_rows("time_cards") + 1
        assert run.silver.silver_counts["employees"] == _seed_rows("employees")
        silver_ids = set(
            run.con.execute("SELECT employee_id FROM silver.employees").fetchdf()["employee_id"]
        )
        assert FIXTURE_EMPLOYEES.isdisjoint(silver_ids)
        assert "EMP-000001" in silver_ids
        fired = set(run.silver.violation_counts)
        for rule_id in (
            "emp_pk_unique",
            "emp_required_fields",
            "emp_valid_hire_date",
            "emp_fk_department",
            "emp_fte_bounds",
            "emp_valid_termination",
            "emp_status_values",
            "emp_missing_shift_assignments",
            "staff_heads_bounds",
            "staff_hours_match",
            "staff_valid_date",
            "tc_hours_bounds",
            "tc_overtime_consistent",
        ):
            assert rule_id in fired, f"expected {rule_id} to fire on fixtures"
        keys = set(run.silver.violations["record_key"].astype(str))
        assert "EMP-FIX001" in keys
        assert "EMP-FIX002" in keys
        assert "EMP-FIX003" in keys
        assert "EMP-FIX004" in keys
        assert "EMP-FIX005" in keys
        assert "EMP-FIX006" in keys
        assert "EMP-FIX007" in keys
        assert "NSH-ICU|2099-01-01|DAYS" in keys
        assert "TC-FIX0001" in keys
        staff_silver = int(
            run.con.execute(
                """
                SELECT COUNT(*) FROM silver.staffing_requirements
                WHERE department_id = 'NSH-ICU'
                  AND requirement_date = DATE '2099-01-01'
                """
            ).fetchone()[0]
        )
        assert staff_silver == 0
    finally:
        run.con.close()


def test_silver_referential_integrity(tmp_path: Path):
    run = run_local(include_fixtures=True, duckdb_path=tmp_path / "fk.duckdb")
    try:
        orphans = run.con.execute(
            """
            SELECT COUNT(*) FROM silver.employees e
            LEFT JOIN silver.departments d ON e.department_id = d.department_id
            WHERE d.department_id IS NULL
            """
        ).fetchone()[0]
        assert orphans == 0
        sched_orphans = run.con.execute(
            """
            SELECT COUNT(*) FROM silver.schedule_assignments s
            LEFT JOIN silver.employees e ON s.employee_id = e.employee_id
            WHERE e.employee_id IS NULL
            """
        ).fetchone()[0]
        assert sched_orphans == 0
        heads = run.con.execute(
            """
            SELECT MIN(required_heads), MAX(required_heads)
            FROM silver.staffing_requirements
            """
        ).fetchone()
        assert heads[0] >= 1
        assert heads[1] <= 40
    finally:
        run.con.close()


def test_bronze_is_all_varchar_payload(tmp_path: Path):
    run = run_local(include_fixtures=False, duckdb_path=tmp_path / "types.duckdb")
    try:
        rows = run.con.execute(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = 'bronze' AND table_name = 'employees'
              AND column_name = 'hire_date'
            """
        ).fetchall()
        assert rows[0][0].upper() in {"VARCHAR", "TEXT", "STRING"}
        silver_type = run.con.execute(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = 'silver' AND table_name = 'employees'
              AND column_name = 'hire_date'
            """
        ).fetchone()[0]
        assert "DATE" in silver_type.upper()
    finally:
        run.con.close()


def test_row_predicates_exist_for_dlt_subset():
    rules = load_rules("2026-09-01", "2025-09-01")
    expects = spark_row_expectations("employees", rules)
    assert "emp_fte_bounds" in expects
    assert "emp_pk_unique" not in expects
    assert "emp_fk_department" not in expects
    assert "0.6" in expects["emp_fte_bounds"]
