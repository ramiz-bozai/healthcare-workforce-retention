"""Static healthcare-ops vocabularies. Fictional facilities, real job-code language."""

from __future__ import annotations

FIRST_NAMES: tuple[str, ...] = (
    "Alex", "Jordan", "Taylor", "Casey", "Riley", "Avery", "Quinn", "Morgan",
    "Jamie", "Cameron", "Drew", "Skyler", "Reese", "Parker", "Rowan", "Sage",
    "Emerson", "Finley", "Hayden", "Kendall", "Logan", "Micah", "Noah", "Pat",
    "Sam", "Shawn", "Terry", "Tracy", "Robin", "Lee", "Dana", "Blair",
    "Chris", "Devon", "Ellis", "Frankie", "Gray", "Harper", "Indigo", "Jules",
    "Kai", "Lane", "Marley", "Nico", "Oakley", "Peyton", "Remy", "Shay",
    "Tatum", "Val", "Winter", "Zion", "Amari", "Blake", "Corey", "Dallas",
)

ROLES: tuple[dict[str, str], ...] = (
    {"role_code": "RN", "role_name": "Registered Nurse", "job_family": "Nursing"},
    {"role_code": "LPN", "role_name": "Licensed Practical Nurse", "job_family": "Nursing"},
    {"role_code": "CNA", "role_name": "Certified Nursing Assistant", "job_family": "Nursing"},
    {"role_code": "RT", "role_name": "Respiratory Therapist", "job_family": "Allied Health"},
    {"role_code": "ED_TECH", "role_name": "Emergency Department Technician", "job_family": "Allied Health"},
)

SHIFTS: tuple[dict[str, object], ...] = (
    {"shift_code": "DAYS", "shift_name": "Days (07-19)", "scheduled_hours": 12},
    {"shift_code": "EVENINGS", "shift_name": "Evenings (15-23)", "scheduled_hours": 8},
    {"shift_code": "NIGHTS", "shift_name": "Nights (19-07)", "scheduled_hours": 12},
)

BANDS: tuple[str, ...] = ("B1", "B2", "B3")

FACILITIES: tuple[dict[str, str], ...] = (
    {"facility_id": "NSH", "facility_name": "Northshore General Hospital", "facility_type": "acute_care", "min_profile": "seed"},
    {"facility_id": "CVM", "facility_name": "Cedar Valley Medical Center", "facility_type": "acute_care", "min_profile": "seed"},
    {"facility_id": "HVR", "facility_name": "Harborview Regional", "facility_type": "acute_care", "min_profile": "demo"},
)

# unit_type drives role mix and required heads. profiles: seed uses first 8.
DEPARTMENTS: tuple[dict[str, object], ...] = (
    {"department_id": "NSH-MS-4W", "facility_id": "NSH", "department_name": "Med-Surg 4 West", "service_line": "Med-Surg", "unit_type": "med_surg", "weight": 32, "min_profile": "seed"},
    {"department_id": "NSH-ICU", "facility_id": "NSH", "department_name": "Intensive Care Unit", "service_line": "Critical Care", "unit_type": "icu", "weight": 28, "min_profile": "seed"},
    {"department_id": "NSH-ED", "facility_id": "NSH", "department_name": "Emergency Department", "service_line": "Emergency", "unit_type": "ed", "weight": 36, "min_profile": "seed"},
    {"department_id": "NSH-TELE", "facility_id": "NSH", "department_name": "Telemetry", "service_line": "Med-Surg", "unit_type": "telemetry", "weight": 24, "min_profile": "seed"},
    {"department_id": "CVM-MS-3E", "facility_id": "CVM", "department_name": "Med-Surg 3 East", "service_line": "Med-Surg", "unit_type": "med_surg", "weight": 32, "min_profile": "seed"},
    {"department_id": "CVM-ICU", "facility_id": "CVM", "department_name": "Intensive Care Unit", "service_line": "Critical Care", "unit_type": "icu", "weight": 28, "min_profile": "seed"},
    {"department_id": "CVM-LD", "facility_id": "CVM", "department_name": "Labor and Delivery", "service_line": "Women's Health", "unit_type": "ld", "weight": 20, "min_profile": "seed"},
    {"department_id": "CVM-OR", "facility_id": "CVM", "department_name": "Operating Room", "service_line": "Perioperative", "unit_type": "or", "weight": 18, "min_profile": "seed"},
    {"department_id": "NSH-PACU", "facility_id": "NSH", "department_name": "PACU", "service_line": "Perioperative", "unit_type": "pacu", "weight": 14, "min_profile": "demo"},
    {"department_id": "CVM-PACU", "facility_id": "CVM", "department_name": "PACU", "service_line": "Perioperative", "unit_type": "pacu", "weight": 14, "min_profile": "demo"},
    {"department_id": "HVR-MS-2N", "facility_id": "HVR", "department_name": "Med-Surg 2 North", "service_line": "Med-Surg", "unit_type": "med_surg", "weight": 30, "min_profile": "demo"},
    {"department_id": "HVR-ICU", "facility_id": "HVR", "department_name": "Intensive Care Unit", "service_line": "Critical Care", "unit_type": "icu", "weight": 26, "min_profile": "demo"},
)

