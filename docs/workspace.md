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

## 5. FE Bar in the workspace (four stops)

Lakeflow gold is **not** the whole FE Bar. Streamlit, Ask, risk lists, and what-if need score tables that the pipeline does not publish.

| Stop | Live object | Who clicks | Status |
|---|---|---|---|
| 1 | Lakeflow `gold_executive_kpis` + feature tables | You (pipeline Start) | You are here if gold exists |
| 2 | Score / action tables + optional model Volume | You run `notebooks/07_workspace_models.py` | Next |
| 3 | Databricks App wrapping `app.py` | You create the App | After stop 2 |
| 4 | Genie space on gold (Ask in the App is template until then) | You create the space | After stop 2 |

**Not in this path:** Model Serving. Scoring is in-process in the notebook (same sklearn objects as local). `ai.model_serving_live` stays false. Do not claim an endpoint.

### Stop 2 — models notebook (you click Run)

1. Commit / push / refresh the Git folder so `notebooks/07_workspace_models.py` is there.
2. Optional: Catalog Explorer → create Volume `<catalog>.<schema>.carestaff_models` (or any schema you prefer). Needed later if the App should call in-process `predict`.
3. Open `notebooks/07_workspace_models.py` **from the Git folder** (not copied into the Lakeflow source dir, not Run file on a pipeline).
4. Attach a cluster or serverless notebook compute. Widgets:
   - `catalog` / `schema` = the same target as the pipeline
   - `model_volume` = `/Volumes/<catalog>/<schema>/carestaff_models` or leave blank
5. **Run all**. First cell installs duckdb / sklearn.

It writes (overwrite) into that schema, prefixed like Lakeflow:

`gold_employee_risk_scores`, `gold_unit_shortage_forecast`, `gold_exec_brief`, `gold_recommended_actions`, `gold_whatif_scenarios`, `gold_action_summary`, `gold_model_metrics`, `gold_model_fairness_slices`, `gold_model_calibration_bins`, `gold_model_feature_importances`, and `gold_metric_catalog_scored` (ops + model formulas).

It does **not** overwrite Lakeflow tables (`gold_metric_catalog`, `gold_employee_month_features`, `gold_unit_*`, `gold_executive_kpis`, …). Those are pipeline objects, not unmanaged Delta.

Sanity after the notebook:

```sql
SELECT as_of_date, active_headcount, high_risk_headcount,
       predicted_attrition_rate_90d, predicted_shortage_units_14d
FROM <catalog>.<schema>.gold_exec_brief;

SELECT uniform_status, applied_count FROM <catalog>.<schema>.gold_action_summary;
```

Expect one exec row, `as_of_date = 2026-09-01`, `applied_count = 0`, status `pending_human_review`.

### Metric views (Databricks-only)

Open `notebooks/08_metric_views.py` from the Git folder. Same `catalog` / `schema` widgets. Run all.

Creates:

- `carestaff_unit_coverage` / `carestaff_as_of_roster` — pipeline gold
- `carestaff_attrition_risk` / `carestaff_unit_shortage` — after notebook 07; skipped if those tables are missing

Query with `MEASURE(...)`, for example:

```sql
SELECT department_id, MEASURE(coverage_ratio), MEASURE(shortage_day_count)
FROM <catalog>.<schema>.carestaff_unit_coverage
GROUP BY department_id
```

Put these on the Genie space and AI/BI, not a dump of every `gold_*` table.

### Stop 3 — Databricks App (after scores exist)

Do not create the App until `gold_exec_brief` exists. `app.py` still reads **DuckDB** until the next increment wires Unity Catalog. After that increment you will: New **App** → source = Git folder **root** (not `pipelines/carestaff_insight`) → command `streamlit run app.py` → SQL warehouse resource → grant the app SP `SELECT` on the gold tables and `CAN USE` on the warehouse.

Until that wiring lands, the workbench for the talk track is still:

```bash
uv run python -m src.ml --profile seed
uv run streamlit run app.py
```

### Stop 4 — Genie (you create the space)

New Genie space → add the `carestaff_*` metric views, plus `gold_exec_brief` / `gold_recommended_actions` after notebook 07. Same questions as `src/ai/tools.py`. Do not flip `ai.genie_live` until the space exists. The App Ask page stays template-mode until then.

## 6. Sanity checks after *you* start the pipeline

- `gold_executive_kpis` has one row, `as_of_date = 2026-09-01`
- `coverage_ratio_7d` is populated; `predicted_attrition_rate_90d` is **not** on that table until stop 2 (`gold_exec_brief`)
- Employee columns still have no age/sex/race/SSN
- Nothing in this laptop’s repo flipped `ai.genie_live` or `ai.model_serving_live`

## Troubleshooting

**`PYTHON.MODULE_NOT_FOUND_ERROR` on bronze.py / silver.py / gold.py**  
Lakeflow isolated the notebook. Older copies imported `src`, `data_generation`, a sibling `_bootstrap`, or walked `/Workspace` with `Path.is_dir()`. Pull this revision so those three files are self-contained, **refresh the Git folder**, and Start again. You do not need `repo_root`. You do not need a PyYAML cluster library.

If the error names a missing CSV, the Volume is empty or `volume_path` does not match the prefix that holds `{table}.csv`.

**`DataType "VARCHAR" requires a length parameter`**  
Silver staging must use `STRING`, not unbounded `VARCHAR`. Pull this revision, refresh the Git folder, and Start again.

## What this is not

- Not Auto Loader / `cloudFiles` (bronze is batch `spark.read.csv` of Volume files)
- Not a Databricks Asset Bundle deploy from this chat
- Not Model Serving, not Genie, not a live Databricks App
- Not executed in this local environment
