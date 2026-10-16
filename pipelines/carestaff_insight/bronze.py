"""Lakeflow / DLT bronze landing. Workspace-only — not executed locally.

Reads CSV from a UC Volume. Payload columns remain strings; metadata columns
match the local DuckDB bronze contract: _ingest_ts, _source_path, _record_origin.
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  — repo root on sys.path

try:
    import dlt
    from pyspark.sql import functions as F
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pipelines/carestaff_insight is the Databricks path. Run `python -m src.pipeline` locally."
    ) from exc

from data_generation.schema import TABLE_ORDER

DEFAULT_VOLUME = "/Volumes/healthcare_ops/bronze/workforce_landing"


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
