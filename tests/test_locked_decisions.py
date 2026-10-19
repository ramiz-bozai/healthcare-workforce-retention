"""Guardrails so approved FE Bar decisions cannot drift out of conf/."""

from __future__ import annotations

from datetime import date

from data_generation.catalogs import ROLES, departments_for_profile, facilities_for_profile
from data_generation.config import load_config


def test_locked_project_identity():
    cfg = load_config("seed")
    assert cfg.project_name == "CareStaff Insight"
    assert cfg.random_seed == 42
    assert cfg.as_of_date == date(2026, 9, 1)
    assert cfg.attrition_horizon_days == 90


def test_locked_label_thresholds():
    labels = load_config("seed").raw["labels"]
    assert labels["attrition_positive_class"] == "voluntary"
    assert labels["shortage_coverage_ratio_threshold"] == 0.90
    assert labels["shortage_open_shift_share_threshold"] == 0.10
    assert labels["shortage_primary_horizon_days"] == 14
    assert labels["shortage_secondary_horizon_days"] == 28


def test_ai_layer_is_template_and_not_claiming_genie():
    ai = load_config("seed").raw["ai"]
    assert ai["mode"] == "template"
    assert ai["genie_live"] is False
    assert ai["model_serving_live"] is False
    assert int(ai["max_rows"]) == 12


def test_locked_actions_require_human_review():
    actions = load_config("seed").raw["actions"]
    assert actions["require_human_review"] is True
    assert actions["playbook"] == [
        "schedule_stabilize",
        "manager_outreach",
        "workload_balance",
        "recruit_prioritize",
        "float_ot_review",
    ]


def test_role_salaries_cover_clinical_scope():
    cfg = load_config("seed")
    role_codes = {r["role_code"] for r in ROLES}
    assert role_codes == set(cfg.cost.salaries_usd)
    assert cfg.cost.replacement_multiplier == 1.0
    assert cfg.cost.agency_to_staff_hourly_ratio == 2.0
    for salary in cfg.cost.salaries_usd.values():
        assert salary > 0


def test_profile_volumes():
    seed = load_config("seed")
    demo = load_config("demo")
    assert seed.n_active_employees == 180
    assert seed.n_facilities == 2
    assert seed.n_units == 8
    assert demo.n_active_employees == 1200
    assert demo.n_facilities == 3
    assert demo.n_units == 12
    assert len(departments_for_profile("seed")) == 8
    assert len(facilities_for_profile("seed")) == 2
    assert len(departments_for_profile("demo")) == 12
    assert len(facilities_for_profile("demo")) == 3
