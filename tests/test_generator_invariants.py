from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from data_generation.config import load_config
from data_generation.engine import generate_tables, voluntary_90d_probability
from data_generation.io import write_tables
from data_generation.schema import (
    DISPLAY_NAME_PATTERN,
    EMPLOYEE_ID_PATTERN,
    FORBIDDEN_COLUMN_SUBSTRINGS,
    SALARY_TABLE,
    TABLE_COLUMNS,
)

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data" / "seed"


def test_output_columns_match_contract(seed_tables):
    assert set(seed_tables) == set(TABLE_COLUMNS)
    for name, cols in TABLE_COLUMNS.items():
        assert tuple(seed_tables[name].columns) == cols


def test_no_protected_or_phi_columns(seed_tables):
    for name, df in seed_tables.items():
        for col in df.columns:
            lowered = col.lower()
            if name == SALARY_TABLE and col == "avg_annual_salary_usd":
                continue
            if name == SALARY_TABLE and col == "hourly_equivalent_usd":
                continue
            if name == SALARY_TABLE and col == "agency_hourly_usd":
                continue
            for token in FORBIDDEN_COLUMN_SUBSTRINGS:
                assert token not in lowered, f"{name}.{col} contains forbidden token {token!r}"


def test_salary_assumptions_only_on_role_table(seed_tables):
    for name, df in seed_tables.items():
        if name == SALARY_TABLE:
            continue
        for col in df.columns:
            assert "salary" not in col.lower()
            assert "wage" not in col.lower()
            assert "pay_rate" not in col.lower()


def test_seed_active_headcount_and_ids(seed_tables, seed_cfg):
    emp = seed_tables["employees"]
    active = emp[emp["employment_status"] == "active"]
    assert len(active) == seed_cfg.n_active_employees
    assert emp["employee_id"].is_unique
    assert emp["employee_id"].str.fullmatch(EMPLOYEE_ID_PATTERN).all()
    assert emp["display_name"].str.fullmatch(DISPLAY_NAME_PATTERN).all()
    assert emp["last_initial"].str.fullmatch(r"[A-Z]").all()
    assert emp["fte"].between(0.6, 1.0).all()
    assert set(emp["role_code"]) <= {"RN", "LPN", "CNA", "RT", "ED_TECH"}
    assert set(emp["primary_shift_code"]) <= {"DAYS", "EVENINGS", "NIGHTS"}
    assert set(emp["employment_status"]) <= {"active", "terminated"}


def test_referential_integrity(seed_tables):
    emp = seed_tables["employees"]
    dept_ids = set(seed_tables["departments"]["department_id"])
    fac_ids = set(seed_tables["facilities"]["facility_id"])
    role_ids = set(seed_tables["roles"]["role_code"])
    emp_ids = set(emp["employee_id"])
    assert set(emp["department_id"]) <= dept_ids
    assert set(emp["facility_id"]) <= fac_ids
    assert set(emp["role_code"]) <= role_ids
    managers = emp["manager_employee_id"].dropna()
    assert set(managers) <= emp_ids
    assert emp.loc[emp["employee_id"].isin(managers), "role_code"].eq("RN").all()

    for table, fk in (
        ("schedule_assignments", "employee_id"),
        ("time_cards", "employee_id"),
        ("absences", "employee_id"),
        ("attrition_events", "employee_id"),
    ):
        assert set(seed_tables[table][fk]) <= emp_ids

    for table, fk in (
        ("schedule_assignments", "department_id"),
        ("time_cards", "department_id"),
        ("absences", "department_id"),
        ("staffing_requirements", "department_id"),
        ("census_proxy", "department_id"),
        ("open_positions", "department_id"),
    ):
        assert set(seed_tables[table][fk]) <= dept_ids


def test_dates_are_coherent(seed_tables, seed_cfg):
    emp = seed_tables["employees"].copy()
    emp["hire_date"] = pd.to_datetime(emp["hire_date"])
    emp["termination_date"] = pd.to_datetime(emp["termination_date"])
    terminated = emp[emp["employment_status"] == "terminated"]
    assert terminated["termination_date"].notna().all()
    assert (terminated["termination_date"] >= terminated["hire_date"]).all()
    assert (terminated["termination_date"] <= pd.Timestamp(seed_cfg.as_of_date)).all()
    active = emp[emp["employment_status"] == "active"]
    assert active["termination_date"].isna().all()

    events = seed_tables["attrition_events"].copy()
    events["separation_date"] = pd.to_datetime(events["separation_date"])
    assert set(events["separation_type"]) <= {"voluntary", "involuntary"}
    assert events["separation_date"].max() <= pd.Timestamp(seed_cfg.future_end)
    assert events["separation_date"].min() >= pd.Timestamp(seed_cfg.history_start) - pd.Timedelta(days=0)

    sch = pd.to_datetime(seed_tables["schedule_assignments"]["shift_date"])
    assert sch.min() >= pd.Timestamp(seed_cfg.history_start)
    assert sch.max() <= pd.Timestamp(seed_cfg.as_of_date)


