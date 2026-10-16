"""Deterministic synthetic workforce generator.

Causal graph (injected, documented — this is not a claim about a real health system):

    ot_propensity, schedule_churn, unplanned absence, nights, short tenure,
    unit vacancy, manager span
        -> higher P(voluntary separation in 90 days)

    flu-season demand, unit vacancy, absences, extra shifts
        -> lower coverage (used later in gold)

Latent propensities are NOT written to output tables (leakage guard).
No protected characteristics are generated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from data_generation.catalogs import (
    BANDS,
    BASE_REQUIRED_HEADS,
    FIRST_NAMES,
    FLU_MONTHS,
    ROLE_MIX,
    ROLES,
    SHIFT_HOURS,
    SHIFTS,
    departments_for_profile,
    facilities_for_profile,
)
from data_generation.config import GenerationConfig
from data_generation.schema import TABLE_COLUMNS

FTE_VALUES = np.array([1.0, 0.9, 0.75, 0.6])
FTE_PROBS = np.array([0.70, 0.15, 0.10, 0.05])
SHIFT_CODES = np.array(["DAYS", "NIGHTS", "EVENINGS"])
SHIFT_PROBS = np.array([0.50, 0.35, 0.15])
ABSENCE_TYPES_UNPLANNED = "unplanned_callout"
ABSENCE_TYPE_PTO = "pto"


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))


def voluntary_90d_probability(
    ot: float,
    churn: float,
    absence: float,
    is_nights: bool,
    tenure_months: float,
    vacancy: float,
    span: float,
) -> float:
    """90-day voluntary separation probability. Baseline ~3% so a 180-person seed is stressed, not collapsing."""
    logit = -3.7
    logit += 1.15 * ot
    logit += 0.9 * churn
    logit += 0.45 * absence
    logit += 0.55 * (1.0 if is_nights else 0.0)
    logit += 0.9 * max(0.0, (18.0 - tenure_months) / 18.0)
    logit += 0.9 * vacancy
    logit += 0.3 * min(span / 18.0, 1.6)
    return float(_sigmoid(logit))


def demand_index(d: date) -> float:
    flu = 1.0 if d.month in FLU_MONTHS else 0.0
    doy = d.timetuple().tm_yday
    wave = 0.04 * np.sin(2.0 * np.pi * doy / 365.25)
    return round(1.0 + 0.12 * flu + float(wave), 4)


def _shifts_per_week(fte: float) -> int:
    if fte >= 0.9:
        return 3
    if fte >= 0.75:
        return 2
    return 2 if fte >= 0.6 else 1


def _hire_date(rng: np.random.Generator, as_of: date, bucket: str) -> date:
    if bucket == "short":
        days = int(rng.integers(45, 18 * 30))
    elif bucket == "mid":
        days = int(rng.integers(18 * 30, 5 * 365))
    else:
        days = int(rng.integers(5 * 365, 15 * 365))
    return as_of - timedelta(days=days)


def _band_for_tenure(rng: np.random.Generator, tenure_months: float) -> str:
    if tenure_months < 18:
        probs = np.array([0.65, 0.30, 0.05])
    elif tenure_months < 60:
        probs = np.array([0.25, 0.55, 0.20])
    else:
        probs = np.array([0.10, 0.40, 0.50])
    return str(rng.choice(np.array(BANDS), p=probs))


def _allocate_roles(n: int, unit_type: str, rng: np.random.Generator) -> list[str]:
    mix = ROLE_MIX[unit_type]
    codes = [c for c, p in mix.items() if p > 0]
    probs = np.array([mix[c] for c in codes], dtype=float)
    probs = probs / probs.sum()
    counts = rng.multinomial(n, probs)
    roles: list[str] = []
    for code, k in zip(codes, counts):
        roles.extend([code] * int(k))
    rng.shuffle(roles)
    if n > 0 and "RN" not in roles:
        roles[0] = "RN"
    return roles


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


@dataclass
class EmployeeDraft:
    employee_id: str
    first_name: str
    last_initial: str
    role_code: str
    department_id: str
    facility_id: str
    hire_date: date
    fte: float
    primary_shift_code: str
    compensation_band: str
    ot: float
    churn: float
    absence: float
    is_historical_leaver: bool
    termination_date: date | None = None
    separation_type: str | None = None
    destination: str | None = None
    manager_employee_id: str | None = None
    is_manager: bool = False


def generate_tables(cfg: GenerationConfig) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(cfg.random_seed)
    depts_meta = departments_for_profile(cfg.profile)
    fac_meta = facilities_for_profile(cfg.profile)
    if len(depts_meta) != cfg.n_units:
        raise ValueError(f"Profile {cfg.profile} expected {cfg.n_units} units, got {len(depts_meta)}")
    if len(fac_meta) != cfg.n_facilities:
        raise ValueError(
            f"Profile {cfg.profile} expected {cfg.n_facilities} facilities, got {len(fac_meta)}"
        )

    tables: dict[str, pd.DataFrame] = {}
    tables["facilities"] = pd.DataFrame(
        [{k: f[k] for k in ("facility_id", "facility_name", "facility_type")} for f in fac_meta]
    )
    tables["roles"] = pd.DataFrame(list(ROLES))
    tables["shifts"] = pd.DataFrame(list(SHIFTS))
    tables["compensation_bands"] = pd.DataFrame(
        [{"role_code": r["role_code"], "band_code": b, "band_rank": i + 1} for r in ROLES for i, b in enumerate(BANDS)]
    )
    hours = cfg.cost.hours_per_year
    tables["role_cost_assumptions"] = pd.DataFrame(
        [
            {
                "role_code": role,
                "avg_annual_salary_usd": salary,
                "hours_per_year": hours,
                "hourly_equivalent_usd": round(salary / hours, 2),
                "replacement_multiplier": cfg.cost.replacement_multiplier,
                "agency_hourly_usd": round((salary / hours) * cfg.cost.agency_to_staff_hourly_ratio, 2),
                "assumption_note": cfg.cost.note,
            }
            for role, salary in cfg.cost.salaries_usd.items()
        ]
    )

    n_active = cfg.n_active_employees
    n_hist = max(8, int(round(0.16 * n_active)))
    weights = np.array([float(d["weight"]) for d in depts_meta], dtype=float)
    weights = weights / weights.sum()
    active_counts = rng.multinomial(n_active, weights)
    hist_counts = rng.multinomial(n_hist, weights)
    # Every unit needs at least one active employee (and therefore an RN manager).
    while (active_counts == 0).any():
        empty = int(np.flatnonzero(active_counts == 0)[0])
        donor = int(np.argmax(active_counts))
        if active_counts[donor] <= 1:
            break
        active_counts[donor] -= 1
        active_counts[empty] += 1

    vacancy: dict[str, float] = {}
    hot = set(rng.choice(np.arange(len(depts_meta)), size=min(2, len(depts_meta)), replace=False).tolist())
    for i, dept in enumerate(depts_meta):
        did = str(dept["department_id"])
        vacancy[did] = float(rng.uniform(0.22, 0.28) if i in hot else rng.uniform(0.05, 0.16))

    drafts: list[EmployeeDraft] = []
    emp_seq = 1
    tenure_buckets = np.array(["short", "mid", "long"])
    bucket_p = np.array([0.25, 0.40, 0.35])

    def _traits(high_risk: bool) -> tuple[float, float, float]:
        ot = float(rng.beta(2.0, 5.0))
        churn = float(rng.beta(2.0, 5.0))
        absence = float(rng.beta(2.0, 6.0))
        if high_risk:
            ot = max(ot, float(rng.uniform(0.65, 0.95)))
            churn = max(churn, float(rng.uniform(0.50, 0.90)))
        return ot, churn, absence

    def _new_person(dept: dict[str, Any], role: str, historical: bool) -> EmployeeDraft:
        nonlocal emp_seq
        eid = f"EMP-{emp_seq:06d}"
        emp_seq += 1
        first = str(FIRST_NAMES[int(rng.integers(0, len(FIRST_NAMES)))])
        last_i = chr(int(rng.integers(65, 91)))
        bucket = str(rng.choice(tenure_buckets, p=bucket_p))
        hire = _hire_date(rng, cfg.as_of_date, bucket)
        if historical:
            hire = min(hire, cfg.history_start - timedelta(days=int(rng.integers(60, 800))))
        tenure_months = (cfg.as_of_date - hire).days / 30.44
        fte = float(rng.choice(FTE_VALUES, p=FTE_PROBS))
        shift = str(rng.choice(SHIFT_CODES, p=SHIFT_PROBS))
        high_risk = bool(rng.random() < 0.08) or historical
        ot, churn, absence = _traits(high_risk)
        return EmployeeDraft(
            employee_id=eid,
            first_name=first,
            last_initial=last_i,
            role_code=role,
            department_id=str(dept["department_id"]),
            facility_id=str(dept["facility_id"]),
            hire_date=hire,
            fte=fte,
            primary_shift_code=shift,
            compensation_band=_band_for_tenure(rng, tenure_months),
            ot=ot,
            churn=churn,
            absence=absence,
            is_historical_leaver=historical,
        )

    for dept, n_a, n_h in zip(depts_meta, active_counts, hist_counts):
        roles_a = _allocate_roles(int(n_a), str(dept["unit_type"]), rng)
        roles_h = _allocate_roles(int(n_h), str(dept["unit_type"]), rng)
        for role in roles_a:
            drafts.append(_new_person(dept, role, historical=False))
        for role in roles_h:
            drafts.append(_new_person(dept, role, historical=True))

    by_dept: dict[str, list[EmployeeDraft]] = {}
    for e in drafts:
        by_dept.setdefault(e.department_id, []).append(e)
    for did, people in by_dept.items():
        rns = [p for p in people if (not p.is_historical_leaver) and p.role_code == "RN"]
        if not rns:
            rns = [p for p in people if not p.is_historical_leaver]
        manager = rns[0]
        manager.is_manager = True
        manager.manager_employee_id = None
        for p in people:
            if p.employee_id != manager.employee_id:
                p.manager_employee_id = manager.employee_id

    span_at_as_of: dict[str, int] = {}
    for e in drafts:
        if e.is_manager:
            span_at_as_of[e.employee_id] = sum(
                1
                for x in drafts
                if x.manager_employee_id == e.employee_id and not x.is_historical_leaver
            )

    for e in drafts:
        vac = vacancy[e.department_id]
        mgr = e.employee_id if e.is_manager else e.manager_employee_id
        span = float(span_at_as_of.get(mgr or "", 8))
        tenure_months = (cfg.as_of_date - e.hire_date).days / 30.44
        is_nights = e.primary_shift_code == "NIGHTS"
        if e.is_historical_leaver:
            window_start = max(e.hire_date + timedelta(days=30), cfg.history_start)
            window_end = cfg.as_of_date - timedelta(days=1)
            if window_end < window_start:
                window_end = window_start
            span_days = (window_end - window_start).days
            offset = int(rng.integers(0, max(span_days, 0) + 1))
            e.termination_date = window_start + timedelta(days=offset)
            if rng.random() < 0.12:
                e.separation_type = "involuntary"
                e.destination = "involuntary_separation"
            else:
                e.separation_type = "voluntary"
                e.destination = "retired" if tenure_months > 120 and rng.random() < 0.25 else "left_health_system"
            continue
        p_vol = voluntary_90d_probability(
            e.ot, e.churn, e.absence, is_nights, tenure_months, vac, span
        )
        if rng.random() < p_vol:
            offset = int(rng.integers(1, cfg.attrition_horizon_days + 1))
            e.termination_date = cfg.as_of_date + timedelta(days=offset)
            e.separation_type = "voluntary"
            e.destination = "left_health_system"
        elif rng.random() < 0.01:
            offset = int(rng.integers(1, cfg.attrition_horizon_days + 1))
            e.termination_date = cfg.as_of_date + timedelta(days=offset)
            e.separation_type = "involuntary"
            e.destination = "involuntary_separation"

    # Future voluntary leavers already work extra / swap more at as_of so the
    # 90-day label is visible in features (same injected graph as historical leavers).
    for e in drafts:
        if (
            not e.is_historical_leaver
            and e.termination_date is not None
            and e.separation_type == "voluntary"
            and e.termination_date > cfg.as_of_date
        ):
            e.ot = max(e.ot, float(rng.uniform(0.70, 0.95)))
            e.churn = max(e.churn, float(rng.uniform(0.55, 0.90)))

    dept_rows = []
    for dept, n_a in zip(depts_meta, active_counts):
        did = str(dept["department_id"])
        dept_rows.append(
            {
                "department_id": did,
                "facility_id": dept["facility_id"],
                "department_name": dept["department_name"],
                "service_line": dept["service_line"],
                "unit_type": dept["unit_type"],
                "target_headcount": int(n_a),
                "vacancy_rate": round(vacancy[did], 4),
            }
        )
    tables["departments"] = pd.DataFrame(dept_rows)

    emp_rows = []
    attr_rows = []
    for e in drafts:
        status = "active"
        term_for_status = e.termination_date
        if term_for_status is not None and term_for_status <= cfg.as_of_date:
            status = "terminated"
        # Future separations stay off the employee snapshot (still active at as_of)
        # and appear only on attrition_events for later label construction.
        snapshot_term = e.termination_date if status == "terminated" else None
        emp_rows.append(
            {
                "employee_id": e.employee_id,
                "first_name": e.first_name,
                "last_initial": e.last_initial,
                "display_name": f"{e.first_name} {e.last_initial}.",
                "role_code": e.role_code,
                "department_id": e.department_id,
                "facility_id": e.facility_id,
                "manager_employee_id": e.manager_employee_id,
                "hire_date": e.hire_date,
                "fte": e.fte,
                "primary_shift_code": e.primary_shift_code,
                "compensation_band": e.compensation_band,
                "employment_status": status,
                "termination_date": snapshot_term,
            }
        )
        if e.termination_date is not None and e.separation_type is not None:
            attr_rows.append(
                {
                    "employee_id": e.employee_id,
                    "separation_date": e.termination_date,
                    "separation_type": e.separation_type,
                    "destination": e.destination,
                }
            )
    tables["employees"] = pd.DataFrame(emp_rows)
    tables["attrition_events"] = pd.DataFrame(attr_rows)

    census_rows = []
    req_rows = []
    for dept in depts_meta:
        did = str(dept["department_id"])
        ut = str(dept["unit_type"])
        for d in _daterange(cfg.history_start, cfg.as_of_date):
            idx = demand_index(d)
            census_rows.append(
                {
                    "department_id": did,
                    "census_date": d,
                    "demand_index": idx,
                    "flu_season_flag": int(d.month in FLU_MONTHS),
                }
            )
            for shift_code, base in BASE_REQUIRED_HEADS[ut].items():
                heads = max(1, int(round(base * idx)))
                req_rows.append(
                    {
                        "department_id": did,
                        "requirement_date": d,
                        "shift_code": shift_code,
                        "required_heads": heads,
                        "required_hours": heads * SHIFT_HOURS[shift_code],
                    }
                )
    tables["census_proxy"] = pd.DataFrame(census_rows)
    tables["staffing_requirements"] = pd.DataFrame(req_rows)

    open_rows = []
    pos_seq = 1
    for dept, n_a in zip(depts_meta, active_counts):
        did = str(dept["department_id"])
        vac = vacancy[did]
        n_open = max(1, int(round(int(n_a) * vac / max(1.0 - vac, 0.05))))
        mix = ROLE_MIX[str(dept["unit_type"])]
        openable = [c for c, p in mix.items() if p > 0]
        open_p = np.array([mix[c] for c in openable], dtype=float)
        open_p = open_p / open_p.sum()
        for _ in range(n_open):
            opened = cfg.as_of_date - timedelta(days=int(rng.integers(14, 180)))
            still_open = rng.random() < 0.75
            filled = None if still_open else opened + timedelta(days=int(rng.integers(10, 90)))
            if filled is not None and filled > cfg.as_of_date:
                filled = None
                still_open = True
            open_rows.append(
                {
                    "position_id": f"REQ-{pos_seq:05d}",
                    "department_id": did,
                    "role_code": str(rng.choice(np.array(openable), p=open_p)),
                    "fte": 1.0,
                    "opened_date": opened,
                    "filled_date": filled,
                    "status": "open" if still_open else "filled",
                }
            )
            pos_seq += 1
    tables["open_positions"] = pd.DataFrame(open_rows)

    sch_rows = []
    tc_rows = []
    abs_rows = []
    sch_seq = 1
    tc_seq = 1
    abs_seq = 1
    other_shifts = {
        "DAYS": ["EVENINGS", "NIGHTS"],
        "EVENINGS": ["DAYS", "NIGHTS"],
        "NIGHTS": ["DAYS", "EVENINGS"],
    }

    for e in drafts:
        last_work = cfg.as_of_date
        if e.termination_date is not None and e.termination_date <= cfg.as_of_date:
            last_work = e.termination_date - timedelta(days=1)
        start = max(cfg.history_start, e.hire_date)
        if last_work < start:
            continue
        vac = vacancy[e.department_id]
        week = _week_start(start)
        last_week = _week_start(last_work)
        pattern_offset = int(rng.integers(0, 7))
        while week <= last_week:
            n_shifts = _shifts_per_week(e.fte)
            extra_p = 0.12 * e.ot * (1.0 + 1.5 * vac)
            extra = 1 if rng.random() < extra_p else 0
            need = n_shifts + extra
            day_idx = [(pattern_offset + i) % 7 for i in range(7)]
            chosen = []
            for idx in day_idx:
                if len(chosen) >= need:
                    break
                chosen.append(idx)
            if extra and len(chosen) < need:
                for idx in range(7):
                    if idx not in chosen:
                        chosen.append(idx)
                    if len(chosen) >= need:
                        break
            for i, idx in enumerate(chosen[:need]):
                d = week + timedelta(days=idx)
                if d < start or d > last_work:
                    continue
                shift = e.primary_shift_code
                is_swap = False
                if rng.random() < (0.06 + 0.40 * e.churn):
                    shift = str(rng.choice(np.array(other_shifts[e.primary_shift_code])))
                    is_swap = True
                hours = SHIFT_HOURS[shift]
                is_extra = i >= n_shifts
                sch_rows.append(
                    {
                        "assignment_id": f"SCH-{sch_seq:07d}",
                        "employee_id": e.employee_id,
                        "department_id": e.department_id,
                        "shift_date": d,
                        "shift_code": shift,
                        "scheduled_hours": hours,
                        "is_extra_shift": int(is_extra),
                        "is_swap": int(is_swap),
                    }
                )
                sch_seq += 1
                flu = d.month in FLU_MONTHS
                unplanned_p = 0.03 + 0.18 * e.absence + (0.02 if flu else 0.0)
                pto_p = 0.015
                draw = float(rng.random())
                if draw < unplanned_p:
                    abs_rows.append(
                        {
                            "absence_id": f"ABS-{abs_seq:07d}",
                            "employee_id": e.employee_id,
                            "department_id": e.department_id,
                            "absence_date": d,
                            "absence_type": ABSENCE_TYPES_UNPLANNED,
                            "hours_missed": hours,
                            "scheduled_shift_code": shift,
                        }
                    )
                    abs_seq += 1
                    continue
                if draw < unplanned_p + pto_p:
                    abs_rows.append(
                        {
                            "absence_id": f"ABS-{abs_seq:07d}",
                            "employee_id": e.employee_id,
                            "department_id": e.department_id,
                            "absence_date": d,
                            "absence_type": ABSENCE_TYPE_PTO,
                            "hours_missed": hours,
                            "scheduled_shift_code": shift,
                        }
                    )
                    abs_seq += 1
                    continue
                ot_hours = 0.0
                if is_extra or rng.random() < (0.08 * e.ot * (1.0 + vac + (0.3 if flu else 0.0))):
                    ot_hours = float(rng.choice(np.array([1.0, 2.0, 3.0, 4.0])))
                tc_rows.append(
                    {
                        "time_card_id": f"TC-{tc_seq:07d}",
                        "employee_id": e.employee_id,
                        "department_id": e.department_id,
                        "work_date": d,
                        "shift_code": shift,
                        "hours_worked": hours + ot_hours,
                        "overtime_hours": ot_hours,
                    }
                )
                tc_seq += 1
            week += timedelta(days=7)

    tables["schedule_assignments"] = pd.DataFrame(sch_rows)
    tables["time_cards"] = pd.DataFrame(tc_rows)
    tables["absences"] = pd.DataFrame(abs_rows)

    for name, cols in TABLE_COLUMNS.items():
        if name not in tables:
            raise RuntimeError(f"Generator missing table {name}")
        tables[name] = tables[name].loc[:, list(cols)]
    return tables
