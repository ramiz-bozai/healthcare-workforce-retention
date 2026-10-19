# Locked design decisions

Approved 2026-10-16. Do not change these without an explicit new decision.

| # | Decision | Locked choice |
|---|---|---|
| 1 | Working title | CareStaff Insight |
| 2 | Clinical scope | Nursing + allied: RN, LPN, CNA, RT, ED Tech. Seed: 2 hospitals / 8 units. Demo: 3 / 12. |
| 3 | Demo UI | React + FastAPI Databricks App (`frontend/`, `app.py`) + one walkthrough notebook (`notebooks/05_walkthrough.py`). Replaced Streamlit 2026-10-19. |
| 4 | Pipeline dual-runtime | Shared SQL. DuckDB locally. Spark Declarative Pipelines in the workspace after Git connect. |
| 5 | Shortage definition | `coverage_ratio < 0.90` **or** `open_shift_share > 0.10`. Train on 14-day. Report 28-day. |
| 6 | Attrition definition | Voluntary separation within 90 days of a month-end snapshot. Involuntary is not the positive class. |
| 7 | Model family | HistGradientBoosting or LightGBM with importances. No deep learning. |
| 8 | AI layer | Allowlisted SQL + predict tools + citation validator. Genie on gold in workspace. Template fallback if no LLM. |
| 9 | Employee identity | Synthetic first name + last initial + `employee_id`. |
| 10 | Dollar impact | **On.** Role-average synthetic salaries in `conf/default.yaml`. Models do **not** see individual pay (band only). Exec dollars = planning estimate, not savings the tool produced. |
| 11 | Frozen demo clock | `as_of_date = 2026-09-01`, `random_seed = 42`. |
| 12 | Actions | Closed playbook: schedule stabilize, manager outreach, workload balance, recruit prioritize, float/OT review. Status always `pending_human_review`. |

## Dollar formulas (decision 10)

- Attrition exposure ≈ Σ (high-risk employees in role × role avg salary × 1.0 replacement multiplier)
- Coverage exposure ≈ forecast gap hours × agency hourly (2.0 × staff hourly equivalent)

Staff hourly equivalent = annual salary / 2080.

## Explicit non-goals

- No protected characteristics or proxies (age, sex, race, zip, disability, religion).
- No PHI, no real employees, no customer data.
- No automated employment or scheduling decisions.
- No Solution Builder.
- Do not claim the Databricks serving endpoint or Genie space is live unless it has been deployed in the workspace.
