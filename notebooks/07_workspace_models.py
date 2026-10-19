# Databricks notebook source
# MAGIC %md
# MAGIC # Workspace models (you click Run)
# MAGIC
# MAGIC Lakeflow gold is operational only. This notebook trains the same HistGradientBoosting
# MAGIC models as `python -m src.ml`, writes score / what-if tables into the **same**
# MAGIC pipeline schema (`gold_exec_brief`, `gold_employee_risk_scores`, …), and saves
# MAGIC joblib files to a Volume if you set `model_volume`.
# MAGIC
# MAGIC This is **not** Model Serving. `ai.model_serving_live` stays false.
# MAGIC
# MAGIC Order: pipeline Start (done) → this notebook → Databricks App / Genie later.
# MAGIC
# MAGIC Open it from the Git folder. Do **not** add this file to the Lakeflow source directory.

# COMMAND ----------

# MAGIC %pip install duckdb scikit-learn joblib pyyaml pandas numpy --quiet

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------

from __future__ import annotations

import sys
from pathlib import Path

dbutils.widgets.text("catalog", "healthcare_ops")  # noqa: F821
dbutils.widgets.text("schema", "carestaff_insight")  # noqa: F821
dbutils.widgets.text("model_volume", "")  # noqa: F821


def _repo_root() -> Path:
    here = Path.cwd().resolve()
    for cand in (here, *here.parents):
        if (cand / "src" / "ml" / "run.py").is_file() and (cand / "app.py").is_file():
            return cand
    raise FileNotFoundError(
        "Could not see src/ml from the notebook working directory. "
        "Open this file from the Git folder healthcare-workforce-retention, "
        "not as a copy outside the repo."
    )


ROOT = _repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ml.workspace_run import run_workspace_models  # noqa: E402

catalog = dbutils.widgets.get("catalog").strip()  # noqa: F821
schema = dbutils.widgets.get("schema").strip()  # noqa: F821
model_volume = dbutils.widgets.get("model_volume").strip()  # noqa: F821

print("Repo:", ROOT)
print("Writing scores to:", f"{catalog}.{schema}.gold_*")
print("Model volume:", model_volume or "(tmp on driver; predict-in-app needs a Volume)")

result = run_workspace_models(
    spark,  # noqa: F821
    catalog=catalog,
    schema=schema,
    model_dir=model_volume or None,
)

brief = result.exec_brief.iloc[0]
print("as_of:", brief.get("as_of_date"))
print("active_headcount:", brief.get("active_headcount"))
print("high_risk_headcount:", brief.get("high_risk_headcount"))
print("predicted_shortage_units_14d:", brief.get("predicted_shortage_units_14d"))
print("applied_count must be 0; status pending_human_review")
print("Not Model Serving. Next: Databricks App (React) and attach the Genie space as an App resource.")
