"""Lakeflow / DLT bronze landing. Workspace-only — not executed locally.

Reads CSV from a UC Volume. Payload columns remain strings; metadata columns
match the local DuckDB bronze contract: _ingest_ts, _source_path, _record_origin.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_repo_on_path() -> None:
    """Lakeflow isolates each notebook. Sibling `import _bootstrap` will not work."""
    conf_root = ""
    try:
        conf_root = str(spark.conf.get("repo_root", "") or "")  # noqa: F821
    except Exception:
        conf_root = ""
    try:
        file_path = Path(__file__).resolve()
    except NameError:
        file_path = None
    seen: set[Path] = set()
    ordered: list[Path] = []

    def _add(raw: object) -> None:
        if not raw:
            return
        path = Path(str(raw))
        try:
            path = path.expanduser().resolve()
        except OSError:
            pass
        for item in (path, *path.parents):
            if item not in seen:
                seen.add(item)
                ordered.append(item)

    _add(conf_root)
    _add(file_path)
    _add(Path.cwd())
    for item in ordered:
        if (item / "src").is_dir() and (item / "data_generation").is_dir():
            text = str(item)
            if text not in sys.path:
                sys.path.insert(0, text)
            return
    raise ModuleNotFoundError(
        "Could not find repo root (src/ and data_generation/). "
        "Set pipeline configuration repo_root to the Git folder path, "
        "for example /Workspace/Users/<you>/healthcare-workforce-retention"
    )


_ensure_repo_on_path()

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
