"""Apply fitted models at as_of and write gold score tables. Not an employment decision."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.ml.contract import MODEL_CATALOG_ROWS
from src.ml.features import feature_frame
from src.ml.train import FittedModel, _high_risk_from_quantile, _proba, classification_metrics, local_drivers


def score_attrition(
    model: FittedModel,
    inference: pd.DataFrame,
    costs: pd.DataFrame,
    names: pd.DataFrame,
    quantile: float,
) -> tuple[pd.DataFrame, dict[str, float]]:
    X = feature_frame(inference, model.numeric, model.categorical)
    p = _proba(model.pipeline, X)
    high_risk = _high_risk_from_quantile(p, quantile)
    ranked = pd.Series(p).rank(ascending=False, method="first").astype(int)
    rows = inference.reset_index(drop=True).copy()
    rows["p_voluntary_90d"] = p
    rows["high_risk_flag"] = high_risk
    rows["risk_rank"] = ranked.to_numpy()
    drivers = []
    for _, row in rows.iterrows():
        drivers.append(local_drivers(row, model.importances, model.medians, model.risk_direction))
    rows["driver_1"] = [d[0] if len(d) > 0 else "" for d in drivers]
    rows["driver_2"] = [d[1] if len(d) > 1 else "" for d in drivers]
    rows["driver_3"] = [d[2] if len(d) > 2 else "" for d in drivers]
    rows = rows.merge(costs[["role_code", "avg_annual_salary_usd", "replacement_multiplier"]], on="role_code", how="left")
    rows["planning_replacement_usd"] = rows["avg_annual_salary_usd"] * rows["replacement_multiplier"]
    rows = rows.merge(names, on="employee_id", how="left")
    y = rows["label_voluntary_90d"].astype(int).to_numpy()
    oracle = classification_metrics(y, p)
    oracle["high_risk_n"] = float(high_risk.sum())
    oracle["high_risk_rate"] = float(high_risk.mean())
    if y.sum():
        oracle["high_risk_recall"] = float(high_risk[y == 1].mean())
        oracle["leaver_mean_p"] = float(p[y == 1].mean())
        oracle["stayer_mean_p"] = float(p[y == 0].mean())
    scored = rows[
        [
            "employee_id",
            "display_name",
            "snapshot_date",
            "role_code",
            "department_id",
            "facility_id",
            "tenure_band",
            "primary_shift_code",
            "p_voluntary_90d",
            "high_risk_flag",
            "risk_rank",
            "driver_1",
            "driver_2",
            "driver_3",
            "planning_replacement_usd",
            "label_voluntary_90d",
        ]
    ].sort_values("risk_rank")
    return scored, oracle


def score_shortage(
    model: FittedModel,
    latest: pd.DataFrame,
    min_probability: float,
    gap_hours: pd.DataFrame,
    agency_hourly: float,
) -> tuple[pd.DataFrame, dict[str, float]]:
    X = feature_frame(latest, model.numeric, model.categorical)
    p = _proba(model.pipeline, X)
    rows = latest.reset_index(drop=True).copy()
    rows["p_shortage_14d"] = p
    rows["predicted_shortage_flag"] = p >= min_probability
    rows["shortage_rank"] = pd.Series(p).rank(ascending=False, method="first").astype(int).to_numpy()
    drivers = []
    for _, row in rows.iterrows():
        drivers.append(local_drivers(row, model.importances, model.medians, model.risk_direction))
    rows["driver_1"] = [d[0] if len(d) > 0 else "" for d in drivers]
    rows["driver_2"] = [d[1] if len(d) > 1 else "" for d in drivers]
    rows["driver_3"] = [d[2] if len(d) > 2 else "" for d in drivers]
    rows = rows.merge(gap_hours, on="department_id", how="left")
    rows["trailing_gap_hours_14d"] = rows["trailing_gap_hours_14d"].fillna(0.0)
    rows["planning_coverage_exposure_usd"] = np.where(
        rows["predicted_shortage_flag"],
        rows["trailing_gap_hours_14d"] * agency_hourly,
        0.0,
    )
    scored = rows[
        [
            "department_id",
            "week_start",
            "week_end",
            "avg_coverage_ratio",
            "avg_open_shift_share",
            "is_shortage_week",
            "p_shortage_14d",
            "predicted_shortage_flag",
            "shortage_rank",
            "driver_1",
            "driver_2",
            "driver_3",
            "trailing_gap_hours_14d",
            "planning_coverage_exposure_usd",
            "label_shortage_next_14d",
            "label_window_complete_14d",
        ]
    ].sort_values("shortage_rank")
    summary = {
        "n_units": float(len(scored)),
        "mean_p": float(p.mean()),
        "flagged_units": float(scored["predicted_shortage_flag"].sum()),
        "planning_coverage_exposure_usd": float(scored["planning_coverage_exposure_usd"].sum()),
    }
    return scored, summary


def write_gold_scores(
    con,
    *,
    attrition: pd.DataFrame,
    shortage: pd.DataFrame,
    importances: pd.DataFrame,
    fairness: pd.DataFrame,
    calibration: pd.DataFrame,
    metrics_rows: pd.DataFrame,
    as_of: str,
    assumption_note: str,
) -> pd.DataFrame:
    con.register("_attrition_scores", attrition)
    con.register("_shortage_scores", shortage)
    con.register("_importances", importances)
    con.register("_fairness", fairness)
    con.register("_calibration", calibration)
    con.register("_metrics", metrics_rows)
    con.execute("CREATE OR REPLACE TABLE gold.employee_risk_scores AS SELECT * FROM _attrition_scores")
    con.execute("CREATE OR REPLACE TABLE gold.unit_shortage_forecast AS SELECT * FROM _shortage_scores")
    con.execute("CREATE OR REPLACE TABLE gold.model_feature_importances AS SELECT * FROM _importances")
    con.execute("CREATE OR REPLACE TABLE gold.model_fairness_slices AS SELECT * FROM _fairness")
    con.execute("CREATE OR REPLACE TABLE gold.model_calibration_bins AS SELECT * FROM _calibration")
    con.execute("CREATE OR REPLACE TABLE gold.model_metrics AS SELECT * FROM _metrics")
    catalog = pd.DataFrame(
        MODEL_CATALOG_ROWS,
        columns=["metric_name", "table_name", "grain", "formula", "includes_model"],
    )
    existing = con.execute(
        "SELECT * FROM gold.metric_catalog WHERE includes_model = 0"
    ).fetchdf()
    combined = pd.concat([existing, catalog], ignore_index=True)
    con.register("_catalog_all", combined)
    con.execute("CREATE OR REPLACE TABLE gold.metric_catalog AS SELECT * FROM _catalog_all")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE gold.exec_brief AS
        SELECT
          k.*,
          (SELECT AVG(p_voluntary_90d) FROM gold.employee_risk_scores) AS predicted_attrition_rate_90d,
          (SELECT SUM(CAST(high_risk_flag AS INTEGER)) FROM gold.employee_risk_scores) AS high_risk_headcount,
          (SELECT COALESCE(SUM(planning_replacement_usd), 0)
             FROM gold.employee_risk_scores WHERE high_risk_flag) AS planning_attrition_exposure_usd,
          (SELECT SUM(CAST(predicted_shortage_flag AS INTEGER)) FROM gold.unit_shortage_forecast) AS predicted_shortage_units_14d,
          (SELECT COALESCE(SUM(planning_coverage_exposure_usd), 0) FROM gold.unit_shortage_forecast) AS planning_coverage_exposure_usd,
          DATE '{as_of}' AS scored_as_of,
          'Scores are planning signals. Status is pending_human_review. {assumption_note.replace("'", "''")}' AS model_note
        FROM gold.executive_kpis k
        """
    )
    return con.execute("SELECT * FROM gold.exec_brief").fetchdf()


def metrics_table(model: FittedModel, extra: dict[str, float] | None = None) -> pd.DataFrame:
    rows = []
    for split, values in model.metrics.items():
        for key, value in values.items():
            rows.append({"model": model.name, "split": split, "metric": key, "value": value})
    if extra:
        for key, value in extra.items():
            rows.append({"model": model.name, "split": "inference_demo_oracle", "metric": key, "value": value})
    return pd.DataFrame(rows)


def dump_metrics_json(path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))
