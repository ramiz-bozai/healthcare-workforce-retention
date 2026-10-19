from __future__ import annotations

from pathlib import Path

from data_generation.schema import TABLE_ORDER
from src.pipeline.workspace_path import ensure_repo_on_path, find_repo_root
from src.common.paths import SEED_DIR
from src.gold.sql import STATEMENTS
from src.silver.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "pipelines" / "carestaff_insight"
WORKSPACE_DOC = ROOT / "docs" / "workspace.md"


def test_find_repo_root_from_nested_file_and_conf():
    nested = RECIPE / "gold.py"
    assert find_repo_root(file_path=nested) == ROOT
    assert ensure_repo_on_path(file_path=nested) == ROOT
    missing = Path("/tmp/does-not-exist-carestaff")
    assert find_repo_root(file_path=missing, conf_root=str(ROOT)) == ROOT


def test_seed_csv_names_match_bronze_volume_layout():
    bronze = (RECIPE / "bronze.py").read_text()
    assert "{table_name}.csv" in bronze
    assert "cloudFiles" not in bronze
    for table in TABLE_ORDER:
        assert (SEED_DIR / f"{table}.csv").exists(), table


def test_pipeline_files_do_not_import_sibling_bootstrap():
    py_files = list(RECIPE.glob("*.py"))
    assert {p.name for p in py_files} == {"bronze.py", "silver.py", "gold.py"}
    for path in py_files:
        text = path.read_text()
        assert "\nimport _bootstrap" not in text
        assert "def _ensure_repo_on_path" in text
        assert 'spark.conf.get("repo_root"' in text
        assert "data_generation" in text


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
