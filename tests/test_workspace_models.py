from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.ml.workspace_run import (
    INPUT_TABLES,
    OUTPUT_TABLES,
    PIPELINE_OWNED_GOLD,
    duckdb_from_frames,
    frames_from_connection,
    run_from_frames,
    spark_output_name,
    uc_fqn,
    uc_table,
    write_frames_to_spark,
)
from src.pipeline.local_run import run_local

ROOT = Path(__file__).resolve().parents[1]


def test_uc_names_match_lakeflow_prefix():
    assert uc_table("gold", "executive_kpis") == "gold_executive_kpis"
    assert uc_fqn("healthcare_ops", "carestaff_insight", "silver", "employees") == (
        "healthcare_ops.carestaff_insight.silver_employees"
    )
    assert "executive_kpis" in PIPELINE_OWNED_GOLD
    assert "metric_catalog" in PIPELINE_OWNED_GOLD
    assert "exec_brief" not in PIPELINE_OWNED_GOLD
    assert "exec_brief" in OUTPUT_TABLES
    assert "employee_month_features" not in OUTPUT_TABLES
    assert spark_output_name("metric_catalog") == "metric_catalog_scored"
    assert spark_output_name("exec_brief") == "exec_brief"


def test_refuses_to_overwrite_pipeline_feature_tables():
    class Dummy:
        def createDataFrame(self, df):  # pragma: no cover
            raise AssertionError("must not write pipeline-owned gold")

    with pytest.raises(ValueError, match="Lakeflow-owned"):
        write_frames_to_spark(
            Dummy(),
            "c",
            "s",
            {"employee_month_features": pd.DataFrame({"employee_id": ["EMP-000001"]})},
        )


def test_metric_catalog_writes_under_scored_name():
    written: list[str] = []

    class Writer:
        def format(self, _fmt):
            return self

        def mode(self, _mode):
            return self

        def option(self, *_args, **_kwargs):
            return self

        def saveAsTable(self, fqn):
            written.append(fqn)

    class Frame:
        @property
        def write(self):
            return Writer()

    class Dummy:
        def createDataFrame(self, df):
            return Frame()

    out = write_frames_to_spark(
        Dummy(),
        "c",
        "s",
        {"metric_catalog": pd.DataFrame({"metric_name": ["coverage_ratio_7d"]})},
    )
    assert out == ["c.s.gold_metric_catalog_scored"]
    assert written == ["c.s.gold_metric_catalog_scored"]


def test_duckdb_bridge_from_local_gold(tmp_path: Path):
    built = run_local(include_fixtures=False, duckdb_path=tmp_path / "carestaff.duckdb")
    try:
        frames = frames_from_connection(built.con)
    finally:
        built.con.close()
    assert set(frames) == {f"{layer}.{name}" for layer, name in INPUT_TABLES}
    con = duckdb_from_frames(frames)
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM gold.employee_month_features WHERE is_inference_snapshot"
        ).fetchone()[0]
        assert n == 180
        assert con.execute("SELECT COUNT(*) FROM silver.employees").fetchone()[0] >= 180
    finally:
        con.close()


def test_run_from_frames_writes_exec_brief_and_joblib(tmp_path: Path):
    built = run_local(include_fixtures=False, duckdb_path=tmp_path / "carestaff.duckdb")
    try:
        frames = frames_from_connection(built.con)
    finally:
        built.con.close()
    models = tmp_path / "models"
    result, con = run_from_frames(frames, model_dir=models, log_mlflow=False)
    try:
        brief = result.exec_brief.iloc[0]
        assert int(brief["active_headcount"]) == 180
        assert "predicted_attrition_rate_90d" in brief.index
        assert (models / "attrition.joblib").exists()
        assert (models / "shortage.joblib").exists()
        actions = con.execute("SELECT DISTINCT status, applied FROM gold.recommended_actions").fetchdf()
        assert set(actions["status"]) == {"pending_human_review"}
        assert set(actions["applied"]) == {False}
    finally:
        con.close()


def test_models_notebook_is_not_lakeflow_source():
    recipe = ROOT / "pipelines" / "carestaff_insight"
    assert not (recipe / "07_workspace_models.py").exists()
    text = (ROOT / "notebooks" / "07_workspace_models.py").read_text()
    assert "run_workspace_models" in text
    assert "model_serving_live" in text
    assert "Not Model Serving" in text or "not Model Serving" in text
