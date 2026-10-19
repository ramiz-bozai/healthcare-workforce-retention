# Databricks notebook source
# MAGIC %md
# MAGIC # Metric views (Databricks-only)
# MAGIC
# MAGIC Creates Unity Catalog metric views over gold. Query them with `MEASURE(...)`.
# MAGIC Point Genie / AI/BI at these, not at a pile of raw tables.
# MAGIC
# MAGIC `carestaff_unit_coverage` and `carestaff_as_of_roster` work off pipeline gold.
# MAGIC `carestaff_attrition_risk` and `carestaff_unit_shortage` need notebook 07 first.
# MAGIC
# MAGIC Open from the Git folder. Not Lakeflow source.

# COMMAND ----------

from __future__ import annotations

import sys
from pathlib import Path

dbutils.widgets.text("catalog", "healthcare_ops")  # noqa: F821
dbutils.widgets.text("schema", "carestaff_insight")  # noqa: F821


def _repo_root() -> Path:
    here = Path.cwd().resolve()
    for cand in (here, *here.parents):
        if (cand / "src" / "gold" / "metric_views.py").is_file():
            return cand
    raise FileNotFoundError("Open this notebook from the Git folder.")


ROOT = _repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.gold.metric_views import (  # noqa: E402
    OPS_VIEWS,
    SCORE_VIEWS,
    metric_view_sql,
    sample_queries,
)

catalog = dbutils.widgets.get("catalog").strip()  # noqa: F821
schema = dbutils.widgets.get("schema").strip()  # noqa: F821
fqn_prefix = f"{catalog}.{schema}"

needed = {
    "carestaff_unit_coverage": f"{fqn_prefix}.gold_unit_day_coverage",
    "carestaff_as_of_roster": f"{fqn_prefix}.gold_employee_month_features",
    "carestaff_attrition_risk": f"{fqn_prefix}.gold_employee_risk_scores",
    "carestaff_unit_shortage": f"{fqn_prefix}.gold_unit_shortage_forecast",
}

ddls = metric_view_sql(catalog, schema)
created = []
skipped = []
for name, ddl in ddls.items():
    src = needed[name]
    try:
        spark.table(src)  # noqa: F821
    except Exception:
        skipped.append(f"{name} (missing {src})")
        continue
    spark.sql(ddl)  # noqa: F821
    created.append(f"{fqn_prefix}.{name}")

print("created:", created)
print("skipped:", skipped)
print()
print("Example — coverage by unit:")
print(sample_queries(catalog, schema)["carestaff_unit_coverage"].strip())
print()
print("Genie: add the carestaff_* metric views plus gold_exec_brief if 07 has run.")
