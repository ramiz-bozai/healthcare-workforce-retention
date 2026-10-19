"""Train and score CareStaff models from Unity Catalog gold_* tables.

Lakeflow publishes operational gold only. This job reads those tables as pandas,
runs the same `run_models` path as local DuckDB, then writes score / what-if
tables back to the same schema. It does not start Model Serving.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from data_generation.config import load_config
from src.ml.run import ModelRun, run_models

INPUT_TABLES = (
    ("gold", "employee_month_features"),
    ("gold", "unit_week_features"),
    ("gold", "unit_day_coverage"),
    ("gold", "role_cost_assumptions"),
    ("gold", "executive_kpis"),
    ("gold", "metric_catalog"),
    ("silver", "employees"),
)

OUTPUT_TABLES = (
    "employee_risk_scores",
    "unit_shortage_forecast",
    "model_feature_importances",
    "model_fairness_slices",
    "model_calibration_bins",
    "model_metrics",
    "exec_brief",
    "whatif_scenarios",
    "recommended_actions",
    "action_summary",
    "metric_catalog",
)

PIPELINE_OWNED_GOLD = frozenset(
    {
        "snapshot_calendar",
        "role_cost_assumptions",
        "unit_day_coverage",
        "unit_week_features",
        "employee_month_features",
        "executive_kpis",
    }
)


def uc_table(layer: str, name: str) -> str:
    return f"{layer}_{name}"


def uc_fqn(catalog: str, schema: str, layer: str, name: str) -> str:
    return f"{catalog}.{schema}.{uc_table(layer, name)}"


def frames_from_connection(con) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for layer, name in INPUT_TABLES:
        if layer == "silver" and name == "employees":
            frames["silver.employees"] = con.execute(
                "SELECT employee_id, display_name FROM silver.employees"
            ).fetchdf()
        else:
            frames[f"{layer}.{name}"] = con.execute(f"SELECT * FROM {layer}.{name}").fetchdf()
    return frames


def frames_from_spark(spark, catalog: str, schema: str) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for layer, name in INPUT_TABLES:
        fqn = uc_fqn(catalog, schema, layer, name)
        try:
            df = spark.table(fqn)
            if layer == "silver" and name == "employees":
                df = df.select("employee_id", "display_name")
            frames[f"{layer}.{name}"] = df.toPandas()
        except Exception as exc:  # spark.table raises AnalysisException
            missing.append(f"{fqn} ({exc})")
    if missing:
        raise FileNotFoundError(
            "Workspace scoring needs Lakeflow gold/silver tables. Missing:\n- "
            + "\n- ".join(missing)
        )
    return frames


def duckdb_from_frames(frames: dict[str, pd.DataFrame]):
    required = {f"{layer}.{name}" for layer, name in INPUT_TABLES}
    absent = sorted(required - set(frames))
    if absent:
        raise FileNotFoundError(f"Missing frames for {absent}")
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA gold")
    con.execute("CREATE SCHEMA silver")
    for qual, pdf in frames.items():
        view = "_src"
        con.register(view, pdf)
        con.execute(f"CREATE TABLE {qual} AS SELECT * FROM {view}")
        con.unregister(view)
    return con


def run_from_frames(
    frames: dict[str, pd.DataFrame],
    *,
    profile: str = "seed",
    model_dir: Path | None = None,
    log_mlflow: bool = False,
) -> tuple[ModelRun, object]:
    cfg = load_config(profile)
    con = duckdb_from_frames(frames)
    try:
        result = run_models(con, cfg, log_mlflow=log_mlflow, model_dir=model_dir)
        return result, con
    except Exception:
        con.close()
        raise


def output_frames(con) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for name in OUTPUT_TABLES:
        out[name] = con.execute(f"SELECT * FROM gold.{name}").fetchdf()
    return out


def write_frames_to_spark(spark, catalog: str, schema: str, frames: dict[str, pd.DataFrame]) -> list[str]:
    written: list[str] = []
    for name, pdf in frames.items():
        if name in PIPELINE_OWNED_GOLD:
            raise ValueError(f"Refusing to overwrite Lakeflow-owned gold table {name}")
        fqn = uc_fqn(catalog, schema, "gold", name)
        spark.createDataFrame(pdf).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(fqn)
        written.append(fqn)
    return written


def run_workspace_models(
    spark,
    *,
    catalog: str,
    schema: str,
    model_dir: str | Path | None = None,
    profile: str = "seed",
) -> ModelRun:
    dest = Path(model_dir) if model_dir else None
    if dest is not None:
        dest.mkdir(parents=True, exist_ok=True)
    frames = frames_from_spark(spark, catalog, schema)
    result, con = run_from_frames(frames, profile=profile, model_dir=dest, log_mlflow=False)
    try:
        write_frames_to_spark(spark, catalog, schema, output_frames(con))
    finally:
        con.close()
    return result