def test_staffing_values_are_plausible(seed_tables):
    req = seed_tables["staffing_requirements"]
    assert req["required_heads"].between(1, 40).all()
    assert (req["required_hours"] > 0).all()
    census = seed_tables["census_proxy"]
    assert census["demand_index"].between(0.9, 1.25).all()
    assert set(census["flu_season_flag"]) <= {0, 1}


def test_no_duplicate_schedule_or_time_cards(seed_tables):
    sch = seed_tables["schedule_assignments"]
    dup = sch.duplicated(["employee_id", "shift_date", "shift_code"])
    assert not dup.any()
    tc = seed_tables["time_cards"]
    assert not tc.duplicated(["employee_id", "work_date"]).any()


def test_deterministic_regeneration(seed_cfg, tmp_path):
    a = generate_tables(seed_cfg)
    b = generate_tables(seed_cfg)
    for name in TABLE_COLUMNS:
        pd.testing.assert_frame_equal(a[name], b[name], check_dtype=False)
    write_tables(a, tmp_path / "a", seed_cfg)
    write_tables(b, tmp_path / "b", seed_cfg)
    for name in TABLE_COLUMNS:
        left = (tmp_path / "a" / f"{name}.csv").read_text()
        right = (tmp_path / "b" / f"{name}.csv").read_text()
        assert left == right


def test_committed_seed_matches_generator(tmp_path):
    assert SEED_DIR.joinpath("manifest.json").exists(), (
        "Committed seed is missing. Run: uv run python -m data_generation --profile seed"
    )
    cfg = load_config("seed")
    write_tables(generate_tables(cfg), tmp_path, cfg)
    for name in TABLE_COLUMNS:
        got = (tmp_path / f"{name}.csv").read_text()
        committed = (SEED_DIR / f"{name}.csv").read_text()
        assert got == committed, f"Committed {name}.csv drifted from generator"
    manifest = json.loads(SEED_DIR.joinpath("manifest.json").read_text())
    assert manifest["random_seed"] == 42
    assert manifest["as_of_date"] == "2026-09-01"
    assert manifest["contains_phi"] is False


def test_injected_attrition_drivers_are_visible(seed_tables):
    """Leavers in the next 90 days should have higher OT than stayers — the demo story."""
    emp = seed_tables["employees"]
    events = seed_tables["attrition_events"]
    tc = seed_tables["time_cards"]
    active_ids = set(emp.loc[emp["employment_status"] == "active", "employee_id"])
    future_vol = set(
        events.loc[
            (events["separation_type"] == "voluntary")
            & (pd.to_datetime(events["separation_date"]) > pd.Timestamp("2026-09-01")),
            "employee_id",
        ]
    )
    ot = tc.groupby("employee_id")["overtime_hours"].sum()
    leaver_ot = ot.reindex(list(future_vol & active_ids)).fillna(0)
    stayer_ids = active_ids - future_vol
    stayer_ot = ot.reindex(list(stayer_ids)).fillna(0)
    assert len(leaver_ot) >= 5
    assert leaver_ot.mean() > stayer_ot.mean()


def test_probability_function_monotone_in_overtime():
    low = voluntary_90d_probability(0.1, 0.1, 0.1, False, 48, 0.05, 8)
    high = voluntary_90d_probability(0.9, 0.1, 0.1, False, 48, 0.05, 8)
    nights = voluntary_90d_probability(0.1, 0.1, 0.1, True, 48, 0.05, 8)
    short = voluntary_90d_probability(0.1, 0.1, 0.1, False, 6, 0.05, 8)
    assert high > low
    assert nights > low
    assert short > low


def test_display_name_pattern_unit():
    assert re.fullmatch(DISPLAY_NAME_PATTERN, "Jordan M.")
    assert not re.fullmatch(DISPLAY_NAME_PATTERN, "Jordan Moore")
