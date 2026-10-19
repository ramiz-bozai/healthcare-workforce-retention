# CareStaff Insight

Synthetic Databricks prototype for a health-system operations leader: predict 90-day voluntary attrition risk, forecast 14-day unit staffing shortages, explain operational drivers, and recommend **human-reviewed** retention or staffing actions.

This is **not** a production system, **not** trained on real employees, and **not** an automated employment decision engine.

## Status

Increments 1–9 are implemented: generator through Streamlit, Git-folder Lakeflow recipe (you click Start), and the FE Bar pack.

The pipeline, Model Serving, Genie, and Databricks App are **not live**. Talk track: [docs/fe_bar.md](docs/fe_bar.md). Workspace: [docs/workspace.md](docs/workspace.md).

## Locked decisions

See [docs/decisions.md](docs/decisions.md). Architecture: [docs/architecture.md](docs/architecture.md).

- As-of date: `2026-09-01`
- Generator seed: `42`
- Identity: first name + last initial + `employee_id`
- Dollars: role-average salary **assumptions** for planning math only

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --group dev
```

## Generate data

Seed (180 active employees, 2 hospitals, 8 units, 12 months) — also committed under `data/seed/`:

```bash
uv run python -m data_generation --profile seed
```

Larger demo set (1,200 active employees, 3 hospitals, 12 units, 24 months) — gitignored:

```bash
uv run python -m data_generation --profile demo
```

## Bronze → silver → gold (local)

```bash
uv run python -m src.pipeline --profile seed
```

Writes `data/generated/carestaff.duckdb` (bronze, silver, gold). Appends intentional bad rows from `data/dq_fixtures/` so you can show quarantine. Prove the seed itself is clean with `--no-fixtures`.

Inspect gold grains:

```bash
uv run python notebooks/01_inspect_gold_grains.py
```

## Models (local)

```bash
uv run python -m src.ml --profile seed
uv run python notebooks/02_inspect_models.py
```

Trains HistGradientBoosting + sigmoid calibration on labels fully realized by as_of. Scores the frozen as_of roster. Logs to local MLflow (`data/generated/mlflow.db`). High-risk is the top 15% planning list — not an employment decision.

Cite `gold.executive_kpis` for operational numbers. Cite `gold.exec_brief` when you need predicted planning figures. Both carry the assumption note.

Inspect what-if (in-process predict, not Model Serving):

```bash
uv run python notebooks/03_inspect_whatif.py
```

Every row in `gold.recommended_actions` has `status = pending_human_review` and `applied = false`. What-if dollars are assumed feature shifts, not savings.

Inspect the allowlisted assistant (template mode, not Genie):

```bash
uv run python -m src.ai --list-tools
uv run python -m src.ai "What is 7-day coverage?"
uv run python notebooks/04_inspect_assistant.py
```

The assistant never computes a KPI in prose. Numbers come from allowlisted gold SQL or in-process `predict()`. A validator rejects numeric claims that are not in the tool payload.

## Streamlit workbench (local)

```bash
uv run streamlit run app.py
uv run python notebooks/05_walkthrough.py
```

Pages: Overview, Attrition risk, Unit shortage, Actions & what-if, Ask, Policy. Metrics are read from gold (same columns the tools cite). Apply is disabled. Ask uses `src.ai`. This is not a Databricks App until you create one in the workspace.

## Databricks workspace (you attach the Git folder)

This repo does **not** auto-deploy. Instructions: [docs/workspace.md](docs/workspace.md).

```bash
uv run python notebooks/06_workspace_checklist.py
```

Lakeflow source (only this directory): `pipelines/carestaff_insight/`. You click Start.

## FE Bar pack

```bash
uv run python notebooks/00_fe_bar.py
```

Talk track, say/don't-say, inspect list, objections: [docs/fe_bar.md](docs/fe_bar.md). Quote numbers from that script, not from memory.

## Tests

```bash
uv run pytest
```

## What you should inspect

1. `conf/default.yaml` — thresholds, salaries, playbook. This is the source of truth.
2. `data/seed/employees.csv` — no age/sex/race/SSN/email; names look like `Jordan M.`
3. `data/seed/role_cost_assumptions.csv` — the only place dollars live.
4. `data/seed/attrition_events.csv` — `voluntary` vs `involuntary`.
5. `data/seed/manifest.json` — row counts and `contains_phi: false`.
6. `conf/dq_rules.yaml` — every DQ rule ID you will name in a roleplay.
7. `data/dq_fixtures/` — bad rows labeled `EMP-FIX*`. They must not appear in `silver.employees`.
8. `gold.executive_kpis` — operational exec numbers (no model scores).
9. `gold.exec_brief` — operational KPIs plus predicted planning figures.
10. `gold.employee_risk_scores` / `gold.unit_shortage_forecast` — ranked lists with drivers.
11. `gold.metric_catalog` — formula list. If a metric is not here, do not say it.
12. `gold.recommended_actions` — closed playbook, all pending human review.
13. `gold.whatif_scenarios` — assumed feature shifts vs baseline. Not applied.
14. `src.ai` allowlist — if a metric is not in `gold.metric_catalog`, the assistant will not invent it.
15. Streamlit `app.py` — Apply is disabled; Genie and Model Serving banners stay false.
16. `docs/fe_bar.md` — talk track. `docs/workspace.md` — Git folder, no auto-deploy.

## Assumptions and limitations

- All people, units, and dollars are synthetic.
- Attrition drivers are **injected** (overtime, schedule churn, nights, short tenure, vacancy, manager span) so explanations later are not random. That is a demo design choice, not a published causal finding.
- 90% coverage is a configurable planning threshold, not a clinical staffing standard.
- What-if feature shifts are assumed in `conf/default.yaml`. They are not applied to the schedule and are not measured savings.
- Connecting this Git repo in a Databricks workspace is the deployment path. Nothing is deployed until you run it there. This repository does not auto-deploy a pipeline, App, Genie space, or Serving endpoint.
