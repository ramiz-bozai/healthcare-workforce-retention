"""Gold table grains and columns. Predictions are Increment 4 — not here."""

from __future__ import annotations

GOLD_TABLES = (
    "snapshot_calendar",
    "role_cost_assumptions",
    "metric_catalog",
    "unit_day_coverage",
    "unit_week_features",
    "employee_month_features",
    "executive_kpis",
)

EMPLOYEE_MONTH_COLUMNS = (
    "employee_id",
    "snapshot_date",
    "is_inference_snapshot",
    "role_code",
    "department_id",
    "facility_id",
    "primary_shift_code",
    "compensation_band",
    "band_rank",
    "fte",
    "tenure_months",
    "tenure_band",
    "manager_span",
    "unit_vacancy_rate",
    "open_fte_in_unit",
    "ot_hours_30d",
    "ot_hours_90d",
    "extra_shift_count_30d",
    "swap_count_90d",
    "nights_share_90d",
    "unplanned_absence_hours_90d",
    "unplanned_absence_rate_90d",
    "label_voluntary_90d",
    "label_window_complete",
)

UNIT_DAY_COLUMNS = (
    "department_id",
    "coverage_date",
    "required_heads",
    "required_hours",
    "assigned_heads",
    "assigned_hours",
    "productive_hours",
    "overtime_hours",
    "unplanned_absence_hours",
    "open_heads",
    "open_shift_share",
    "coverage_ratio",
    "demand_index",
    "flu_season_flag",
    "is_shortage_day",
)

UNIT_WEEK_COLUMNS = (
    "department_id",
    "week_start",
    "week_end",
    "avg_coverage_ratio",
    "avg_open_shift_share",
    "overtime_hours",
    "unplanned_absence_hours",
    "avg_demand_index",
    "shortage_day_count",
    "is_shortage_week",
    "label_shortage_next_14d",
    "label_shortage_next_28d",
    "label_window_complete_14d",
    "label_window_complete_28d",
)

EXEC_KPI_COLUMNS = (
    "as_of_date",
    "active_headcount",
    "open_fte",
    "vacancy_rate",
    "overtime_hours_30d",
    "unplanned_absence_hours_30d",
    "unplanned_absence_rate_30d",
    "coverage_ratio_7d",
    "trailing_coverage_gap_hours_14d",
    "observed_voluntary_exits_90d",
    "observed_attrition_rate_90d",
    "planning_open_salary_exposure_usd",
    "planning_overtime_agency_usd_30d",
    "assumption_note",
)
