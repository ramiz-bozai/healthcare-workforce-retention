"""Display helpers. Formatting only — no new KPIs."""

from __future__ import annotations

import re

from src.ai.validate import format_value

DISCLAIMER = (
    "Synthetic planning workbench. Ask uses the attached Genie space when "
    "GENIE_SPACE_ID is set; otherwise allowlisted template tools. Not Model Serving. "
    "Actions stay pending_human_review and are not applied. "
    "Dollars are role-average planning assumptions, not measured savings."
)

ATTRITION_DISPLAY_COLS = (
    "risk_rank",
    "display_name",
    "employee_id",
    "role_code",
    "department_id",
    "facility_id",
    "p_voluntary_90d",
    "high_risk_flag",
    "drivers",
    "planning_replacement_usd",
)

SHORTAGE_DISPLAY_COLS = (
    "shortage_rank",
    "department_id",
    "week_end",
    "p_shortage_14d",
    "predicted_shortage_flag",
    "avg_coverage_ratio",
    "avg_open_shift_share",
    "trailing_gap_hours_14d",
    "planning_coverage_exposure_usd",
    "drivers",
)

ACTION_DISPLAY_COLS = (
    "action_id",
    "playbook_action",
    "subject_type",
    "display_name",
    "department_id",
    "baseline_p",
    "scenario_p",
    "planning_delta_usd",
    "scored",
    "status",
    "applied",
)

WHATIF_DISPLAY_COLS = (
    "scenario_id",
    "playbook_action",
    "n_employees",
    "n_units",
    "mean_p_attrition",
    "high_risk_headcount",
    "planning_attrition_exposure_usd",
    "planning_attrition_delta_usd",
    "flagged_units",
    "planning_coverage_exposure_usd",
    "planning_coverage_delta_usd",
)

FORBIDDEN_DISPLAY_RE = re.compile(
    r"(^|_)(age|sex|gender|race|ethnicity|ssn|zip|disability|religion)(_|$)",
    re.I,
)


def driver_name(raw: object) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    return text.split("=", 1)[0].strip()


def driver_names(*parts: object) -> str:
    names = [driver_name(part) for part in parts]
    return " / ".join(name for name in names if name)


def cite_value(table: str, column: str, value: object) -> str:
    return format_value(f"{table}.{column}", value)


def assert_display_columns_safe(columns: tuple[str, ...] | list[str]) -> None:
    for col in columns:
        assert not FORBIDDEN_DISPLAY_RE.search(col), col