# Role mix by unit type. Must sum to 1.0. Managers are always RN and count in RN share.
ROLE_MIX: dict[str, dict[str, float]] = {
    "med_surg": {"RN": 0.50, "LPN": 0.15, "CNA": 0.35, "RT": 0.00, "ED_TECH": 0.00},
    "icu": {"RN": 0.70, "LPN": 0.00, "CNA": 0.15, "RT": 0.15, "ED_TECH": 0.00},
    "ed": {"RN": 0.55, "LPN": 0.00, "CNA": 0.10, "RT": 0.10, "ED_TECH": 0.25},
    "telemetry": {"RN": 0.55, "LPN": 0.15, "CNA": 0.30, "RT": 0.00, "ED_TECH": 0.00},
    "ld": {"RN": 0.80, "LPN": 0.10, "CNA": 0.10, "RT": 0.00, "ED_TECH": 0.00},
    "or": {"RN": 0.85, "LPN": 0.00, "CNA": 0.15, "RT": 0.00, "ED_TECH": 0.00},
    "pacu": {"RN": 0.80, "LPN": 0.00, "CNA": 0.20, "RT": 0.00, "ED_TECH": 0.00},
}

# Baseline required heads per shift at demand_index = 1.0 (planning, not a clinical standard).
# Sized for ~3x12 staffing so coverage sits near 0.8–1.0 on a 180-person seed,
# not a 0.4 catastrophe that a CNO would reject as fake.
BASE_REQUIRED_HEADS: dict[str, dict[str, int]] = {
    "med_surg": {"DAYS": 3, "EVENINGS": 2, "NIGHTS": 3},
    "icu": {"DAYS": 4, "EVENINGS": 3, "NIGHTS": 4},
    "ed": {"DAYS": 4, "EVENINGS": 4, "NIGHTS": 4},
    "telemetry": {"DAYS": 3, "EVENINGS": 2, "NIGHTS": 2},
    "ld": {"DAYS": 3, "EVENINGS": 2, "NIGHTS": 2},
    "or": {"DAYS": 3, "EVENINGS": 2, "NIGHTS": 1},
    "pacu": {"DAYS": 2, "EVENINGS": 1, "NIGHTS": 1},
}

SHIFT_HOURS = {s["shift_code"]: int(s["scheduled_hours"]) for s in SHIFTS}

FLU_MONTHS = frozenset({12, 1, 2, 3})


def departments_for_profile(profile: str) -> list[dict[str, object]]:
    if profile == "demo":
        return [dict(d) for d in DEPARTMENTS]
    return [dict(d) for d in DEPARTMENTS if d["min_profile"] == "seed"]


def facilities_for_profile(profile: str) -> list[dict[str, str]]:
    if profile == "demo":
        return [dict(f) for f in FACILITIES]
    return [dict(f) for f in FACILITIES if f["min_profile"] == "seed"]
