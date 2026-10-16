"""Write generated tables as inspectable CSV plus a manifest."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from data_generation.config import GenerationConfig
from data_generation.schema import TABLE_ORDER


def write_tables(
    tables: dict[str, pd.DataFrame],
    out_dir: Path,
    cfg: GenerationConfig,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name in TABLE_ORDER:
        df = tables[name]
        counts[name] = int(len(df))
        df.to_csv(out_dir / f"{name}.csv", index=False, date_format="%Y-%m-%d")
    manifest = {
        "project": cfg.project_name,
        "profile": cfg.profile,
        "random_seed": cfg.random_seed,
        "as_of_date": cfg.as_of_date.isoformat(),
        "history_start": cfg.history_start.isoformat(),
        "future_end": cfg.future_end.isoformat(),
        "n_active_employees_target": cfg.n_active_employees,
        "row_counts": counts,
        "synthetic": True,
        "contains_phi": False,
        "contains_protected_characteristics": False,
    }
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def read_tables(in_dir: Path) -> dict[str, pd.DataFrame]:
    tables = {}
    for name in TABLE_ORDER:
        tables[name] = pd.read_csv(in_dir / f"{name}.csv")
    return tables
