"""Stage bronze → typed stg → dq_violations → silver tables (errors quarantined)."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pandas as pd

from data_generation.schema import TABLE_ORDER
from src.silver.rules import SILVER_KEY_SQL, DqRule, load_rules
from src.silver.standardize import all_staging_sql


@dataclass(frozen=True)
class SilverResult:
    staging_counts: dict[str, int]
    silver_counts: dict[str, int]
    violation_counts: dict[str, int]
    violations: pd.DataFrame


def _create_violation_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE OR REPLACE TABLE silver.dq_violations (
            rule_id VARCHAR,
            table_name VARCHAR,
            severity VARCHAR,
            record_key VARCHAR,
            violation_detail VARCHAR,
            description VARCHAR,
            detected_at TIMESTAMP
        )
        """
    )


def _run_rules(con: duckdb.DuckDBPyConnection, rules: list[DqRule]) -> None:
    for rule in rules:
        con.execute(
            f"""
            INSERT INTO silver.dq_violations
            SELECT
              '{rule.id}' AS rule_id,
              '{rule.table}' AS table_name,
              '{rule.severity}' AS severity,
              CAST(v.record_key AS VARCHAR) AS record_key,
              CAST(v.violation_detail AS VARCHAR) AS violation_detail,
              '{rule.description.replace("'", "''")}' AS description,
              CAST(current_timestamp AS TIMESTAMP) AS detected_at
            FROM ({rule.sql}) v
            """
        )


def _publish_silver(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in TABLE_ORDER:
        key_sql = SILVER_KEY_SQL[table]
        con.execute(
            f"""
            CREATE OR REPLACE TABLE silver.{table} AS
            SELECT s.*
            FROM silver.stg_{table} s
            WHERE CAST(({key_sql}) AS VARCHAR) NOT IN (
                SELECT record_key
                FROM silver.dq_violations
                WHERE table_name = '{table}'
                  AND severity = 'error'
                  AND record_key IS NOT NULL
            )
            """
        )
        counts[table] = int(con.execute(f"SELECT COUNT(*) FROM silver.{table}").fetchone()[0])
    return counts


def build_silver(
    con: duckdb.DuckDBPyConnection,
    as_of: str,
    history_start: str,
) -> SilverResult:
    con.execute("CREATE SCHEMA IF NOT EXISTS silver")
    staging_counts: dict[str, int] = {}
    for table, sql in all_staging_sql():
        con.execute(sql)
        staging_counts[table] = int(con.execute(f"SELECT COUNT(*) FROM silver.stg_{table}").fetchone()[0])
    _create_violation_table(con)
    rules = load_rules(as_of=as_of, history_start=history_start)
    _run_rules(con, rules)
    silver_counts = _publish_silver(con)
    violations = con.execute(
        """
        SELECT rule_id, table_name, severity, record_key, violation_detail, description
        FROM silver.dq_violations
        ORDER BY table_name, rule_id, record_key
        """
    ).fetchdf()
    violation_counts = (
        violations.groupby("rule_id").size().astype(int).to_dict() if len(violations) else {}
    )
    return SilverResult(
        staging_counts=staging_counts,
        silver_counts=silver_counts,
        violation_counts=violation_counts,
        violations=violations,
    )
