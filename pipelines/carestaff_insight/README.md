# Databricks Lakeflow recipe (you attach this folder)

Workspace operator steps live in [docs/workspace.md](../../docs/workspace.md). **This repo does not auto-deploy.** You add the Git folder and you click Start.

Local equivalent:

```bash
uv run python -m src.pipeline --profile seed
```

| File | Role |
|---|---|
| `bronze.py` | Volume CSV → `bronze_<table>` (VARCHAR + ingest metadata) |
| `silver.py` | Typed silver + per-row expects (same IDs as `conf/dq_rules.yaml`) |
| `gold.py` | Spark rewrite of `src/gold/sql.py`, inlined → `gold_<table>` |

Each file is **self-contained** (dlt / pyspark only). Do not import `src`, `data_generation`, yaml, or a sibling `_bootstrap.py` — Lakeflow isolates notebooks, so those imports raise `MODULE_NOT_FOUND`.

Pipeline config:

- `volume_path` (default `/Volumes/healthcare_ops/bronze/workforce_landing`)

No `repo_root`. Destination catalog/schema are set in the pipeline UI, not in this folder.

Do not claim this pipeline, Genie, Model Serving, or a Databricks App is live until you run it in the workspace.
