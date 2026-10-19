"""Lakeflow / DLT silver recipe. Workspace-only — not executed locally.

Self-contained: stdlib + dlt/pyspark only. Lakeflow isolates each file as a
notebook, so this module must not import `src`, `data_generation`, yaml, or a sibling.

Casts match `src.silver.standardize`. Per-row expects match `conf/dq_rules.yaml`
IDs with as_of=2026-09-01 and history_start=2025-09-01. Uniqueness and FK checks
are set-level; do not implement them as per-row expects.
"""

from __future__ import annotations

try:
    import dlt  # Databricks Lakeflow / DLT
except ImportError:
    try:
        from pyspark import pipelines as dlt  # Spark Declarative Pipelines
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "pipelines/carestaff_insight is the Databricks path. "
            "Run `python -m src.pipeline` locally."
        ) from exc

STAGING_SQL: dict[str, str] = {
    'facilities': """SELECT
      NULLIF(TRIM(CAST(facility_id AS STRING)), '') AS facility_id,
      NULLIF(TRIM(CAST(facility_name AS STRING)), '') AS facility_name,
      NULLIF(TRIM(CAST(facility_type AS STRING)), '') AS facility_type,
      _ingest_ts,
      _source_path,
      _record_origin
    FROM LIVE.bronze_facilities""",
    'departments': """SELECT
      NULLIF(TRIM(CAST(department_id AS STRING)), '') AS department_id,
      NULLIF(TRIM(CAST(facility_id AS STRING)), '') AS facility_id,
      NULLIF(TRIM(CAST(department_name AS STRING)), '') AS department_name,
      NULLIF(TRIM(CAST(service_line AS STRING)), '') AS service_line,
      NULLIF(TRIM(CAST(unit_type AS STRING)), '') AS unit_type,
      TRY_CAST(NULLIF(TRIM(CAST(target_headcount AS STRING)), '') AS INTEGER) AS target_headcount,
      TRY_CAST(NULLIF(TRIM(CAST(vacancy_rate AS STRING)), '') AS DOUBLE) AS vacancy_rate,
      _ingest_ts,
      _source_path,
      _record_origin
    FROM LIVE.bronze_departments""",
    'roles': """SELECT
      NULLIF(TRIM(CAST(role_code AS STRING)), '') AS role_code,
      NULLIF(TRIM(CAST(role_name AS STRING)), '') AS role_name,
      NULLIF(TRIM(CAST(job_family AS STRING)), '') AS job_family,
      _ingest_ts,
      _source_path,
      _record_origin
    FROM LIVE.bronze_roles""",
    'shifts': """SELECT
      NULLIF(TRIM(CAST(shift_code AS STRING)), '') AS shift_code,
      NULLIF(TRIM(CAST(shift_name AS STRING)), '') AS shift_name,
      TRY_CAST(NULLIF(TRIM(CAST(scheduled_hours AS STRING)), '') AS DOUBLE) AS scheduled_hours,
      _ingest_ts,
      _source_path,
      _record_origin
    FROM LIVE.bronze_shifts""",
    'compensation_bands': """SELECT
      NULLIF(TRIM(CAST(role_code AS STRING)), '') AS role_code,
      NULLIF(TRIM(CAST(band_code AS STRING)), '') AS band_code,
      TRY_CAST(NULLIF(TRIM(CAST(band_rank AS STRING)), '') AS INTEGER) AS band_rank,
      _ingest_ts,
      _source_path,
      _record_origin
    FROM LIVE.bronze_compensation_bands""",
    'role_cost_assumptions': """SELECT
      NULLIF(TRIM(CAST(role_code AS STRING)), '') AS role_code,
      TRY_CAST(NULLIF(TRIM(CAST(avg_annual_salary_usd AS STRING)), '') AS DOUBLE) AS avg_annual_salary_usd,
      TRY_CAST(NULLIF(TRIM(CAST(hours_per_year AS STRING)), '') AS INTEGER) AS hours_per_year,
      TRY_CAST(NULLIF(TRIM(CAST(hourly_equivalent_usd AS STRING)), '') AS DOUBLE) AS hourly_equivalent_usd,
      TRY_CAST(NULLIF(TRIM(CAST(replacement_multiplier AS STRING)), '') AS DOUBLE) AS replacement_multiplier,
      TRY_CAST(NULLIF(TRIM(CAST(agency_hourly_usd AS STRING)), '') AS DOUBLE) AS agency_hourly_usd,
      NULLIF(TRIM(CAST(assumption_note AS STRING)), '') AS assumption_note,
      _ingest_ts,
      _source_path,
      _record_origin
    FROM LIVE.bronze_role_cost_assumptions""",
    'employees': """SELECT
      NULLIF(TRIM(CAST(employee_id AS STRING)), '') AS employee_id,
      NULLIF(TRIM(CAST(first_name AS STRING)), '') AS first_name,
      NULLIF(TRIM(CAST(last_initial AS STRING)), '') AS last_initial,
      NULLIF(TRIM(CAST(display_name AS STRING)), '') AS display_name,
      NULLIF(TRIM(CAST(role_code AS STRING)), '') AS role_code,
      NULLIF(TRIM(CAST(department_id AS STRING)), '') AS department_id,
      NULLIF(TRIM(CAST(facility_id AS STRING)), '') AS facility_id,
      NULLIF(TRIM(CAST(manager_employee_id AS STRING)), '') AS manager_employee_id,
      TRY_CAST(NULLIF(TRIM(CAST(hire_date AS STRING)), '') AS DATE) AS hire_date,
      TRY_CAST(NULLIF(TRIM(CAST(fte AS STRING)), '') AS DOUBLE) AS fte,
      NULLIF(TRIM(CAST(primary_shift_code AS STRING)), '') AS primary_shift_code,
      NULLIF(TRIM(CAST(compensation_band AS STRING)), '') AS compensation_band,
      LOWER(NULLIF(TRIM(CAST(employment_status AS STRING)), '')) AS employment_status,
      TRY_CAST(NULLIF(TRIM(CAST(termination_date AS STRING)), '') AS DATE) AS termination_date,
      _ingest_ts,
      _source_path,
      _record_origin
    FROM LIVE.bronze_employees""",
    'schedule_assignments': """SELECT
      NULLIF(TRIM(CAST(assignment_id AS STRING)), '') AS assignment_id,
      NULLIF(TRIM(CAST(employee_id AS STRING)), '') AS employee_id,
      NULLIF(TRIM(CAST(department_id AS STRING)), '') AS department_id,
      TRY_CAST(NULLIF(TRIM(CAST(shift_date AS STRING)), '') AS DATE) AS shift_date,
      NULLIF(TRIM(CAST(shift_code AS STRING)), '') AS shift_code,
      TRY_CAST(NULLIF(TRIM(CAST(scheduled_hours AS STRING)), '') AS DOUBLE) AS scheduled_hours,
      TRY_CAST(NULLIF(TRIM(CAST(is_extra_shift AS STRING)), '') AS INTEGER) AS is_extra_shift,
      TRY_CAST(NULLIF(TRIM(CAST(is_swap AS STRING)), '') AS INTEGER) AS is_swap,
      _ingest_ts,
      _source_path,
      _record_origin
    FROM LIVE.bronze_schedule_assignments""",
    'time_cards': """SELECT
      NULLIF(TRIM(CAST(time_card_id AS STRING)), '') AS time_card_id,
      NULLIF(TRIM(CAST(employee_id AS STRING)), '') AS employee_id,
      NULLIF(TRIM(CAST(department_id AS STRING)), '') AS department_id,
      TRY_CAST(NULLIF(TRIM(CAST(work_date AS STRING)), '') AS DATE) AS work_date,
      NULLIF(TRIM(CAST(shift_code AS STRING)), '') AS shift_code,
      TRY_CAST(NULLIF(TRIM(CAST(hours_worked AS STRING)), '') AS DOUBLE) AS hours_worked,
      TRY_CAST(NULLIF(TRIM(CAST(overtime_hours AS STRING)), '') AS DOUBLE) AS overtime_hours,
      _ingest_ts,
      _source_path,
      _record_origin
    FROM LIVE.bronze_time_cards""",
    'absences': """SELECT
      NULLIF(TRIM(CAST(absence_id AS STRING)), '') AS absence_id,
      NULLIF(TRIM(CAST(employee_id AS STRING)), '') AS employee_id,
      NULLIF(TRIM(CAST(department_id AS STRING)), '') AS department_id,
      TRY_CAST(NULLIF(TRIM(CAST(absence_date AS STRING)), '') AS DATE) AS absence_date,
      LOWER(NULLIF(TRIM(CAST(absence_type AS STRING)), '')) AS absence_type,
      TRY_CAST(NULLIF(TRIM(CAST(hours_missed AS STRING)), '') AS DOUBLE) AS hours_missed,
      NULLIF(TRIM(CAST(scheduled_shift_code AS STRING)), '') AS scheduled_shift_code,
      _ingest_ts,
      _source_path,
      _record_origin
    FROM LIVE.bronze_absences""",
    'staffing_requirements': """SELECT
      NULLIF(TRIM(CAST(department_id AS STRING)), '') AS department_id,
      TRY_CAST(NULLIF(TRIM(CAST(requirement_date AS STRING)), '') AS DATE) AS requirement_date,
      NULLIF(TRIM(CAST(shift_code AS STRING)), '') AS shift_code,
      TRY_CAST(NULLIF(TRIM(CAST(required_heads AS STRING)), '') AS INTEGER) AS required_heads,
      TRY_CAST(NULLIF(TRIM(CAST(required_hours AS STRING)), '') AS DOUBLE) AS required_hours,
      _ingest_ts,
      _source_path,
      _record_origin
    FROM LIVE.bronze_staffing_requirements""",
    'census_proxy': """SELECT
      NULLIF(TRIM(CAST(department_id AS STRING)), '') AS department_id,
      TRY_CAST(NULLIF(TRIM(CAST(census_date AS STRING)), '') AS DATE) AS census_date,
      TRY_CAST(NULLIF(TRIM(CAST(demand_index AS STRING)), '') AS DOUBLE) AS demand_index,
      TRY_CAST(NULLIF(TRIM(CAST(flu_season_flag AS STRING)), '') AS INTEGER) AS flu_season_flag,
      _ingest_ts,
      _source_path,
      _record_origin
    FROM LIVE.bronze_census_proxy""",
    'open_positions': """SELECT
      NULLIF(TRIM(CAST(position_id AS STRING)), '') AS position_id,
      NULLIF(TRIM(CAST(department_id AS STRING)), '') AS department_id,
      NULLIF(TRIM(CAST(role_code AS STRING)), '') AS role_code,
      TRY_CAST(NULLIF(TRIM(CAST(fte AS STRING)), '') AS DOUBLE) AS fte,
      TRY_CAST(NULLIF(TRIM(CAST(opened_date AS STRING)), '') AS DATE) AS opened_date,
      TRY_CAST(NULLIF(TRIM(CAST(filled_date AS STRING)), '') AS DATE) AS filled_date,
      LOWER(NULLIF(TRIM(CAST(status AS STRING)), '')) AS status,
      _ingest_ts,
      _source_path,
      _record_origin
    FROM LIVE.bronze_open_positions""",
    'attrition_events': """SELECT
      NULLIF(TRIM(CAST(employee_id AS STRING)), '') AS employee_id,
      TRY_CAST(NULLIF(TRIM(CAST(separation_date AS STRING)), '') AS DATE) AS separation_date,
      LOWER(NULLIF(TRIM(CAST(separation_type AS STRING)), '')) AS separation_type,
      LOWER(NULLIF(TRIM(CAST(destination AS STRING)), '')) AS destination,
      _ingest_ts,
      _source_path,
      _record_origin
    FROM LIVE.bronze_attrition_events""",
}

