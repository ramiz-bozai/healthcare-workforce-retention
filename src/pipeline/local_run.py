"""Run bronze → silver → gold locally on DuckDB."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from data_generation.config import load_config
from src.bronze.ingest import ingest_bronze
from src.common.paths import DEFAULT_DUCKDB, FIXTURE_DIR, SEED_DIR
from src.gold.build import GoldResult, build_gold
from src.silver.build import SilverResult, build_silver


@dataclass
class PipelineRun:
    con: duckdb.DuckDBPyConnection
    bronze_counts: dict[str, int]
    silver: SilverResult
    gold: GoldResult


def run_local(
    profile: str = "seed",
    source_dir: Path | None = None,
    fixture_dir: Path | None = None,
    duckdb_path: Path | None = None,
    include_fixtures: bool = True,
) -> PipelineRun:
    cfg = load_config(profile)
    db_path = duckdb_path or DEFAULT_DUCKDB
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    bronze_counts = ingest_bronze(
        con,
        source_dir=source_dir or SEED_DIR,
        fixture_dir=fixture_dir or FIXTURE_DIR,
        include_fixtures=include_fixtures,
    )
    silver = build_silver(
        con,
        as_of=cfg.as_of_date.isoformat(),
        history_start=cfg.history_start.isoformat(),
    )
    labels = cfg.raw["labels"]
    gold = build_gold(
        con,
        as_of=cfg.as_of_date.isoformat(),
        history_start=cfg.history_start.isoformat(),
        future_end=cfg.future_end.isoformat(),
        coverage_threshold=float(labels["shortage_coverage_ratio_threshold"]),
        open_shift_threshold=float(labels["shortage_open_shift_share_threshold"]),
        attrition_horizon=int(labels["attrition_horizon_days"]),
        shortage_primary=int(labels["shortage_primary_horizon_days"]),
        shortage_secondary=int(labels["shortage_secondary_horizon_days"]),
    )
    return PipelineRun(con=con, bronze_counts=bronze_counts, silver=silver, gold=gold)


def print_summary(run: PipelineRun) -> None:
    print("Bronze row counts:")
    for table, n in run.bronze_counts.items():
        print(f"  {table:24s} {n:8d}")
    print("Silver row counts (errors quarantined):")
    for table, n in run.silver.silver_counts.items():
        print(f"  {table:24s} {n:8d}")
    print("Gold row counts:")
    for table, n in run.gold.counts.items():
        print(f"  {table:24s} {n:8d}")
    print("DQ violations by rule:")
    if not run.silver.violation_counts:
        print("  (none)")
    else:
        for rule_id, n in sorted(run.silver.violation_counts.items()):
            print(f"  {rule_id:32s} {n:6d}")
    print("Executive KPIs (operational, no model scores yet):")
    print(run.gold.kpis.to_string(index=False))
