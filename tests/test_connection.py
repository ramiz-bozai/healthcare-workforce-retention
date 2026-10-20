from __future__ import annotations

import pytest

from src.app.connection import (
    HybridConnection,
    lakebase_configured,
    rewrite_lakebase_sql,
    rewrite_workspace_sql,
    warehouse_configured,
)


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


def test_rewrite_lakebase_serving_tables_and_params():
    sql = "SELECT * FROM gold.employee_risk_scores WHERE employee_id = ?"
    out = rewrite_lakebase_sql(sql, "carestaff_insight")
    assert '"carestaff_insight"."gold_employee_risk_scores_serving"' in out
    assert "employee_id = %s" in out


def test_rewrite_lakebase_rejects_non_serving_table():
    with pytest.raises(ValueError):
        rewrite_lakebase_sql("SELECT * FROM gold.recommended_actions", "carestaff_insight")


class _StubConnection:
    def __init__(self, name):
        self.name = name
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self.name

    def close(self):
        pass


def test_hybrid_routes_serving_tables_to_lakebase():
    warehouse = _StubConnection("warehouse")
    lakebase = _StubConnection("lakebase")
    con = HybridConnection(warehouse, lakebase)
    assert con.execute("SELECT * FROM gold.exec_brief") == "lakebase"
    assert con.execute("SELECT * FROM gold.recommended_actions") == "warehouse"
    assert len(lakebase.calls) == 1
    assert len(warehouse.calls) == 1


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


def test_lakebase_configured_requires_resource_and_pg_env(monkeypatch):
    keys = (
        "LAKEBASE_ENDPOINT",
        "PGHOST",
        "PGDATABASE",
        "PGUSER",
        "CARESTAFF_LAKEBASE_SCHEMA",
    )
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    assert lakebase_configured() is False
    for key in keys:
        monkeypatch.setenv(key, "value")
    assert lakebase_configured() is True