ROW_EXPECTS: dict[str, dict[str, str]] = {
    'employees': {
        'emp_required_fields': 'employee_id IS NOT NULL AND role_code IS NOT NULL AND department_id IS NOT NULL AND hire_date IS NOT NULL AND fte IS NOT NULL AND employment_status IS NOT NULL',
        'emp_valid_hire_date': "hire_date IS NOT NULL AND hire_date <= DATE '2026-09-01'",
        'emp_valid_termination': 'termination_date IS NULL OR hire_date IS NULL OR termination_date >= hire_date',
        'emp_status_values': "employment_status IN ('active', 'terminated')",
        'emp_fte_bounds': 'fte >= 0.6 AND fte <= 1.0',
    },
    'schedule_assignments': {
        'sch_valid_date': "shift_date IS NOT NULL AND shift_date >= DATE '2025-09-01' AND shift_date <= DATE '2026-09-01'",
    },
    'time_cards': {
        'tc_hours_bounds': 'hours_worked >= 0 AND hours_worked <= 24',
        'tc_overtime_consistent': 'overtime_hours >= 0 AND overtime_hours <= hours_worked',
    },
    'absences': {
        'abs_type_values': "absence_type IN ('unplanned_callout', 'pto')",
    },
    'staffing_requirements': {
        'staff_heads_bounds': 'required_heads >= 1 AND required_heads <= 40',
        'staff_valid_date': "requirement_date IS NOT NULL AND requirement_date >= DATE '2025-09-01' AND requirement_date <= DATE '2026-09-01'",
    },
    'attrition_events': {
        'attr_type_values': "separation_type IN ('voluntary', 'involuntary')",
    },
}


def _register_silver(table_name: str) -> None:
    query = STAGING_SQL[table_name]
    expects = ROW_EXPECTS.get(table_name, {})

    def _load(_q: str = query):
        return spark.sql(_q)  # noqa: F821

    _load.__name__ = f"silver_{table_name}"
    if expects:
        _load = dlt.expect_all_or_drop(expects)(_load)
    dlt.table(
        name=f"silver_{table_name}",
        comment=f"Typed {table_name}; per-row expects share local rule IDs",
    )(_load)


for _table in STAGING_SQL:
    _register_silver(_table)
