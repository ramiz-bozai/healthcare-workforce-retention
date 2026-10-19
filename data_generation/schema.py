"""Published table contracts for synthetic workforce data.

Gold/ML layers are not generated here. Latent generation traits never appear
in these columns so they cannot leak into training.
"""

from __future__ import annotations

# Substrings that must never appear as column names (protected class, PHI, PII extras).
FORBIDDEN_COLUMN_SUBSTRINGS = (
    "ssn",
    "social_security",
    "dob",
    "date_of_birth",
    "birth",
    "gender",
    "sex",
    "race",
    "ethnic",
    "religion",
    "disability",
    "veteran",
    "marital",
    "pregnancy",
    "zip",
    "address",
    "phone",
    "email",
    "mrn",
    "diagnosis",
    "icd",
    "npi",
    "patient",
    "salary",  # individual pay; role averages live only on role_cost_assumptions
    "wage",
    "pay_rate",
)

# role_cost_assumptions is the only table allowed to contain salary assumptions.
SALARY_TABLE = "role_cost_assumptions"

TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "facilities": (
        "facility_id",
        "facility_name",
        "facility_type",
    ),
    "departments": (
        "department_id",
        "facility_id",
        "department_name",
        "service_line",
        "unit_type",
        "target_headcount",
        "vacancy_rate",
    ),
    "roles": (
        "role_code",
        "role_name",
        "job_family",
    ),
    "shifts": (
        "shift_code",
        "shift_name",
        "scheduled_hours",
    ),
    "compensation_bands": (
        "role_code",
        "band_code",
        "band_rank",
    ),
    "role_cost_assumptions": (
        "role_code",
        "avg_annual_salary_usd",
        "hours_per_year",
        "hourly_equivalent_usd",
        "replacement_multiplier",
        "agency_hourly_usd",
        "assumption_note",
    ),
    "employees": (
        "employee_id",
        "first_name",
        "last_initial",
        "display_name",
        "role_code",
        "department_id",
        "facility_id",
        "manager_employee_id",
        "hire_date",
        "fte",
        "primary_shift_code",
        "compensation_band",
        "employment_status",
        "termination_date",
    ),
    "schedule_assignments": (
        "assignment_id",
        "employee_id",
        "department_id",
        "shift_date",
        "shift_code",
        "scheduled_hours",
        "is_extra_shift",
        "is_swap",
    ),
    "time_cards": (
        "time_card_id",
        "employee_id",
        "department_id",
        "work_date",
        "shift_code",
        "hours_worked",
        "overtime_hours",
    ),
    "absences": (
        "absence_id",
        "employee_id",
        "department_id",
        "absence_date",
        "absence_type",
        "hours_missed",
        "scheduled_shift_code",
    ),
    "staffing_requirements": (
        "department_id",
        "requirement_date",
        "shift_code",
        "required_heads",
        "required_hours",
    ),
    "census_proxy": (
        "department_id",
        "census_date",
        "demand_index",
        "flu_season_flag",
    ),
    "open_positions": (
        "position_id",
        "department_id",
        "role_code",
        "fte",
        "opened_date",
        "filled_date",
        "status",
    ),
    "attrition_events": (
        "employee_id",
        "separation_date",
        "separation_type",
        "destination",
    ),
}

TABLE_ORDER = tuple(TABLE_COLUMNS.keys())

DISPLAY_NAME_PATTERN = r"^[A-Za-z]+ [A-Z]\.$"
EMPLOYEE_ID_PATTERN = r"^EMP-\d{6}$"
