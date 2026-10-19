from __future__ import annotations

from pathlib import Path

from src.gold.metric_views import (
    OPS_VIEWS,
    SCORE_VIEWS,
    metric_view_sql,
    sample_queries,
)

ROOT = Path(__file__).resolve().parents[1]


def test_metric_views_are_databricks_yaml_not_lakeflow():
    ddls = metric_view_sql("healthcare_ops", "carestaff_insight")
    assert set(ddls) == set(OPS_VIEWS) | set(SCORE_VIEWS)
    for name, sql in ddls.items():
        assert sql.startswith("CREATE OR REPLACE VIEW healthcare_ops.carestaff_insight.")
        assert "WITH METRICS" in sql
        assert "LANGUAGE YAML" in sql
        assert "version: 1.1" in sql
        assert "gold_" in sql
        assert "MEASURE(" not in sql  # definition, not a query
    samples = sample_queries("healthcare_ops", "carestaff_insight")
    for name, q in samples.items():
        assert "MEASURE(" in q
        assert name in q or "carestaff_" in q
    recipe = ROOT / "pipelines" / "carestaff_insight"
    assert not (recipe / "08_metric_views.py").exists()
    nb = (ROOT / "notebooks" / "08_metric_views.py").read_text()
    assert "metric_view_sql" in nb
    assert "WITH METRICS" not in nb or "MEASURE" in nb


def test_ops_views_point_at_pipeline_gold():
    ddls = metric_view_sql("c", "s")
    assert "c.s.gold_unit_day_coverage" in ddls["carestaff_unit_coverage"]
    assert "c.s.gold_employee_month_features" in ddls["carestaff_as_of_roster"]
    assert "is_inference_snapshot = true" in ddls["carestaff_as_of_roster"]
    assert "c.s.gold_employee_risk_scores" in ddls["carestaff_attrition_risk"]
    assert "employment decision" in ddls["carestaff_attrition_risk"].lower() or "not an employment" in ddls[
        "carestaff_attrition_risk"
    ].lower()
