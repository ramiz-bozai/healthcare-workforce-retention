"""Train both models, score as_of, optionally log to local MLflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from data_generation.config import GenerationConfig, load_config
from src.common.paths import DEFAULT_DUCKDB, MLFLOW_DB, MODEL_DIR
from src.ml.contract import (
    ATTRITION_CATEGORICAL,
    ATTRITION_FAIRNESS_SLICES,
    ATTRITION_NUMERIC,
    ATTRITION_TARGET,
    SHORTAGE_CATEGORICAL,
    SHORTAGE_FAIRNESS_SLICES,
    SHORTAGE_NUMERIC,
    SHORTAGE_TARGET,
    assert_feature_safety,
)
from src.ml.predict import write_policy
from src.ml.score import metrics_table, score_attrition, score_shortage, write_gold_scores
from src.ml.train import FittedModel, fit_model, production_honest_attrition, production_honest_shortage
from src.ml.whatif import recommend_and_simulate, write_whatif


@dataclass
class ModelRun:
    attrition: FittedModel
    shortage: FittedModel
    attrition_scores: pd.DataFrame
    shortage_scores: pd.DataFrame
    exec_brief: pd.DataFrame
    whatif_scenarios: pd.DataFrame
    recommended_actions: pd.DataFrame
    mlflow_run_id: str | None


def _finite_metrics(prefix: str, values: dict[str, float]) -> dict[str, float]:
    out = {}
    for key, value in values.items():
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(number):
            out[f"{prefix}_{key}"] = number
    return out


def default_tracking_uri() -> str:
    MLFLOW_DB.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{MLFLOW_DB.resolve()}"


def _log_mlflow(attrition: FittedModel, shortage: FittedModel, tracking_uri: str, as_of: str) -> str:
    import os

    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    import mlflow
    import mlflow.sklearn

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("carestaff-insight")
    with mlflow.start_run(run_name=f"seed-{as_of}") as parent:
        mlflow.set_tags(
            {
                "as_of": as_of,
                "family": "hist_gradient_boosting",
                "not_an_employment_decision": "true",
            }
        )
        for fitted in (attrition, shortage):
            with mlflow.start_run(run_name=fitted.name, nested=True):
                mlflow.log_metrics(_finite_metrics("valid", fitted.metrics["valid"]))
                mlflow.log_metrics(_finite_metrics("train", fitted.metrics["train"]))
                if "valid_persistence_baseline" in fitted.metrics:
                    mlflow.log_metrics(
                        _finite_metrics("valid_persistence", fitted.metrics["valid_persistence_baseline"])
                    )
                mlflow.sklearn.log_model(
                    fitted.pipeline,
                    name="model",
                    serialization_format="cloudpickle",
                    pyfunc_predict_fn="predict_proba",
                )
        return parent.info.run_id


def run_models(
    con,
    cfg: GenerationConfig | None = None,
    *,
    log_mlflow: bool = True,
    tracking_uri: str | None = None,
    model_dir: Path | None = None,
) -> ModelRun:
    cfg = cfg or load_config("seed")
    labels = cfg.raw["labels"]
    models_cfg = cfg.raw["models"]
    as_of = cfg.as_of_date.isoformat()
    assert_feature_safety(ATTRITION_NUMERIC + ATTRITION_CATEGORICAL)
    assert_feature_safety(SHORTAGE_NUMERIC + SHORTAGE_CATEGORICAL)
    assert labels["attrition_positive_class"] == "voluntary"

    employees = con.execute(
        "SELECT * FROM gold.employee_month_features"
    ).fetchdf()
    weeks = con.execute("SELECT * FROM gold.unit_week_features").fetchdf()
    costs = con.execute("SELECT * FROM gold.role_cost_assumptions").fetchdf()
    names = con.execute("SELECT employee_id, display_name FROM silver.employees").fetchdf()
    gap_hours = con.execute(
        f"""
        SELECT department_id,
               SUM(GREATEST(required_hours - productive_hours, 0)) AS trailing_gap_hours_14d
        FROM gold.unit_day_coverage
        WHERE coverage_date > DATE '{as_of}' - INTERVAL 14 DAY
          AND coverage_date <= DATE '{as_of}'
        GROUP BY 1
        """
    ).fetchdf()
    agency_hourly = float(costs["agency_hourly_usd"].mean())

    att_train, att_valid, att_inf = production_honest_attrition(employees, as_of)
    sh_train, sh_valid, sh_latest = production_honest_shortage(weeks)

    attrition = fit_model(
        name="attrition",
        train=att_train,
        valid=att_valid,
        numeric=ATTRITION_NUMERIC,
        categorical=ATTRITION_CATEGORICAL,
        target=ATTRITION_TARGET,
        class_weight="balanced",
        fairness_cols=ATTRITION_FAIRNESS_SLICES,
        high_risk_quantile=float(models_cfg["attrition_high_risk_quantile"]),
        permutation_repeats=int(models_cfg["permutation_repeats"]),
    )
    shortage = fit_model(
        name="shortage",
        train=sh_train,
        valid=sh_valid,
        numeric=SHORTAGE_NUMERIC,
        categorical=SHORTAGE_CATEGORICAL,
        target=SHORTAGE_TARGET,
        class_weight=None,
        fairness_cols=SHORTAGE_FAIRNESS_SLICES,
        high_risk_quantile=0.5,
        permutation_repeats=int(models_cfg["permutation_repeats"]),
    )

    att_scores, att_oracle = score_attrition(
        attrition,
        att_inf,
        costs,
        names,
        quantile=float(models_cfg["attrition_high_risk_quantile"]),
    )
    sh_scores, sh_summary = score_shortage(
        shortage,
        sh_latest,
        min_probability=float(models_cfg["shortage_flag_min_probability"]),
        gap_hours=gap_hours,
        agency_hourly=agency_hourly,
    )

    metrics_rows = pd.concat(
        [
            metrics_table(attrition, att_oracle),
            metrics_table(shortage, sh_summary),
        ],
        ignore_index=True,
    )
    fairness = pd.concat(
        [df for df in (attrition.fairness, shortage.fairness) if len(df)],
        ignore_index=True,
    )
    calibration = pd.concat([attrition.calibration_bins, shortage.calibration_bins], ignore_index=True)
    importances = pd.concat([attrition.importances, shortage.importances], ignore_index=True)

    brief = write_gold_scores(
        con,
        attrition=att_scores,
        shortage=sh_scores,
        importances=importances,
        fairness=fairness,
        calibration=calibration,
        metrics_rows=metrics_rows,
        as_of=as_of,
        assumption_note=str(costs["assumption_note"].iloc[0]),
    )

    dest = Path(model_dir or MODEL_DIR)
    dest.mkdir(parents=True, exist_ok=True)
    joblib.dump(attrition.pipeline, dest / "attrition.joblib")
    joblib.dump(shortage.pipeline, dest / "shortage.joblib")
    flagged = att_scores["high_risk_flag"].astype(bool)
    high_risk_cut = float(att_scores.loc[flagged, "p_voluntary_90d"].min()) if flagged.any() else 1.0
    shortage_cut = float(models_cfg["shortage_flag_min_probability"])
    write_policy(
        dest,
        {
            "as_of": as_of,
            "attrition_high_risk_quantile": float(models_cfg["attrition_high_risk_quantile"]),
            "attrition_high_risk_cut": high_risk_cut,
            "shortage_flag_min_probability": shortage_cut,
            "not_an_employment_decision": True,
            "serving": "in_process_predict",
        },
    )
    scenarios, actions = recommend_and_simulate(
        emp=att_inf,
        weeks=sh_latest,
        att_scores=att_scores,
        sh_scores=sh_scores,
        attrition=attrition,
        shortage=shortage,
        cfg=cfg,
        as_of=as_of,
        agency_hourly=agency_hourly,
        high_risk_cut=high_risk_cut,
        shortage_cut=shortage_cut,
    )
    write_whatif(con, scenarios, actions, as_of)

    run_id = None
    if log_mlflow:
        run_id = _log_mlflow(
            attrition,
            shortage,
            tracking_uri=tracking_uri or default_tracking_uri(),
            as_of=as_of,
        )

    return ModelRun(
        attrition=attrition,
        shortage=shortage,
        attrition_scores=att_scores,
        shortage_scores=sh_scores,
        exec_brief=brief,
        whatif_scenarios=scenarios,
        recommended_actions=actions,
        mlflow_run_id=run_id,
    )


def run_from_path(
    duckdb_path: Path | None = None,
    profile: str = "seed",
    *,
    log_mlflow: bool = True,
) -> ModelRun:
    import duckdb

    from src.pipeline.local_run import run_local

    cfg = load_config(profile)
    db_path = duckdb_path or DEFAULT_DUCKDB
    if not db_path.exists():
        built = run_local(profile=profile, duckdb_path=db_path, include_fixtures=False)
        built.con.close()
    con = duckdb.connect(str(db_path))
    try:
        return run_models(con, cfg, log_mlflow=log_mlflow)
    finally:
        con.close()
