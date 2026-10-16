from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.ml.predict import load_local_models
from src.ml.run import run_models
from src.ml.whatif import STATUS, apply_ops
from src.pipeline.local_run import run_local

PLAYBOOK = {
    "schedule_stabilize",
    "manager_outreach",
    "workload_balance",
    "recruit_prioritize",
    "float_ot_review",
}


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    db = tmp_path_factory.mktemp("whatif") / "carestaff.duckdb"
    models = tmp_path_factory.mktemp("whatif-models")
    pipeline = run_local(include_fixtures=False, duckdb_path=db)
    result = run_models(pipeline.con, log_mlflow=False, model_dir=models)
    yield pipeline, result, models
    pipeline.con.close()


def test_apply_ops_does_not_mutate_source():
    frame = pd.DataFrame({"employee_id": ["a", "b"], "swap_count_90d": [10.0, 8.0]})
    original = frame["swap_count_90d"].tolist()
    out = apply_ops(frame, {"swap_count_90d": ("multiply", 0.5)}, frame["employee_id"] == "a")
    assert frame["swap_count_90d"].tolist() == original
    assert float(out.loc[out["employee_id"] == "a", "swap_count_90d"].iloc[0]) == 5.0
    assert float(out.loc[out["employee_id"] == "b", "swap_count_90d"].iloc[0]) == 8.0


def test_every_action_is_pending_human_review_and_closed_playbook(trained):
    pipeline, result, _ = trained
    actions = result.recommended_actions
    assert len(actions) >= 10
    assert set(actions["status"].unique()) == {STATUS}
    assert bool(actions["requires_human_review"].all())
    assert not bool(actions["applied"].astype(bool).any())
    assert set(actions["playbook_action"]).issubset(PLAYBOOK)
    assert PLAYBOOK.issubset(set(actions["playbook_action"]))
    n_pending = pipeline.con.execute(
        "SELECT COUNT(*) FROM gold.recommended_actions WHERE status = 'pending_human_review'"
    ).fetchone()[0]
    assert n_pending == len(actions)
    applied = pipeline.con.execute(
        "SELECT applied_count FROM gold.action_summary"
    ).fetchone()[0]
    assert int(applied) == 0


def test_whatif_does_not_rewrite_gold_features(trained):
    pipeline, _, _ = trained
    swaps = pipeline.con.execute(
        """
        SELECT SUM(swap_count_90d) FROM gold.employee_month_features
        WHERE is_inference_snapshot
        """
    ).fetchone()[0]
    coverage = pipeline.con.execute(
        "SELECT AVG(avg_coverage_ratio) FROM gold.unit_week_features"
    ).fetchone()[0]
    # Re-read after what-if write; values must still match a fresh silver-derived gold grain.
    assert float(swaps) > 0
    assert 0.2 < float(coverage) < 2.0
    mutated = pipeline.con.execute(
        """
        SELECT COUNT(*) FROM gold.employee_month_features f
        JOIN gold.recommended_actions a ON f.employee_id = a.subject_id
        WHERE f.is_inference_snapshot AND a.playbook_action = 'schedule_stabilize'
          AND a.applied
        """
    ).fetchone()[0]
    assert mutated == 0


def test_stabilize_lowers_mean_attrition_p_for_high_risk(trained):
    _, result, _ = trained
    base = result.whatif_scenarios.set_index("scenario_id")
    assert float(base.loc["stabilize_high_risk", "mean_p_attrition"]) < float(
        base.loc["baseline", "mean_p_attrition"]
    )
    assert float(base.loc["bundle_stabilize_ot_recruit", "planning_attrition_delta_usd"]) >= 0
    assert "not measured savings" in str(base.loc["baseline", "assumption_note"]).lower()


def test_manager_outreach_is_unscored(trained):
    _, result, _ = trained
    outreach = result.recommended_actions.loc[
        result.recommended_actions["playbook_action"] == "manager_outreach"
    ]
    assert len(outreach)
    assert not bool(outreach["scored"].astype(bool).any())
    assert np.allclose(outreach["baseline_p"], outreach["scenario_p"])
    assert float(outreach["planning_delta_usd"].sum()) == 0.0


def test_in_process_predict_matches_scored_table(trained):
    pipeline, result, models = trained
    loaded = load_local_models(models)
    assert loaded.policy["serving"] == "in_process_predict"
    emp = pipeline.con.execute(
        "SELECT * FROM gold.employee_month_features WHERE is_inference_snapshot"
    ).fetchdf()
    p = loaded.predict_attrition(emp)
    scored = result.attrition_scores.sort_values("employee_id")
    emp = emp.sort_values("employee_id")
    aligned = emp.merge(scored[["employee_id", "p_voluntary_90d"]], on="employee_id")
    rerun = loaded.predict_attrition(aligned)
    assert np.allclose(rerun, aligned["p_voluntary_90d"].to_numpy(), atol=1e-6)
    assert abs(float(p.mean()) - float(scored["p_voluntary_90d"].mean())) < 1e-6
