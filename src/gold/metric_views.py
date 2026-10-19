"""Databricks metric views over CareStaff gold. Workspace-only — DuckDB cannot host these.

Source tables use the Lakeflow `gold_*` names in one schema. Attrition / shortage
views need notebook 07 score tables. Coverage and roster views need pipeline gold only.
"""

from __future__ import annotations

OPS_VIEWS = ("carestaff_unit_coverage", "carestaff_as_of_roster")
SCORE_VIEWS = ("carestaff_attrition_risk", "carestaff_unit_shortage")


def _view_sql(catalog: str, schema: str, name: str, yaml_body: str) -> str:
    fqn = f"{catalog}.{schema}.{name}"
    return (
        f"CREATE OR REPLACE VIEW {fqn}\n"
        "WITH METRICS\n"
        "LANGUAGE YAML\n"
        "AS $$\n"
        f"{yaml_body.strip()}\n"
        "$$"
    )


def coverage_yaml(catalog: str, schema: str) -> str:
    src = f"{catalog}.{schema}.gold_unit_day_coverage"
    return f"""
version: 1.1
comment: "Unit-day coverage. Shortage day if coverage_ratio < 0.90 or open_shift_share > 0.10. Planning threshold, not a clinical standard."
source: {src}
fields:
  - name: department_id
    expr: department_id
  - name: coverage_date
    expr: coverage_date
  - name: flu_season_flag
    expr: flu_season_flag
measures:
  - name: required_hours
    expr: SUM(required_hours)
  - name: productive_hours
    expr: SUM(productive_hours)
  - name: overtime_hours
    expr: SUM(overtime_hours)
  - name: unplanned_absence_hours
    expr: SUM(unplanned_absence_hours)
  - name: coverage_ratio
    expr: SUM(productive_hours) / NULLIF(SUM(required_hours), 0)
    comment: "productive_hours / required_hours"
  - name: open_shift_share
    expr: SUM(open_heads) / NULLIF(SUM(required_heads), 0)
    comment: "open_heads / required_heads"
  - name: shortage_day_count
    expr: SUM(CASE WHEN is_shortage_day THEN 1 ELSE 0 END)
  - name: trailing_gap_hours
    expr: SUM(GREATEST(required_hours - productive_hours, 0))
"""


def roster_yaml(catalog: str, schema: str) -> str:
    src = f"{catalog}.{schema}.gold_employee_month_features"
    return f"""
version: 1.1
comment: "As-of roster from gold_employee_month_features (is_inference_snapshot). Observed labels are inference_demo_oracle."
source: {src}
filter: is_inference_snapshot = true
fields:
  - name: role_code
    expr: role_code
  - name: department_id
    expr: department_id
  - name: facility_id
    expr: facility_id
  - name: tenure_band
    expr: tenure_band
  - name: primary_shift_code
    expr: primary_shift_code
measures:
  - name: active_headcount
    expr: COUNT(DISTINCT employee_id)
  - name: mean_ot_hours_30d
    expr: AVG(ot_hours_30d)
  - name: mean_swap_count_90d
    expr: AVG(swap_count_90d)
  - name: mean_nights_share_90d
    expr: AVG(nights_share_90d)
  - name: observed_voluntary_90d
    expr: SUM(CAST(label_voluntary_90d AS INT))
    comment: "Generator labels after as_of. Not available in production at inference time."
"""


def attrition_yaml(catalog: str, schema: str) -> str:
    src = f"{catalog}.{schema}.gold_employee_risk_scores"
    return f"""
version: 1.1
comment: "Planning attrition list. high_risk is top 15% by p(voluntary 90d), not an employment decision. Dollars are role-average assumptions."
source: {src}
fields:
  - name: role_code
    expr: role_code
  - name: department_id
    expr: department_id
  - name: facility_id
    expr: facility_id
  - name: tenure_band
    expr: tenure_band
  - name: primary_shift_code
    expr: primary_shift_code
  - name: high_risk_flag
    expr: high_risk_flag
measures:
  - name: scored_headcount
    expr: COUNT(DISTINCT employee_id)
  - name: high_risk_headcount
    expr: SUM(CASE WHEN high_risk_flag THEN 1 ELSE 0 END)
  - name: mean_p_voluntary_90d
    expr: AVG(p_voluntary_90d)
  - name: planning_attrition_exposure_usd
    expr: SUM(CASE WHEN high_risk_flag THEN planning_replacement_usd ELSE 0 END)
    comment: "High-risk headcount x role avg salary x replacement 1.0. Not measured savings."
"""


def shortage_yaml(catalog: str, schema: str) -> str:
    src = f"{catalog}.{schema}.gold_unit_shortage_forecast"
    return f"""
version: 1.1
comment: "14-day unit shortage forecast. Flagged units are a planning list. Seed is chronically short."
source: {src}
fields:
  - name: department_id
    expr: department_id
  - name: predicted_shortage_flag
    expr: predicted_shortage_flag
measures:
  - name: unit_count
    expr: COUNT(DISTINCT department_id)
  - name: predicted_shortage_units_14d
    expr: SUM(CASE WHEN predicted_shortage_flag THEN 1 ELSE 0 END)
  - name: mean_p_shortage_14d
    expr: AVG(p_shortage_14d)
  - name: planning_coverage_exposure_usd
    expr: SUM(planning_coverage_exposure_usd)
    comment: "Flagged-unit gap hours x agency hourly. Planning assumption, not savings."
"""


def metric_view_sql(catalog: str, schema: str) -> dict[str, str]:
    builders = {
        "carestaff_unit_coverage": coverage_yaml,
        "carestaff_as_of_roster": roster_yaml,
        "carestaff_attrition_risk": attrition_yaml,
        "carestaff_unit_shortage": shortage_yaml,
    }
    return {name: _view_sql(catalog, schema, name, body(catalog, schema)) for name, body in builders.items()}


def sample_queries(catalog: str, schema: str) -> dict[str, str]:
    c = f"{catalog}.{schema}"
    return {
        "carestaff_unit_coverage": f"""
SELECT department_id,
       MEASURE(coverage_ratio),
       MEASURE(open_shift_share),
       MEASURE(shortage_day_count),
       MEASURE(overtime_hours)
FROM {c}.carestaff_unit_coverage
GROUP BY department_id
ORDER BY MEASURE(shortage_day_count) DESC
""",
        "carestaff_as_of_roster": f"""
SELECT role_code,
       MEASURE(active_headcount),
       MEASURE(mean_ot_hours_30d),
       MEASURE(observed_voluntary_90d)
FROM {c}.carestaff_as_of_roster
GROUP BY role_code
""",
        "carestaff_attrition_risk": f"""
SELECT role_code,
       MEASURE(high_risk_headcount),
       MEASURE(mean_p_voluntary_90d),
       MEASURE(planning_attrition_exposure_usd)
FROM {c}.carestaff_attrition_risk
GROUP BY role_code
""",
        "carestaff_unit_shortage": f"""
SELECT MEASURE(predicted_shortage_units_14d),
       MEASURE(mean_p_shortage_14d),
       MEASURE(planning_coverage_exposure_usd)
FROM {c}.carestaff_unit_shortage
""",
    }
