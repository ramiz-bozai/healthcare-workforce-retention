from __future__ import annotations

from pathlib import Path

from data_generation.schema import TABLE_ORDER
from src.common.paths import SEED_DIR
from src.gold.sql import STATEMENTS
from src.silver.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "pipelines" / "carestaff_insight"
WORKSPACE_DOC = ROOT / "docs" / "workspace.md"


def test_seed_csv_names_match_bronze_volume_layout():
    bronze = (RECIPE / "bronze.py").read_text()
    assert "{table_name}.csv" in bronze
    assert "cloudFiles" not in bronze
    for table in TABLE_ORDER:
        assert (SEED_DIR / f"{table}.csv").exists(), table


def test_pipeline_files_bootstrap_repo_root():
    boot = (RECIPE / "_bootstrap.py").read_text()
    assert "parents[2]" in boot
    for name in ("bronze.py", "silver.py", "gold.py"):
        text = (RECIPE / name).read_text()
        assert "import _bootstrap" in text


def test_gold_recipe_registers_the_same_grains_as_local_sql():
    gold = (RECIPE / "gold.py").read_text()
    names = [name for name, _ in STATEMENTS]
    assert names == [
        "snapshot_calendar",
        "role_cost_assumptions",
        "metric_catalog",
        "unit_day_coverage",
        "unit_week_features",
        "employee_month_features",
        "executive_kpis",
    ]
    assert "STATEMENTS" in gold
    assert "to_spark_select" in gold


def test_set_level_rules_are_not_row_expects():
    rules = load_rules("2026-09-01", "2025-09-01")
    row_ids = {r.id for r in rules if r.row_predicate}
    set_ids = {r.id for r in rules if not r.row_predicate}
    assert "emp_required_fields" in row_ids
    assert "emp_pk_unique" in set_ids


def test_workspace_doc_is_git_folder_not_auto_deploy():
    text = WORKSPACE_DOC.read_text().lower().replace("*", "")
    assert "git folder" in text
    assert "not an auto-deploy" in text
    assert "you click start" in text
    assert "do not claim" in text
    assert "model serving" in text
    assert "genie" in text
    assert "does not auto-deploy" in text or "databricks asset bundle" in text


def test_no_bundle_deploy_config_in_repo():
    assert not (ROOT / "databricks.yml").exists()
    assert not (ROOT / "databricks.yaml").exists()
