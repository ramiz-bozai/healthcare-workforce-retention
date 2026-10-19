# CareStaff Insight — FE Bar pack

Audience: health-system operations / nursing workforce leader plus their Databricks champion. Timebox: **12–15 minutes**. Synthetic data. Frozen clock **2026-09-01**, generator seed **42**.

Refresh live numbers (do not memorize stale dollars):

```bash
uv run python notebooks/00_fe_bar.py
uv run python app.py
```

If gold is missing: `uv run python -m src.pipeline --profile seed` then `uv run python -m src.ml --profile seed`.

This pack does **not** deploy a workspace pipeline, Databricks App, Genie space, or Model Serving endpoint.

---

## One-sentence pitch

A governed planning workbench: who is at 90-day **voluntary** attrition risk, which units look short in **14 days**, what the closed playbook would change **if a human applies it** — with dollars as role-average **assumptions**, not savings the model produced.

## The question with dollar impact

“If we knew this week’s high-risk roster and next two weeks’ short units, what would we **review** — without auto-firing anyone or writing the schedule?”

Seed snapshot (cite `gold.exec_brief` after you refresh):

| Claim | Typical seed-42 value | Citation |
|---|---|---|
| Active headcount | 180 | `gold.exec_brief.active_headcount` |
| 7-day coverage | ~1.024 | `gold.exec_brief.coverage_ratio_7d` |
| Vacancy | ~0.130 | `gold.exec_brief.vacancy_rate` |
| High-risk (top 15%) | 27 | `gold.exec_brief.high_risk_headcount` |
| Planning attrition exposure | ~$2.25M | `gold.exec_brief.planning_attrition_exposure_usd` |
| Flagged shortage units | 7 of 8 | `gold.exec_brief.predicted_shortage_units_14d` |
| Recommended actions | 47, **0 applied** | `gold.action_summary` |

Read **$** as planning math: high-risk headcount × role-average salary × replacement 1.0, and flagged-unit gap hours × agency hourly (2× staff). Not measured savings. Not individual pay.

---

## Timed talk track

### 0:00–1:00 — Frame (do not open the app yet)

- Health systems burn cash on replacement and agency while the schedule is already stressed.
- This prototype is **synthetic**. Names look like `Ellis M.` plus `EMP-000001`. No PHI, no age/sex/race, no real employees.
- Clock is frozen at 2026-09-01 so every number is inspectable.
- Humans decide. The product never applies an action.

### 1:00–3:00 — Governance, not a notebook demo

Show, in this order (files, not slides):

1. `conf/default.yaml` — thresholds, playbook, salaries. Source of truth.
2. `data/seed/employees.csv` — identity contract.
3. `data/seed/role_cost_assumptions.csv` — the only place dollars live.
4. `conf/dq_rules.yaml` — name a rule ID (`emp_pk_unique`, `tc_overtime_consistent`).
5. Optional: `data/dq_fixtures/` `EMP-FIX*` rows must **not** appear in `silver.employees`.

Line: “Bronze lands as strings. Silver types and quarantines with the same rule IDs locally and in Lakeflow. Gold is the only layer the assistant may cite.”

### 3:00–6:00 — Overview + Attrition

`uv run python app.py`

- Overview metrics: caption under each tile is the gold column. Operational KPIs also live on `gold.executive_kpis` **without** predicted scores. Predicted planning figures are on `gold.exec_brief`.
- Attrition: high-risk is the **top 15%** by calibrated p(voluntary 90d). Say “planning list,” never “people we should terminate.”
- Open **Ellis M., RN, NSH-ICU** (rank 1 on seed-42). Drivers should be operational (swaps, OT, tenure) — those traits were **injected in the generator** so explanations are demo-shaped, not a published causal study.
- In-process predict vs gold p: same model object, **not Model Serving**.
- Oracle expander: generator labels after as_of. Label it `inference_demo_oracle`. Production would not have those labels yet.

Honest model line (from last local train; refresh): valid-split ROC-AUC for attrition is strong; the as-of oracle is weaker because of a time shift. Do not quote valid AUC as “what we would have caught tomorrow.”

### 6:00–8:00 — Shortage + actions

- 14-day unit forecast. This seed is **chronically short** (~7/8 flagged). The model **ranks units**; it is not a rare-event detector. Persistence baseline is already high — say that.
- Actions page: 47 rows, status `pending_human_review`, applied 0. Click **Apply** — it is disabled. Gold is opened read-only.
- What-if bundle: high-risk 27→4, attrition Δ on the order of **$1.9M assumed**. Shortage flags stay at 7. Line: “If named features moved as `conf/default.yaml` says. Not written back. Not savings.”

Playbook (closed): schedule stabilize, manager outreach (unscored), workload balance, recruit prioritize, float/OT review.

