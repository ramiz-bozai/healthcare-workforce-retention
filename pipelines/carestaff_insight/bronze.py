"""Lakeflow / DLT bronze landing. Workspace-only — not executed locally.

Self-contained: stdlib + dlt/pyspark only. Lakeflow isolates each file as a
notebook, so this module must not import `src`, `data_generation`, or a sibling.

Reads CSV from a UC Volume. Payload columns remain strings; metadata columns
match the local DuckDB bronze contract: _ingest_ts, _source_path, _record_origin.
"""

from __future__ import annotations

try:
    import dlt  # Databricks Lakeflow / DLT
except ImportError:
    try:
        from pyspark import pipelines as dlt  # Spark Declarative Pipelines
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "pipelines/carestaff_insight is the Databricks path. "
            "Run `python -m src.pipeline` locally."
        ) from exc

try:
    from pyspark.sql import functions as F
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pipelines/carestaff_insight is the Databricks path. "
        "Run `python -m src.pipeline` locally."
    ) from exc

DEFAULT_VOLUME = "/Volumes/healthcare_ops/bronze/workforce_landing"

TABLE_ORDER = ['facilities', 'departments', 'roles', 'shifts', 'compensation_bands', 'role_cost_assumptions', 'employees', 'schedule_assignments', 'time_cards', 'absences', 'staffing_requirements', 'census_proxy', 'open_positions', 'attrition_events']


def _read_csv(table_name: str):
    volume = spark.conf.get("volume_path", DEFAULT_VOLUME)  # noqa: F821
    path = f"{volume.rstrip('/')}/{table_name}.csv"
    return (
        spark.read.option("header", True)  # noqa: F821
        .option("inferSchema", False)
        .csv(path)
        .withColumn("_ingest_ts", F.current_timestamp())
        .withColumn("_source_path", F.lit(path))
        .withColumn("_record_origin", F.lit("volume"))
    )


def _register_bronze(table_name: str):
    @dlt.table(name=f"bronze_{table_name}", comment=f"Raw {table_name} from Volume CSV")
    def _load():
        return _read_csv(table_name)

    return _load


for _table in TABLE_ORDER:
    _register_bronze(_table)
