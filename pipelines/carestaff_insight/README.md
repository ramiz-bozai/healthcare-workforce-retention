# Databricks Lakeflow recipe (you attach this folder)

Workspace operator steps live in [docs/workspace.md](../../docs/workspace.md). **This repo does not auto-deploy.** You add the Git folder and you click Start.

Local equivalent:

```bash
uv run python -m src.pipeline --profile seed
```

| File | Role |
|---|---|
| `bronze.py` | Volume CSV → `bronze_<table>` (VARCHAR + ingest metadata) |
| `silver.py` | Typed silver + per-row expects from `conf/dq_rules.yaml` |
| `gold.py` | `src/gold/sql.py` after Spark rewrite → `gold_<table>` |

Each file inlines repo-root discovery. Do not add a sibling `_bootstrap.py` — Lakeflow isolates notebooks, so that import raises `MODULE_NOT_FOUND`.

Pipeline config:

- `volume_path` (default `/Volumes/healthcare_ops/bronze/workforce_landing`)
- `repo_root` = Git folder path (needed when isolated notebooks do not keep `__file__` inside the repo)

Destination catalog/schema are set in the pipeline UI, not in this folder.

Do not claim this pipeline, Genie, Model Serving, or a Databricks App is live until you run it in the workspace.
