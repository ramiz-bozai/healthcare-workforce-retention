from __future__ import annotations

import pandas as pd
import pytest

from data_generation.schema import FORBIDDEN_COLUMN_SUBSTRINGS
from src.ml.contract import (
    ATTRITION_CATEGORICAL,
    ATTRITION_NUMERIC,
    SHORTAGE_CATEGORICAL,
    SHORTAGE_NUMERIC,
    assert_feature_safety,
)
from src.ml.run import run_models
from src.ml.train import production_honest_attrition, production_honest_shortage
from src.pipeline.local_run import run_local


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    db = tmp_path_factory.mktemp("ml") / "carestaff.duckdb"
    pipeline = run_local(include_fixtures=False, duckdb_path=db)
    result = run_models(pipeline.con, log_mlflow=False, model_dir=tmp_path_factory.mktemp("models"))
    yield pipeline, result
    pipeline.con.close()


def test_feature_contracts_reject_ids_labels_and_pay():
    assert_feature_safety(ATTRITION_NUMERIC + ATTRITION_CATEGORICAL)
    assert_feature_safety(SHORTAGE_NUMERIC + SHORTAGE_CATEGORICAL)
    for col in list(ATTRITION_NUMERIC) + list(ATTRITION_CATEGORICAL) + list(SHORTAGE_NUMERIC) + list(SHORTAGE_CATEGORICAL):
        lowered = col.lower()
        for token in FORBIDDEN_COLUMN_SUBSTRINGS:
            assert token not in lowered, col


def test_attrition_train_uses_only_realized_labels(trained):
    pipeline, _ = trained
    employees = pipeline.con.execute("SELECT * FROM gold.employee_month_features").fetchdf()
    train, valid, inference = production_honest_attrition(employees, "2026-09-01")
    assert train["is_inference_snapshot"].astype(bool).sum() == 0
    assert valid["is_inference_snapshot"].astype(bool).sum() == 0
    as_of = pd.Timestamp("2026-09-01")
    horizon = pd.Timedelta(days=90)
    assert (train["snapshot_date"] + horizon <= as_of).all()
    assert (valid["snapshot_date"] + horizon <= as_of).all()
    assert inference["is_inference_snapshot"].astype(bool).all()
    assert len(inference) == 180


def test_shortage_train_requires_complete_14d_window(trained):
    pipeline, _ = trained
    weeks = pipeline.con.execute("SELECT * FROM gold.unit_week_features").fetchdf()
    train, valid, latest = production_honest_shortage(weeks)
    assert train["label_window_complete_14d"].astype(bool).all()
    assert valid["label_window_complete_14d"].astype(bool).all()
    assert latest["department_id"].nunique() == 8
    assert len(latest) == 8


def test_models_rank_above_chance_on_held_out_valid(trained):
    _, result = trained
    att = result.attrition.metrics["valid"]
    sh = result.shortage.metrics["valid"]
    assert att["n_pos"] >= 5
    assert att["roc_auc"] >= 0.60
    assert att["brier"] < att["base_rate"] * (1 - att["base_rate"]) + 0.05
    assert sh["roc_auc"] >= 0.55
    persist = result.shortage.metrics["valid_persistence_baseline"]
    assert sh["brier"] <= persist["brier"] + 0.08


def test_demo_oracle_leavers_score_higher_than_stayers(trained):
    _, result = trained
    scores = result.attrition_scores
    leavers = scores.loc[scores["label_voluntary_90d"] == 1, "p_voluntary_90d"]
    stayers = scores.loc[scores["label_voluntary_90d"] == 0, "p_voluntary_90d"]
    assert leavers.mean() > stayers.mean()
    assert 20 <= int(scores["high_risk_flag"].sum()) <= 40


def test_scores_are_not_written_onto_operational_kpis(trained):
    pipeline, result = trained
    kpi_cols = {r[0] for r in pipeline.con.execute("DESCRIBE gold.executive_kpis").fetchall()}
    assert "predicted_attrition_rate_90d" not in kpi_cols
    brief = result.exec_brief.iloc[0]
    assert int(brief["high_risk_headcount"]) == int(result.attrition_scores["high_risk_flag"].sum())
    assert float(brief["planning_attrition_exposure_usd"]) > 0
    note = str(brief["model_note"]).lower()
    assert "pending_human_review" in note
    models = pipeline.con.execute(
        "SELECT COUNT(*) FROM gold.metric_catalog WHERE includes_model = 1"
    ).fetchone()[0]
    assert models >= 5


def test_no_salary_feature_on_score_inputs(trained):
    _, result = trained
    for feat in result.attrition.features + result.shortage.features:
        assert "salary" not in feat.lower()
        assert "wage" not in feat.lower()
