# Connect this Git folder in a Databricks workspace

This is **not** an auto-deploy. This repository does not start a pipeline, App, Genie space, or Model Serving endpoint. You attach the Git folder, you upload seed files, you create the Lakeflow pipeline, and **you** click Start.

Do not claim the pipeline, Genie, Model Serving, or a Databricks App is live until you have done those clicks in your workspace.

Local equivalent (already works on this laptop):

```bash
uv run python -m src.pipeline --profile seed
uv run python -m src.ml --profile seed
uv run streamlit run app.py
```

## 1. Get the code onto Git, then into the workspace

Remote: `https://github.com/ramiz-bozai/healthcare-workforce-retention.git`

If `initial-build` is only on your laptop, commit and push first. A Git folder can only see what is on the remote.

In the workspace:

1. **Repos** or **Git folder** → add the GitHub repo.
2. Check out the branch you pushed (this work was done on `initial-build`).
3. Confirm you can open `pipelines/carestaff_insight/bronze.py` and `conf/default.yaml` from the folder.

The Lakeflow files under `pipelines/carestaff_insight/` are **self-contained**. They do not import `src`, `data_generation`, PyYAML, or a sibling helper. Lakeflow runs every file as an **isolated notebook** (often with `__file__` outside the Git folder, and `/Workspace` not FUSE-mounted), so those imports raise `PYTHON.MODULE_NOT_FOUND_ERROR`. You do not need a wheel. You do **not** need `repo_root`.

## 2. Unity Catalog objects (you create)

Use your catalog if `healthcare_ops` does not exist. Then set `volume_path` to match.

Suggested names from `conf/default.yaml` (not created by this repo):

| Object | Example |
|---|---|
| Catalog | `healthcare_ops` |
| Pipeline target schema | `carestaff_insight` |
| Volume | `/Volumes/healthcare_ops/bronze/workforce_landing` |

The Lakeflow recipe publishes **prefixed table names into one target schema**: `bronze_employees`, `silver_employees`, `gold_executive_kpis`, and so on. It does not create three separate bronze/silver/gold schemas.

Grant the pipeline identity `USE CATALOG`, `USE SCHEMA`, `CREATE TABLE` on the target, and `READ VOLUME` (and write if you land files with a notebook) on the Volume.

## 3. Land seed CSVs on the Volume

Bronze reads **one file per table**:

`{volume_path}/{table}.csv`

Tables (same as `data/seed/`):

`facilities`, `departments`, `roles`, `shifts`, `compensation_bands`, `role_cost_assumptions`, `employees`, `schedule_assignments`, `time_cards`, `absences`, `staffing_requirements`, `census_proxy`, `open_positions`, `attrition_events`

Upload those CSVs into the Volume prefix so that, for example, `employees.csv` is at:

`/Volumes/<catalog>/bronze/workforce_landing/employees.csv`

Optional quarantine demo: also upload `data/dq_fixtures/*.csv` **only if** you want bad `EMP-FIX*` rows in bronze. Local DuckDB appends fixtures by default; the Lakeflow bronze reader does not auto-append them. Prefer seed-only in the workspace unless you are showing DQ.

You can upload in the Catalog Explorer UI. This repo does not copy files for you.

## 4. Create the Lakeflow / Spark Declarative Pipeline (you click Start)

1. New **ETL pipeline** / **Lakeflow** / Spark Declarative Pipeline.
2. Source: this Git folder, directory **`pipelines/carestaff_insight` only** — `bronze.py`, `silver.py`, `gold.py`. Do **not** point the pipeline at the repo root or Lakeflow will also try to run Streamlit, tests, and the generator.
3. Destination: catalog + schema from step 2.
4. Pipeline configuration (key / value):
   - `volume_path` = `/Volumes/<catalog>/bronze/workforce_landing`  
     Default in code if you omit it: `/Volumes/healthcare_ops/bronze/workforce_landing`
5. Development mode is fine for the demo. Serverless or a small classic cluster, your choice.
6. **You** click **Start**. Wait until gold tables succeed.

What you should see in the target schema (prefix + name):

- Bronze: `bronze_facilities` … `bronze_attrition_events` (VARCHAR payload + `_ingest_ts`, `_source_path`, `_record_origin`)
- Silver: `silver_*` with per-row `expect_or_drop` using the same rule IDs as `conf/dq_rules.yaml` `row_predicate`
- Gold: `gold_snapshot_calendar`, `gold_role_cost_assumptions`, `gold_metric_catalog`, `gold_unit_day_coverage`, `gold_unit_week_features`, `gold_employee_month_features`, `gold_executive_kpis`

Gold SQL is the Spark rewrite of `src/gold/sql.py` (`generate_series` → `sequence`, `date_diff` → `datediff`, `gold.x` / `silver.x` → `LIVE.gold_x` / `LIVE.silver_x`), inlined in `gold.py`. Same tokens as local DuckDB: as_of `2026-09-01`, coverage `0.90`, open-shift `0.10`, 90-day attrition, 14/28-day shortage.

### Set-level DQ (not per-row expects)

Uniqueness and foreign keys in `conf/dq_rules.yaml` have **no** `row_predicate`. Locally they land in `silver.dq_violations`. In the workspace, run those rule SQLs as a query or materialized view after silver exists. Do not force them into `expect_or_drop`.

## 5. After gold exists — optional, still you

**Inspect.** Open `notebooks/01_inspect_gold_grains.py` from the Git folder and point queries at `gold_*` in the target schema (rename `gold.executive_kpis` → `<catalog>.<schema>.gold_executive_kpis`).

**Models / what-if / Streamlit.** `src.ml` and `app.py` read **local DuckDB**, not these Spark tables. For the FE Bar, keep scoring and the workbench on the laptop unless you later write a job that pulls gold to pandas. Do not claim Model Serving.

**Databricks App.** If you later host the workbench: create an App yourself, working directory = Git folder root, command `streamlit run app.py`. Not created by this repo.

**Genie.** If you later add a space, point it at the gold tables and the same questions as `src/ai/tools.py`. Template fallback stays until an FM endpoint is wired. Not created by this repo.

## 6. Sanity checks after *you* start the pipeline

- `gold_executive_kpis` has one row, `as_of_date = 2026-09-01`
- `coverage_ratio_7d` is populated; `predicted_attrition_rate_90d` is **not** on that table (scores are a later job)
- Employee columns still have no age/sex/race/SSN
- Nothing in this laptop’s repo flipped `ai.genie_live` or `ai.model_serving_live`

## Troubleshooting

**`PYTHON.MODULE_NOT_FOUND_ERROR` on bronze.py / silver.py / gold.py**  
Lakeflow isolated the notebook. Older copies imported `src`, `data_generation`, a sibling `_bootstrap`, or walked `/Workspace` with `Path.is_dir()`. Pull this revision so those three files are self-contained, **refresh the Git folder**, and Start again. You do not need `repo_root`. You do not need a PyYAML cluster library.

If the error names a missing CSV, the Volume is empty or `volume_path` does not match the prefix that holds `{table}.csv`.

## What this is not

- Not Auto Loader / `cloudFiles` (bronze is batch `spark.read.csv` of Volume files)
- Not a Databricks Asset Bundle deploy from this chat
- Not Model Serving, not Genie, not a live Databricks App
- Not executed in this local environment
