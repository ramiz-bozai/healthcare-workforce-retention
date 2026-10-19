from __future__ import annotations

import pytest

from src.app.connection import rewrite_workspace_sql, warehouse_configured


def test_rewrite_gold_and_silver_tables():
    sql = "SELECT * FROM gold.exec_brief JOIN silver.employees USING (employee_id)"
    out = rewrite_workspace_sql(sql, "healthcare_ops", "carestaff_insight")
    assert "healthcare_ops.carestaff_insight.gold_exec_brief" in out
    assert "healthcare_ops.carestaff_insight.silver_employees" in out
    assert "gold.exec_brief" not in out


def test_rewrite_information_schema_gold_listing():
    sql = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'gold'"
    out = rewrite_workspace_sql(sql, "healthcare_ops", "carestaff_insight")
    assert "healthcare_ops.information_schema.tables" in out
    assert "table_name LIKE 'gold_%'" in out
    assert "regexp_replace(table_name, '^gold_', '')" in out


def test_rewrite_rejects_bad_identifiers():
    with pytest.raises(ValueError):
        rewrite_workspace_sql("SELECT 1", "healthcare-ops", "carestaff_insight")
    with pytest.raises(ValueError):
        rewrite_workspace_sql("SELECT 1", "healthcare_ops", "carestaff insight")


def test_warehouse_configured_requires_all_three(monkeypatch):
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID", raising=False)
    monkeypatch.delenv("DATABRICKS_SQL_WAREHOUSE_ID", raising=False)
    monkeypatch.delenv("CARESTAFF_CATALOG", raising=False)
    monkeypatch.delenv("CARESTAFF_SCHEMA", raising=False)
    assert warehouse_configured() is False
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "abc")
    monkeypatch.setenv("CARESTAFF_CATALOG", "healthcare_ops")
    monkeypatch.setenv("CARESTAFF_SCHEMA", "carestaff_insight")
    assert warehouse_configured() is True
