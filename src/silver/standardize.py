"""Cast bronze VARCHAR into typed silver staging tables.

CAST / TRY_CAST / NULLIF / TRIM are used so the same expressions can move to Spark SQL.
"""

from __future__ import annotations

from data_generation.schema import TABLE_COLUMNS

DATE_COLUMNS = {
    "employees": ("hire_date", "termination_date"),
    "schedule_assignments": ("shift_date",),
    "time_cards": ("work_date",),
    "absences": ("absence_date",),
    "staffing_requirements": ("requirement_date",),
    "census_proxy": ("census_date",),
    "open_positions": ("opened_date", "filled_date"),
    "attrition_events": ("separation_date",),
}

DOUBLE_COLUMNS = {
    "employees": ("fte",),
    "departments": ("vacancy_rate",),
    "role_cost_assumptions": (
        "avg_annual_salary_usd",
        "hourly_equivalent_usd",
        "replacement_multiplier",
        "agency_hourly_usd",
    ),
    "schedule_assignments": ("scheduled_hours",),
    "time_cards": ("hours_worked", "overtime_hours"),
    "absences": ("hours_missed",),
    "staffing_requirements": ("required_hours",),
    "census_proxy": ("demand_index",),
    "open_positions": ("fte",),
    "shifts": ("scheduled_hours",),
}

INT_COLUMNS = {
    "departments": ("target_headcount",),
    "compensation_bands": ("band_rank",),
    "role_cost_assumptions": ("hours_per_year",),
    "schedule_assignments": ("is_extra_shift", "is_swap"),
    "staffing_requirements": ("required_heads",),
    "census_proxy": ("flu_season_flag",),
}

LOWER_COLUMNS = {
    "employees": ("employment_status",),
    "absences": ("absence_type",),
    "attrition_events": ("separation_type", "destination"),
    "open_positions": ("status",),
}


def _expr(table: str, col: str) -> str:
    raw = f"NULLIF(TRIM(CAST({col} AS VARCHAR)), '')"
    if col in DATE_COLUMNS.get(table, ()):
        return f"TRY_CAST({raw} AS DATE) AS {col}"
    if col in DOUBLE_COLUMNS.get(table, ()):
        return f"TRY_CAST({raw} AS DOUBLE) AS {col}"
    if col in INT_COLUMNS.get(table, ()):
        return f"TRY_CAST({raw} AS INTEGER) AS {col}"
    if col in LOWER_COLUMNS.get(table, ()):
        return f"LOWER({raw}) AS {col}"
    return f"{raw} AS {col}"


def staging_sql(table: str) -> str:
    payload = ",\n      ".join(_expr(table, col) for col in TABLE_COLUMNS[table])
    return f"""
    CREATE OR REPLACE TABLE silver.stg_{table} AS
    SELECT
      {payload},
      _ingest_ts,
      _source_path,
      _record_origin
    FROM bronze.{table}
    """


def all_staging_sql() -> list[tuple[str, str]]:
    return [(table, staging_sql(table)) for table in TABLE_COLUMNS]
