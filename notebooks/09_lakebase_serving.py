# Databricks notebook source
# MAGIC %md
# MAGIC # Lakebase operational serving layer
# MAGIC
# MAGIC Run after `07_workspace_models.py`. This notebook enables Change Data Feed and
# MAGIC creates three triggered synced tables in Lakebase Autoscaling:
# MAGIC
# MAGIC - `gold_exec_brief` → `gold_exec_brief_serving`
# MAGIC - `gold_employee_risk_scores` → `gold_employee_risk_scores_serving`
# MAGIC - `gold_unit_shortage_forecast` → `gold_unit_shortage_forecast_serving`
# MAGIC
# MAGIC The Databricks App reads these low-latency Postgres copies. Supporting analytical
# MAGIC tables and Genie continue to use the SQL warehouse.
# MAGIC
# MAGIC Before running, create a Lakebase Autoscaling project and database. Copy the branch
# MAGIC resource path (`projects/.../branches/...`) and database name into the widgets.

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81" --quiet

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------

import re

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service.postgres import (
    SyncedTable,
    SyncedTableSyncedTableSpec,
    SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy,
)

dbutils.widgets.text("catalog", "healthcare_ops")  # noqa: F821
dbutils.widgets.text("schema", "carestaff_insight")  # noqa: F821
dbutils.widgets.text("branch", "projects/carestaff-insight/branches/production")  # noqa: F821
dbutils.widgets.text("postgres_database", "carestaff")  # noqa: F821

catalog = dbutils.widgets.get("catalog").strip()  # noqa: F821
schema = dbutils.widgets.get("schema").strip()  # noqa: F821
branch = dbutils.widgets.get("branch").strip()  # noqa: F821
postgres_database = dbutils.widgets.get("postgres_database").strip()  # noqa: F821

for value, label in ((catalog, "catalog"), (schema, "schema"), (postgres_database, "database")):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", value):
        raise ValueError(f"Invalid {label}: {value!r}")
if not re.fullmatch(r"projects/[a-z][a-z0-9-]{2,62}/branches/[a-z][a-z0-9-]{2,62}", branch):
    raise ValueError(f"Invalid Lakebase branch resource path: {branch!r}")

TABLES = {
    "gold_exec_brief": ("gold_exec_brief_serving", ["as_of_date"]),
    "gold_employee_risk_scores": ("gold_employee_risk_scores_serving", ["employee_id"]),
    "gold_unit_shortage_forecast": ("gold_unit_shortage_forecast_serving", ["department_id"]),
}

# COMMAND ----------

for source_name in TABLES:
    source = f"`{catalog}`.`{schema}`.`{source_name}`"
    spark.sql(  # noqa: F821
        f"ALTER TABLE {source} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)"
    )
    print("CDF enabled:", source)

# COMMAND ----------

client = WorkspaceClient()

for source_name, (serving_name, primary_keys) in TABLES.items():
    synced_id = f"{catalog}.{schema}.{serving_name}"
    resource_name = f"synced_tables/{synced_id}"
    try:
        existing = client.postgres.get_synced_table(name=resource_name)
        print("Already exists:", existing.name)
        continue
    except NotFound:
        pass

    created = client.postgres.create_synced_table(
        synced_table=SyncedTable(
            spec=SyncedTableSyncedTableSpec(
                source_table_full_name=f"{catalog}.{schema}.{source_name}",
                branch=branch,
                postgres_database=postgres_database,
                primary_key_columns=primary_keys,
                scheduling_policy=(
                    SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy.TRIGGERED
                ),
                create_database_objects_if_missing=True,
            )
        ),
        synced_table_id=synced_id,
    ).wait()
    print("Created:", created.name)

print("Lakebase serving tables are ready.")
print("Attach this database to the App with resource key: postgres")
print("After rerunning notebook 07, trigger each synced table before the demo.")
