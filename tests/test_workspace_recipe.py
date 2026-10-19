from __future__ import annotations

import ast
from pathlib import Path

from data_generation.schema import TABLE_ORDER
from src.gold.build import render_sql
from src.gold.spark_sql import to_spark_select
from src.gold.sql import STATEMENTS
from src.pipeline.workspace_path import ensure_repo_on_path, find_repo_root
from src.common.paths import SEED_DIR
from src.silver.rules import load_rules, spark_row_expectations
from src.silver.standardize import staging_sql

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "pipelines" / "carestaff_insight"
WORKSPACE_DOC = ROOT / "docs" / "workspace.md"
FORBIDDEN_ROOTS = {"src", "data_generation", "yaml", "_bootstrap"}
ALLOWED_IMPORT_ROOTS = {"__future__", "dlt", "pyspark"}


def _literal(path: Path, name: str):
    tree = ast.parse(path.read_text())
    for node in tree.body:
        target = None
        value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if isinstance(target, ast.Name) and target.id == name:
            return ast.literal_eval(value)
    raise AssertionError(f"{path.name} is missing {name}")


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


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
    assert _literal(RECIPE / "bronze.py", "TABLE_ORDER") == list(TABLE_ORDER)
    for table in TABLE_ORDER:
        assert (SEED_DIR / f"{table}.csv").exists(), table


def test_pipeline_files_are_self_contained():
    py_files = list(RECIPE.glob("*.py"))
    assert {p.name for p in py_files} == {"bronze.py", "silver.py", "gold.py"}
    for path in py_files:
        text = path.read_text()
        roots = _imported_roots(path)
        assert not (roots & FORBIDDEN_ROOTS), (path.name, roots)
        assert roots <= ALLOWED_IMPORT_ROOTS
        assert "import dlt" in text
        assert "from pyspark import pipelines as dlt" in text
        assert "_ensure_repo_on_path" not in text
        assert "repo_root" not in text
        assert "sys.path" not in text
        ast.parse(text)


def test_gold_recipe_matches_local_spark_rewrite():
    queries = _literal(RECIPE / "gold.py", "GOLD_QUERIES")
    names = [name for name, _ in STATEMENTS]
    assert list(queries) == names
    for name, sql in STATEMENTS:
        expected = to_spark_select(
            render_sql(
                sql,
                as_of="2026-09-01",
                history_start="2025-09-01",
                future_end="2026-11-30",
                coverage_threshold=0.90,
                open_shift_threshold=0.10,
                attrition_horizon=90,
                shortage_primary=14,
                shortage_secondary=28,
            )
        )
        assert queries[name] == expected, name
        assert "generate_series" not in queries[name].lower()
        assert "date_diff" not in queries[name].lower()
        assert "CREATE OR REPLACE" not in queries[name].upper()


def test_silver_recipe_matches_local_staging_and_row_expects():
    staging = _literal(RECIPE / "silver.py", "STAGING_SQL")
    expects = _literal(RECIPE / "silver.py", "ROW_EXPECTS")
    assert list(staging) == list(TABLE_ORDER)
    rules = load_rules("2026-09-01", "2025-09-01")
    for table in TABLE_ORDER:
        local = staging_sql(table)
        payload = local.split("SELECT", 1)[1].split("FROM", 1)[0]
        assert f"FROM LIVE.bronze_{table}" in staging[table]
        assert "CREATE OR REPLACE" not in staging[table].upper()
        assert "VARCHAR" not in staging[table].upper()
        assert "AS STRING" in staging[table]
        assert spark_row_expectations(table, rules) == expects.get(table, {})
        for col_sql in payload.strip().split(","):
            token = col_sql.strip()
            if token:
                assert token in staging[table], (table, token)
    row_ids = {r.id for r in rules if r.row_predicate}
    inlined = {rid for table_expects in expects.values() for rid in table_expects}
    assert inlined == row_ids


def test_set_level_rules_are_not_row_expects():
    rules = load_rules("2026-09-01", "2025-09-01")
    row_ids = {r.id for r in rules if r.row_predicate}
    set_ids = {r.id for r in rules if not r.row_predicate}
    expects = _literal(RECIPE / "silver.py", "ROW_EXPECTS")
    inlined = {rid for table_expects in expects.values() for rid in table_expects}
    assert "emp_required_fields" in row_ids
    assert "emp_pk_unique" in set_ids
    assert "emp_pk_unique" not in inlined
    assert inlined.isdisjoint(set_ids)


def test_workspace_doc_is_git_folder_not_auto_deploy():
    text = WORKSPACE_DOC.read_text().lower().replace("*", "").replace("`", "")
    assert "git folder" in text
    assert "not an auto-deploy" in text
    assert "you click start" in text
    assert "do not claim" in text
    assert "model serving" in text
    assert "genie" in text
    assert "does not auto-deploy" in text or "databricks asset bundle" in text
    assert "self-contained" in text
    assert "repo_root" not in text or "do not need repo_root" in text


def test_no_bundle_deploy_config_in_repo():
    assert not (ROOT / "databricks.yml").exists()
    assert not (ROOT / "databricks.yaml").exists()
