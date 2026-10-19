"""Land CSVs as bronze tables. All payload columns stay VARCHAR (raw)."""

from __future__ import annotations

from pathlib import Path

import duckdb

from data_generation.schema import TABLE_ORDER
from src.common.paths import FIXTURE_DIR, SEED_DIR

BRONZE_META_COLS = ("_ingest_ts", "_source_path", "_record_origin")


def ingest_bronze(
    con: duckdb.DuckDBPyConnection,
    source_dir: Path | None = None,
    fixture_dir: Path | None = None,
    include_fixtures: bool = True,
) -> dict[str, int]:
    source_dir = source_dir or SEED_DIR
    fixture_dir = fixture_dir or FIXTURE_DIR
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    counts: dict[str, int] = {}
    for table in TABLE_ORDER:
        csv_path = source_dir / f"{table}.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"Missing bronze source {csv_path}")
        src = csv_path.resolve().as_posix()
        con.execute(f"DROP TABLE IF EXISTS bronze.{table}")
        con.execute(
            f"""
            CREATE TABLE bronze.{table} AS
            SELECT
              *,
              CAST(current_timestamp AS TIMESTAMP) AS _ingest_ts,
              '{src}' AS _source_path,
              'seed' AS _record_origin
            FROM read_csv('{src}', header=true, all_varchar=true)
            """
        )
        fixture_path = fixture_dir / f"{table}.csv"
        if include_fixtures and fixture_path.exists():
            fx = fixture_path.resolve().as_posix()
            con.execute(
                f"""
                INSERT INTO bronze.{table}
                SELECT
                  *,
                  CAST(current_timestamp AS TIMESTAMP) AS _ingest_ts,
                  '{fx}' AS _source_path,
                  'dq_fixture' AS _record_origin
                FROM read_csv('{fx}', header=true, all_varchar=true)
                """
            )
        counts[table] = int(con.execute(f"SELECT COUNT(*) FROM bronze.{table}").fetchone()[0])
    return counts
