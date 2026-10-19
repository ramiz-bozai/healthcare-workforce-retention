"""Load conf/default.yaml and bind a generation profile."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "conf" / "default.yaml"


@dataclass(frozen=True)
class CostAssumptions:
    hours_per_year: int
    replacement_multiplier: float
    agency_to_staff_hourly_ratio: float
    salaries_usd: dict[str, int]
    note: str


@dataclass(frozen=True)
class GenerationConfig:
    project_name: str
    profile: str
    random_seed: int
    as_of_date: date
    history_start: date
    future_end: date
    n_active_employees: int
    n_facilities: int
    n_units: int
    history_months: int
    attrition_horizon_days: int
    cost: CostAssumptions
    raw: dict[str, Any]


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def load_config(profile: str = "seed", path: Path | None = None) -> GenerationConfig:
    cfg_path = path or DEFAULT_CONFIG
    with cfg_path.open() as f:
        raw = yaml.safe_load(f)
    if profile not in raw["generation"]["profiles"]:
        raise ValueError(f"Unknown profile {profile!r}. Use 'seed' or 'demo'.")
    p = raw["generation"]["profiles"][profile]
    as_of = _parse_date(raw["project"]["as_of_date"])
    history_key = "history_start_seed" if profile == "seed" else "history_start_demo"
    history_start = _parse_date(raw["generation"][history_key])
    horizon = int(raw["generation"]["future_horizon_days"])
    cost_raw = raw["cost_assumptions"]
    cost = CostAssumptions(
        hours_per_year=int(cost_raw["hours_per_year"]),
        replacement_multiplier=float(cost_raw["replacement_multiplier"]),
        agency_to_staff_hourly_ratio=float(cost_raw["agency_to_staff_hourly_ratio"]),
        salaries_usd={k: int(v) for k, v in cost_raw["salaries_usd"].items()},
        note=str(cost_raw["note"]).strip(),
    )
    return GenerationConfig(
        project_name=raw["project"]["name"],
        profile=profile,
        random_seed=int(raw["project"]["random_seed"]),
        as_of_date=as_of,
        history_start=history_start,
        future_end=as_of + timedelta(days=horizon),
        n_active_employees=int(p["n_active_employees"]),
        n_facilities=int(p["n_facilities"]),
        n_units=int(p["n_units"]),
        history_months=int(p["history_months"]),
        attrition_horizon_days=int(raw["labels"]["attrition_horizon_days"]),
        cost=cost,
        raw=raw,
    )
