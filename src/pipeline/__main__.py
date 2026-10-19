from __future__ import annotations

import argparse
from pathlib import Path

from src.common.paths import DEFAULT_DUCKDB
from src.pipeline.local_run import print_summary, run_local


def main() -> None:
    parser = argparse.ArgumentParser(description="CareStaff Insight bronze→silver→gold (DuckDB local).")
    parser.add_argument("--profile", choices=("seed", "demo"), default="seed")
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--duckdb", type=Path, default=DEFAULT_DUCKDB)
    parser.add_argument(
        "--no-fixtures",
        action="store_true",
        help="Do not append data/dq_fixtures (proves the seed itself is clean).",
    )
    args = parser.parse_args()
    run = run_local(
        profile=args.profile,
        source_dir=args.source,
        duckdb_path=args.duckdb,
        include_fixtures=not args.no_fixtures,
    )
    print(f"DuckDB: {args.duckdb}")
    print_summary(run)
    n_err = int((run.silver.violations["severity"] == "error").sum()) if len(run.silver.violations) else 0
    print(f"Error violations: {n_err}")
    run.con.close()


if __name__ == "__main__":
    main()
