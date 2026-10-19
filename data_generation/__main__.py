"""CLI: python -m data_generation --profile seed"""

from __future__ import annotations

import argparse
from pathlib import Path

from data_generation.config import ROOT, load_config
from data_generation.engine import generate_tables
from data_generation.io import write_tables


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic healthcare workforce data (no PHI)."
    )
    parser.add_argument("--profile", choices=("seed", "demo"), default="seed")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory. Defaults to data/seed or data/generated/demo.",
    )
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    cfg = load_config(profile=args.profile, path=args.config)
    out = args.out
    if out is None:
        out = ROOT / "data" / "seed" if args.profile == "seed" else ROOT / "data" / "generated" / "demo"
    tables = generate_tables(cfg)
    manifest = write_tables(tables, out, cfg)
    n_emp = len(tables["employees"])
    n_active = int((tables["employees"]["employment_status"] == "active").sum())
    print(f"Wrote {len(tables)} tables to {out}")
    print(f"Employees: {n_emp} ({n_active} active at {cfg.as_of_date.isoformat()})")
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    main()
