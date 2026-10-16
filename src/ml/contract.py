"""Model feature contracts. Labels, IDs, and dollars are never features."""

from __future__ import annotations

from data_generation.schema import FORBIDDEN_COLUMN_SUBSTRINGS

ATTRITION_NUMERIC = (
    "fte",
    "tenure_months",
    "band_rank",
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
)
ATTRITION_CATEGORICAL = (
    "role_code",
    "department_id",
    "facility_id",
    "primary_shift_code",
    "compensation_band",
    "tenure_band",
)
ATTRITION_TARGET = "label_voluntary_90d"
ATTRITION_FAIRNESS_SLICES = ("role_code", "facility_id", "tenure_band", "primary_shift_code")

SHORTAGE_NUMERIC = (
    "avg_coverage_ratio",
    "avg_open_shift_share",
    "overtime_hours",
    "unplanned_absence_hours",
    "avg_demand_index",
    "shortage_day_count",
    "is_shortage_week",
)
SHORTAGE_CATEGORICAL = ("department_id",)
SHORTAGE_TARGET = "label_shortage_next_14d"
SHORTAGE_FAIRNESS_SLICES = ("department_id",)

ID_OR_LABEL_COLUMNS = frozenset(
    {
        "employee_id",
        "snapshot_date",
        "is_inference_snapshot",
        "label_voluntary_90d",
        "label_window_complete",
        "week_start",
        "week_end",
        "label_shortage_next_14d",
        "label_shortage_next_28d",
        "label_window_complete_14d",
        "label_window_complete_28d",
        "display_name",
        "avg_annual_salary_usd",
        "hourly_equivalent_usd",
        "agency_hourly_usd",
        "planning_replacement_usd",
    }
)

MODEL_CATALOG_ROWS = (
    (
        "predicted_attrition_rate_90d",
        "exec_brief",
        "as_of",
        "Mean calibrated P(voluntary 90d) over employees active at as_of",
        1,
    ),
    (
        "high_risk_headcount",
        "exec_brief",
        "as_of",
        "Count of active employees in the top planning quantile by calibrated P(voluntary 90d)",
        1,
    ),
    (
        "planning_attrition_exposure_usd",
        "exec_brief",
        "as_of",
        "Sum of role-average salary * replacement multiplier for high-risk employees. Planning assumption, not savings.",
        1,
    ),
    (
        "predicted_shortage_units_14d",
        "exec_brief",
        "as_of",
        "Units whose latest week has calibrated P(shortage in next 14d) at or above the policy threshold",
        1,
    ),
    (
        "planning_coverage_exposure_usd",
        "exec_brief",
        "as_of",
        "Flagged units' trailing 14d hour gap * mean agency hourly. Planning assumption, not savings.",
        1,
    ),
)


def assert_feature_safety(columns: tuple[str, ...]) -> None:
    for col in columns:
        lowered = col.lower()
        assert col not in ID_OR_LABEL_COLUMNS, col
        for token in FORBIDDEN_COLUMN_SUBSTRINGS:
            if token in ("salary", "wage", "pay_rate") and col in {
                "planning_open_salary_exposure_usd",
                "planning_attrition_exposure_usd",
            }:
                continue
            assert token not in lowered, col