### 8:00–11:00 — Ask (grounded)

Suggested questions (already wired):

- “What is 7-day coverage and vacancy?”
- “Who is high risk?”
- “What if we run the bundle stabilize scenario?”
- “How is coverage_ratio_7d calculated?”

Then show a refuse: “Break down attrition risk by race.” Protected classes are not in the data.

Line: “Ask Genie is the workspace space attached as an App resource. Until that resource exists, **Genie is not live** and Ask falls back to allowlisted gold tools. A validator still drops protected-class questions.”

Unknown metric (`warp_flux_99`) → will not invent a formula.

### 11:00–13:00 — Platform path (no live claim)

- One logical design, two runtimes. Local DuckDB is how we test. Databricks is the customer story **after they connect this Git repo**.
- You do **not** auto-deploy. Operator steps: [workspace.md](workspace.md). Pipeline source = `pipelines/carestaff_insight` only. They click Start, then run `notebooks/07_workspace_models.py` for scores.
- Lakeflow gold is operational (`gold_executive_kpis` has no predictions). Scores land in `gold_exec_brief` / `gold_employee_risk_scores` from notebook 07. Not Model Serving.
- Next clicks after scores: Databricks App wrapping `app.py`, Genie space on gold using the same allowlist. Do not stand up Model Serving for this bar.

### 13:00–15:00 — Close

Ask: “If this were your as-of roster, which three actions would a nursing director actually review this week?” Stay on pending human review. Offer Git-folder connect, not a production rollout.

---

## Say this / do not say this

| Say | Do not say |
|---|---|
| Synthetic planning workbench, frozen 2026-09-01 | Production system / trained on your employees |
| Voluntary 90-day attrition; involuntary is not the positive class | “Predicts all turnover” / “will quit” |
| High-risk = top 15% planning list | Employment decision, fire, block a shift |
| Role-average salary **assumption** | Individual pay, “the model saved $X” |
| What-if = assumed feature shift, not applied | Measured ROI / schedule already changed |
| In-process `predict()` | A serving endpoint is already up |
| Allowlisted tools + template fallback | A Genie space is already on |
| Lakeflow recipe in Git; you click Start | The pipeline is already running (unless they started it) |
| Fairness slices: role, unit, facility, tenure, shift | Race, sex, age, zip, disability |
| Injected operational drivers for a demo | Peer-reviewed causal finding |
| 90% coverage is a config threshold | Clinical staffing standard |
| Dual runtime, same gold SQL | Solution Builder |

`conf/default.yaml` keeps `ai.genie_live: false` and `ai.model_serving_live: false` until a space / endpoint exists.

---

## Inspect list (live demo ammo)

1. `conf/default.yaml`
2. `data/seed/employees.csv` / `role_cost_assumptions.csv` / `attrition_events.csv` / `manifest.json` (`contains_phi: false`)
3. `conf/dq_rules.yaml` + `data/dq_fixtures/`
4. `gold.executive_kpis` vs `gold.exec_brief`
5. `gold.employee_risk_scores` / `gold.unit_shortage_forecast`
6. `gold.metric_catalog` — if it is not here, do not say it
7. `gold.recommended_actions` / `gold.whatif_scenarios` / `gold.action_summary`
8. `src/ai/tools.py` allowlist
9. React Apply disabled; Policy page banners false
10. `docs/workspace.md` — Git folder, no auto-deploy

Commands: `notebooks/01`–`06`, `pytest`.

---

## Objections

**“Will this fire people?”** No. Closed playbook, status always `pending_human_review`, Apply disabled, DuckDB read-only.

**“Where is pay?”** Models see compensation **band** only. Dollars are role averages in `role_cost_assumptions`.

**“Can it use our EHR?”** Not this prototype. Landing contract is CSV → bronze VARCHAR. Next conversation is their HRIS/scheduling feeds into a Volume, same silver rules.

**“Why is shortage almost always flagged?”** Seed is a stressed system. Model ranks units. Quote persistence baseline. Do not sell a miracle detector.

**“Is Genie on?”** Not until they create a space on the gold tables **and attach it to the App** as a Genie Agent resource. Ask is template-mode until then.

**“Can you stand this up in our workspace now?”** They add the Git folder and follow [workspace.md](workspace.md). This repo does not push a pipeline, App, or Genie space.

---

## Day-of checklist

- [ ] `uv sync --group dev && uv run pytest`
- [ ] `uv run python notebooks/00_fe_bar.py` — quote those numbers only
- [ ] App up at http://127.0.0.1:8000; Apply is greyed out
- [ ] Ask: coverage question, race refuse, unknown metric refuse
- [ ] Do not flip `genie_live` / `model_serving_live`
- [ ] Do not promise a deploy from chat
