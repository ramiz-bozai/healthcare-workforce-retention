"""Playbook what-if and recommended actions. Status is always pending_human_review.

Perturbations are assumed feature shifts. They are never written back to silver
or gold feature tables and are not measured savings.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.ml.contract import ATTRITION_CATEGORICAL, ATTRITION_NUMERIC, SHORTAGE_CATEGORICAL, SHORTAGE_NUMERIC
from src.ml.features import feature_frame
from src.ml.train import FittedModel, _proba

STATUS = "pending_human_review"
ASSUMPTION = (
    "Planning estimate if named features changed as assumed. "
    "Not measured savings. Not applied. Pending human review."
)

WHATIF_CATALOG = (
    (
        "whatif_planning_attrition_exposure_usd",
        "whatif_scenarios",
        "scenario",
        "Sum of role-average replacement cost for employees still above the frozen high-risk cut after the assumed feature shift",
        1,
    ),
    (
        "whatif_planning_coverage_exposure_usd",
        "whatif_scenarios",
        "scenario",
        "Flagged units' assumed 14d hour gap * mean agency hourly after the feature shift",
        1,
    ),
)


def _ops(cfg: dict[str, Any]) -> dict[str, Any]:
    w = cfg.raw["actions"]["whatif"]
    return {
        "schedule_stabilize": {
            "scored": True,
            "summary": "Cut swaps in half and drop extra shifts for the named employees.",
            "attrition": {
                "swap_count_90d": ("multiply", float(w["swap_keep"])),
                "extra_shift_count_30d": ("set", float(w["extra_shift_set"])),
            },
            "shortage": {},
        },
        "workload_balance": {
            "scored": True,
            "summary": "Cut overtime hours 40% for the named employees.",
            "attrition": {
                "ot_hours_30d": ("multiply", float(w["ot_keep"])),
                "ot_hours_90d": ("multiply", float(w["ot_keep"])),
            },
            "shortage": {},
        },
        "recruit_prioritize": {
            "scored": True,
            "summary": "Assume vacancy and open-shift share fall; coverage lifts 0.10 (capped).",
            "attrition": {
                "unit_vacancy_rate": ("multiply", float(w["vacancy_keep"])),
                "open_fte_in_unit": ("multiply", float(w["open_fte_keep"])),
            },
            "shortage": {
                "avg_coverage_ratio": ("add_cap", float(w["coverage_lift"]), float(w["coverage_cap"])),
                "avg_open_shift_share": ("multiply", float(w["open_shift_keep"])),
                "shortage_day_count": ("multiply", 0.5),
                "is_shortage_week": ("set", 0),
            },
            "gap_keep": float(w["gap_hours_keep"]),
        },
        "float_ot_review": {
            "scored": True,
            "summary": "Cut unit overtime 40% and employee OT 40% on the named units.",
            "attrition": {
                "ot_hours_30d": ("multiply", float(w["ot_keep"])),
                "ot_hours_90d": ("multiply", float(w["ot_keep"])),
            },
            "shortage": {"overtime_hours": ("multiply", float(w["ot_keep"]))},
        },
        "manager_outreach": {
            "scored": False,
            "summary": "Supervisor conversation. The model does not score outreach.",
            "attrition": {},
            "shortage": {},
        },
    }


def apply_ops(frame: pd.DataFrame, ops: dict[str, tuple], mask: pd.Series) -> pd.DataFrame:
    out = frame.copy()
    if not mask.any() or not ops:
        return out
    for col, spec in ops.items():
        if col not in out.columns:
            continue
        kind = spec[0]
        values = pd.to_numeric(out.loc[mask, col], errors="coerce")
        if kind == "multiply":
            out.loc[mask, col] = values * spec[1]
        elif kind == "set":
            value = spec[1]
            if str(out[col].dtype) == "bool" or pd.api.types.is_bool_dtype(out[col]):
                value = bool(value)
            out.loc[mask, col] = value
        elif kind == "add_cap":
            out.loc[mask, col] = np.minimum(values + spec[1], spec[2])
    return out


def _score_attrition(model: FittedModel, frame: pd.DataFrame) -> np.ndarray:
    return _proba(model.pipeline, feature_frame(frame, ATTRITION_NUMERIC, ATTRITION_CATEGORICAL))


def _score_shortage(model: FittedModel, frame: pd.DataFrame) -> np.ndarray:
    return _proba(model.pipeline, feature_frame(frame, SHORTAGE_NUMERIC, SHORTAGE_CATEGORICAL))


def recommend_and_simulate(
    *,
    emp: pd.DataFrame,
    weeks: pd.DataFrame,
    att_scores: pd.DataFrame,
    sh_scores: pd.DataFrame,
    attrition: FittedModel,
    shortage: FittedModel,
    cfg,
    as_of: str,
    agency_hourly: float,
    high_risk_cut: float,
    shortage_cut: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    playbook = set(cfg.raw["actions"]["playbook"])
    ops = _ops(cfg)
    if playbook != set(ops):
        raise ValueError(f"Playbook mismatch: {playbook} vs {set(ops)}")

    emp = emp.reset_index(drop=True).copy()
    weeks = weeks.reset_index(drop=True).copy()
    att_scores = att_scores.reset_index(drop=True).copy()
    sh_scores = sh_scores.reset_index(drop=True).copy()

    high_risk_ids = set(att_scores.loc[att_scores["high_risk_flag"].astype(bool), "employee_id"])
    flagged_units = set(sh_scores.loc[sh_scores["predicted_shortage_flag"].astype(bool), "department_id"])
    med_swap = float(pd.to_numeric(emp["swap_count_90d"], errors="coerce").median())
    med_ot = float(pd.to_numeric(emp["ot_hours_90d"], errors="coerce").median())
    med_unit_ot = float(pd.to_numeric(weeks["overtime_hours"], errors="coerce").median())

    emp = emp.merge(
        att_scores[["employee_id", "p_voluntary_90d", "high_risk_flag", "planning_replacement_usd", "display_name"]],
        on="employee_id",
        how="left",
        suffixes=("", "_score"),
    )
    if "display_name_score" in emp.columns:
        emp["display_name"] = emp["display_name"].fillna(emp["display_name_score"])

    baseline_p_emp = _score_attrition(attrition, emp)
    baseline_p_unit = _score_shortage(shortage, weeks)
    emp = emp.copy()
    emp["p_voluntary_90d"] = baseline_p_emp
    weeks = weeks.copy()
    weeks["p_shortage_14d"] = baseline_p_unit
    if "planning_coverage_exposure_usd" not in weeks.columns:
        weeks = weeks.merge(
            sh_scores[["department_id", "trailing_gap_hours_14d", "planning_coverage_exposure_usd"]],
            on="department_id",
            how="left",
        )
    weeks["trailing_gap_hours_14d"] = weeks["trailing_gap_hours_14d"].fillna(0.0)
    weeks["planning_coverage_exposure_usd"] = np.where(
        weeks["p_shortage_14d"] >= shortage_cut,
        weeks["trailing_gap_hours_14d"] * agency_hourly,
        0.0,
    )
    emp["planning_replacement_usd"] = emp["planning_replacement_usd"].fillna(0.0)

    def scenario_metrics(emp_s: pd.DataFrame, week_s: pd.DataFrame, gap_keep: float | None = None) -> dict[str, float]:
        p_emp = _score_attrition(attrition, emp_s)
        p_unit = _score_shortage(shortage, week_s)
        hr = p_emp >= high_risk_cut
        fl = p_unit >= shortage_cut
        gap = week_s["trailing_gap_hours_14d"].to_numpy(dtype=float)
        if gap_keep is not None:
            gap = np.where(week_s["department_id"].isin(flagged_units), gap * gap_keep, gap)
        cov_usd = float(np.where(fl, gap * agency_hourly, 0.0).sum())
        return {
            "mean_p_attrition": float(p_emp.mean()),
            "high_risk_headcount": float(hr.sum()),
            "planning_attrition_exposure_usd": float(emp_s.loc[hr, "planning_replacement_usd"].sum()),
            "mean_p_shortage": float(p_unit.mean()),
            "flagged_units": float(fl.sum()),
            "planning_coverage_exposure_usd": cov_usd,
        }

    baseline = scenario_metrics(emp, weeks)
    scenarios = [
        {
            "scenario_id": "baseline",
            "playbook_action": "none",
            "scope": "none",
            "n_employees": 0,
            "n_units": 0,
            "scored": True,
            **baseline,
            "planning_attrition_delta_usd": 0.0,
            "planning_coverage_delta_usd": 0.0,
            "assumption_note": ASSUMPTION,
        }
    ]

    def add_scored_scenario(scenario_id: str, action: str, emp_ids: set[str], unit_ids: set[str]) -> dict[str, float]:
        spec = ops[action]
        emp_s = apply_ops(emp, spec["attrition"], emp["employee_id"].isin(emp_ids))
        week_s = apply_ops(weeks, spec["shortage"], weeks["department_id"].isin(unit_ids))
        metrics = scenario_metrics(emp_s, week_s, spec.get("gap_keep"))
        row = {
            "scenario_id": scenario_id,
            "playbook_action": action,
            "scope": f"employees={len(emp_ids)};units={len(unit_ids)}",
            "n_employees": len(emp_ids),
            "n_units": len(unit_ids),
            "scored": True,
            **metrics,
            "planning_attrition_delta_usd": baseline["planning_attrition_exposure_usd"]
            - metrics["planning_attrition_exposure_usd"],
            "planning_coverage_delta_usd": baseline["planning_coverage_exposure_usd"]
            - metrics["planning_coverage_exposure_usd"],
            "assumption_note": ASSUMPTION,
        }
        scenarios.append(row)
        return metrics

    add_scored_scenario("stabilize_high_risk", "schedule_stabilize", high_risk_ids, set())
    add_scored_scenario("cut_ot_high_risk", "workload_balance", high_risk_ids, set())
    unit_emps = set(emp.loc[emp["department_id"].isin(flagged_units), "employee_id"])
    add_scored_scenario("recruit_short_units", "recruit_prioritize", unit_emps, flagged_units)
    add_scored_scenario("review_ot_short_units", "float_ot_review", unit_emps, flagged_units)

    bundle_emp = apply_ops(emp, ops["schedule_stabilize"]["attrition"], emp["employee_id"].isin(high_risk_ids))
    bundle_emp = apply_ops(
        bundle_emp, ops["workload_balance"]["attrition"], bundle_emp["employee_id"].isin(high_risk_ids)
    )
    bundle_emp = apply_ops(
        bundle_emp, ops["recruit_prioritize"]["attrition"], bundle_emp["employee_id"].isin(unit_emps)
    )
    bundle_week = apply_ops(
        weeks, ops["recruit_prioritize"]["shortage"], weeks["department_id"].isin(flagged_units)
    )
    bundle_metrics = scenario_metrics(bundle_emp, bundle_week, ops["recruit_prioritize"].get("gap_keep"))
    scenarios.append(
        {
            "scenario_id": "bundle_stabilize_ot_recruit",
            "playbook_action": "schedule_stabilize+workload_balance+recruit_prioritize",
            "scope": f"employees={len(high_risk_ids | unit_emps)};units={len(flagged_units)}",
            "n_employees": len(high_risk_ids | unit_emps),
            "n_units": len(flagged_units),
            "scored": True,
            **bundle_metrics,
            "planning_attrition_delta_usd": baseline["planning_attrition_exposure_usd"]
            - bundle_metrics["planning_attrition_exposure_usd"],
            "planning_coverage_delta_usd": baseline["planning_coverage_exposure_usd"]
            - bundle_metrics["planning_coverage_exposure_usd"],
            "assumption_note": ASSUMPTION,
        }
    )

    actions: list[dict[str, Any]] = []

    def person_delta(action: str, row: pd.Series) -> float:
        spec = ops[action]
        if not spec["scored"]:
            return 0.0
        one = emp.loc[[row.name]].copy()
        shifted = apply_ops(one, spec["attrition"], pd.Series([True], index=one.index))
        p0 = float(row["p_voluntary_90d"])
        p1 = float(_score_attrition(attrition, shifted)[0])
        return p0 - p1

    for _, row in emp.loc[emp["employee_id"].isin(high_risk_ids)].iterrows():
        candidates = []
        if float(row["swap_count_90d"]) > med_swap:
            candidates.append(("schedule_stabilize", person_delta("schedule_stabilize", row)))
        if float(row["ot_hours_90d"]) > med_ot:
            candidates.append(("workload_balance", person_delta("workload_balance", row)))
        if not candidates:
            candidates.append(("workload_balance", person_delta("workload_balance", row)))
        action, delta = max(candidates, key=lambda item: item[1])
        actions.append(
            {
                "subject_type": "employee",
                "subject_id": row["employee_id"],
                "display_name": row.get("display_name"),
                "department_id": row["department_id"],
                "playbook_action": action,
                "baseline_p": float(row["p_voluntary_90d"]),
                "scenario_p": float(row["p_voluntary_90d"]) - delta,
                "planning_delta_usd": float(row["planning_replacement_usd"]) if delta > 0 else 0.0,
                "scored": True,
                "rationale": (
                    f"{ops[action]['summary']} Current p={row['p_voluntary_90d']:.3f}; "
                    f"assumed Δp={delta:.3f}."
                ),
            }
        )

    top_outreach = (
        emp.loc[emp["employee_id"].isin(high_risk_ids)]
        .sort_values("p_voluntary_90d", ascending=False)
        .head(10)
    )
    for _, row in top_outreach.iterrows():
        actions.append(
            {
                "subject_type": "employee",
                "subject_id": row["employee_id"],
                "display_name": row.get("display_name"),
                "department_id": row["department_id"],
                "playbook_action": "manager_outreach",
                "baseline_p": float(row["p_voluntary_90d"]),
                "scenario_p": float(row["p_voluntary_90d"]),
                "planning_delta_usd": 0.0,
                "scored": False,
                "rationale": ops["manager_outreach"]["summary"],
            }
        )

    def unit_action_row(row: pd.Series, unit_action: str) -> dict[str, Any]:
        one = weeks.loc[[row.name]].copy()
        shifted = apply_ops(one, ops[unit_action]["shortage"], pd.Series([True], index=one.index))
        p1 = float(_score_shortage(shortage, shifted)[0])
        p0 = float(row["p_shortage_14d"])
        return {
            "subject_type": "department",
            "subject_id": row["department_id"],
            "display_name": row["department_id"],
            "department_id": row["department_id"],
            "playbook_action": unit_action,
            "baseline_p": p0,
            "scenario_p": p1,
            "planning_delta_usd": float(row["planning_coverage_exposure_usd"]),
            "scored": True,
            "rationale": (
                f"{ops[unit_action]['summary']} Current p_shortage={p0:.3f}; "
                f"assumed p={p1:.3f}."
            ),
        }

    flagged_week_rows = weeks.loc[weeks["department_id"].isin(flagged_units)]
    for _, row in flagged_week_rows.iterrows():
        actions.append(unit_action_row(row, "recruit_prioritize"))
        if float(row["overtime_hours"]) > med_unit_ot:
            actions.append(unit_action_row(row, "float_ot_review"))
    if flagged_week_rows.empty and len(weeks):
        actions.append(unit_action_row(weeks.iloc[0], "recruit_prioritize"))

    present = {a["playbook_action"] for a in actions}
    hr = emp.loc[emp["employee_id"].isin(high_risk_ids)]
    if "schedule_stabilize" not in present and len(hr):
        row = hr.sort_values("swap_count_90d", ascending=False).iloc[0]
        delta = person_delta("schedule_stabilize", row)
        actions.append(
            {
                "subject_type": "employee",
                "subject_id": row["employee_id"],
                "display_name": row.get("display_name"),
                "department_id": row["department_id"],
                "playbook_action": "schedule_stabilize",
                "baseline_p": float(row["p_voluntary_90d"]),
                "scenario_p": float(row["p_voluntary_90d"]) - delta,
                "planning_delta_usd": float(row["planning_replacement_usd"]) if delta > 0 else 0.0,
                "scored": True,
                "rationale": ops["schedule_stabilize"]["summary"],
            }
        )
    if "workload_balance" not in present and len(hr):
        row = hr.sort_values("ot_hours_90d", ascending=False).iloc[0]
        delta = person_delta("workload_balance", row)
        actions.append(
            {
                "subject_type": "employee",
                "subject_id": row["employee_id"],
                "display_name": row.get("display_name"),
                "department_id": row["department_id"],
                "playbook_action": "workload_balance",
                "baseline_p": float(row["p_voluntary_90d"]),
                "scenario_p": float(row["p_voluntary_90d"]) - delta,
                "planning_delta_usd": float(row["planning_replacement_usd"]) if delta > 0 else 0.0,
                "scored": True,
                "rationale": ops["workload_balance"]["summary"],
            }
        )
    if "float_ot_review" not in present and len(weeks):
        actions.append(unit_action_row(weeks.sort_values("overtime_hours", ascending=False).iloc[0], "float_ot_review"))

    action_rows = []
    for i, rec in enumerate(actions, start=1):
        action_rows.append(
            {
                "action_id": f"ACT-{i:04d}",
                "as_of_date": as_of,
                "subject_type": rec["subject_type"],
                "subject_id": rec["subject_id"],
                "display_name": rec["display_name"],
                "department_id": rec["department_id"],
                "playbook_action": rec["playbook_action"],
                "baseline_p": rec["baseline_p"],
                "scenario_p": rec["scenario_p"],
                "planning_delta_usd": rec["planning_delta_usd"],
                "scored": rec["scored"],
                "status": STATUS,
                "requires_human_review": True,
                "applied": False,
                "rationale": rec["rationale"],
                "assumption_note": ASSUMPTION,
            }
        )
    return pd.DataFrame(scenarios), pd.DataFrame(action_rows)


def write_whatif(con, scenarios: pd.DataFrame, actions: pd.DataFrame, as_of: str) -> None:
    con.register("_whatif_scenarios", scenarios)
    con.register("_recommended_actions", actions)
    con.execute("CREATE OR REPLACE TABLE gold.whatif_scenarios AS SELECT * FROM _whatif_scenarios")
    con.execute("CREATE OR REPLACE TABLE gold.recommended_actions AS SELECT * FROM _recommended_actions")
    extra = pd.DataFrame(
        WHATIF_CATALOG,
        columns=["metric_name", "table_name", "grain", "formula", "includes_model"],
    )
    existing = con.execute("SELECT * FROM gold.metric_catalog").fetchdf()
    combined = pd.concat([existing, extra], ignore_index=True).drop_duplicates("metric_name")
    con.register("_catalog_whatif", combined)
    con.execute("CREATE OR REPLACE TABLE gold.metric_catalog AS SELECT * FROM _catalog_whatif")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE gold.action_summary AS
        SELECT
          DATE '{as_of}' AS as_of_date,
          COUNT(*) AS recommended_action_count,
          SUM(CAST(requires_human_review AS INTEGER)) AS pending_human_review_count,
          SUM(CAST(applied AS INTEGER)) AS applied_count,
          '{STATUS}' AS uniform_status,
          '{ASSUMPTION.replace("'", "''")}' AS assumption_note
        FROM gold.recommended_actions
        """
    )
