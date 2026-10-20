# CareStaff Insight — FE Bar deck outline

Use one `---` block per slide. Text under **On-slide content** belongs on the slide. **Visual direction** guides the slide-making tool. **Speaker notes** should remain in presenter notes.

Audience: health-system workforce and nursing operations leaders, with a Databricks technical stakeholder.

Presentation length: 12–15 minutes, including a 5–6 minute live demo.

Before presenting, refresh exact figures with:

`uv run python notebooks/00_fe_bar.py`

The figures below are typical for synthetic seed 42 and must be replaced if the live output differs.

---

# 1. CareStaff Insight

## On-slide content

### See workforce pressure early. Put the next decision in human hands.

90-day voluntary attrition risk · 14-day staffing outlook · governed action planning

**Synthetic demonstration | As of September 1, 2026**

## Visual direction

Minimal title slide. Use a dark healthcare operations aesthetic. Show a subtle hospital command-center image or an abstract workforce network. Add small Databricks, Lakeflow, Genie, and Apps labels along the bottom—no product-logo wall.

## Speaker notes

CareStaff Insight brings workforce risk, near-term staffing pressure, and an action review workflow into one governed planning experience. It does not make employment decisions or change schedules. All data in this demonstration is synthetic.

---

# 2. The operating problem

## On-slide content

### Workforce risk and staffing pressure are usually reviewed too late—and in separate systems.

- Retention signals live across HR, scheduling, timekeeping, absence, and vacancy data.
- Unit leaders see staffing gaps after the schedule is already under stress.
- Financial exposure is discussed without a shared, inspectable method.
- Generic dashboards describe the past but do not organize the next review.

**The opportunity:** connect workforce risk, unit demand, and a governed action queue before the next planning cycle.

## Visual direction

Show four disconnected source-system cards flowing into a fragmented weekly review. Contrast that with one unified decision point on the right.

## Speaker notes

Frame this as a planning latency problem, not simply a modeling problem. The customer question is: “If we knew this week’s high-risk roster and next two weeks’ short units, what would we review now?”

---

# 3. From signals to a reviewable decision

## On-slide content

### One workflow, three decisions

1. **Who needs review?**  
   Rank the top 15% planning cohort for voluntary attrition risk over 90 days.

2. **Where is pressure building?**  
   Rank units likely to face staffing shortage over the next 14 days.

3. **What should a leader review?**  
   Generate actions from a closed playbook and test transparent what-if assumptions.

**Human approval is the control point. Nothing is automatically applied.**

## Visual direction

Create a horizontal three-step flow: Workforce risk → Unit pressure → Human-reviewed actions. End with a visible human approval gate.

## Speaker notes

Say “planning cohort,” not “people who will quit.” Voluntary attrition is the positive class. The product ranks attention; it does not make an employment decision.

---

# 4. As-of executive snapshot

## On-slide content

### A single governed view of today’s workforce exposure

- **180** active employees
- **102.4%** 7-day coverage
- **13.0%** vacancy
- **27** employees in the high-risk planning cohort
- **7 of 8** units flagged for 14-day shortage review
- **$2.25M** estimated attrition exposure
- **47** recommended actions · **0 applied**

Footer: *Synthetic seed-42 example. Dollar figures are planning assumptions, not measured savings.*

## Visual direction

Use six large KPI tiles and one small action-status strip. Emphasize “0 applied” in a governance color. Avoid a dense table.

## Speaker notes

Confirm these values from `gold_exec_brief` before presenting. Attrition exposure uses high-risk headcount × role-average salary × replacement factor 1.0. Coverage exposure uses gap hours × an agency-rate assumption. These are not individual compensation values and are not ROI claims.

---

# 5. Live demo — from command center to action review

## On-slide content

### Follow one operating review

**Command center**  
Start with coverage, vacancy, exposure, and the current review queue.

**Risk queue**  
Inspect the ranked 90-day voluntary attrition planning cohort and operational drivers.

**Floor outlook**  
Identify units with near-term staffing pressure.

**Playbook**  
Review recommended actions and a what-if scenario. Confirm that Apply is disabled.

**Ask Genie**  
Ask a governed question and inspect the generated SQL and result.

## Visual direction

Use a five-step demo storyboard with one screenshot placeholder from the App on the right. Keep this slide visible only briefly before switching to the live App.

## Speaker notes

Demo path:
1. Open Command.
2. Open Ellis M. on seed 42; explain that swaps, overtime, and tenure are demo-shaped operational drivers, not causal findings.
3. Open the Floor page; state that this synthetic system is chronically short, so the model ranks units rather than claiming rare-event detection.
4. Open Playbook; show 47 pending actions and click the disabled Apply control.
5. Show the bundle scenario. Typical result is high-risk 27 → 4 and roughly $1.9M assumed attrition delta; confirm live values first. Shortage flags remain 7.

---

# 6. Ask the governed data, not a black box

## On-slide content

### Genie is embedded in the workflow—with visible grounding.

Try:

- “What is 7-day coverage and vacancy?”
- “Who is high risk?”
- “Which units are flagged for 14-day shortage?”
- “What actions are recommended?”

The response includes the generated SQL and returned rows.

**Guardrail:** protected-class requests are refused before they reach Genie.

## Visual direction

Show a cropped Genie panel screenshot with three callouts: natural-language question, generated SQL, governed result. Include a small shield icon beside the refusal guardrail.

## Speaker notes

Demonstrate one grounded question. Then ask, “Break down attrition risk by race.” The application refuses because protected attributes are intentionally absent. An unknown metric such as `warp_flux_99` must not produce an invented definition.

---

# 7. Built natively on the Databricks Data Intelligence Platform

## On-slide content

### A governed path from source files to an operational application

**Source data**  
Synthetic HR, scheduling, timekeeping, absence, vacancy, and staffing CSVs in a Unity Catalog Volume

→ **Lakeflow**  
Bronze ingestion · Silver typing and quality rules · Gold operational features

→ **Unity Catalog**  
Governed tables, metric views, lineage, and service-principal access

→ **Scoring and planning**  
Attrition scores · shortage outlook · executive brief · actions · what-if scenarios

→ **Lakebase operational serving**
Triggered sync of executive brief · employee risk queue · shortage forecast

→ **Consumption**  
Databricks App (Lakebase + SQL warehouse) · Genie space

## Visual direction

Create a left-to-right architecture diagram. Put Unity Catalog as a governance band spanning Lakeflow, scoring, metric views, App, and Genie.

## Speaker notes

The workspace schema is `healthcare_ops.carestaff_insight`. Lakeflow produces the operational gold layer. Notebook 07 creates score and action tables. Notebook 08 creates four metric views. Notebook 09 syncs three serving tables into Lakebase Autoscaling. The FastAPI + React App reads live operational views from Lakebase and supporting analytics from the SQL warehouse; its embedded Genie experience calls the attached Genie space.

---

# 8. Databricks assets delivered

## On-slide content

### A complete workspace demonstration, not a standalone model

- **Lakeflow pipeline:** bronze, silver, and operational gold
- **Unity Catalog:** `healthcare_ops.carestaff_insight`
- **Four metric views:** coverage, as-of roster, attrition risk, unit shortage
- **Scoring notebook:** risk, shortage, model diagnostics, action and what-if tables
- **Lakebase Autoscaling:** three triggered synced tables for low-latency application reads
- **Databricks App:** React command center with a FastAPI backend
- **SQL warehouse resource:** supporting analytics and Genie query path
- **Genie space:** attached to the App for conversational analytics
- **Git folder:** repeatable source for pipeline, notebooks, App, tests, and documentation

**Deliberate choice:** no Model Serving endpoint; this prototype scores in process.

## Visual direction

Use a clean asset map with seven labeled tiles. Group them under Data Engineering, AI/Analytics, and Application.

## Speaker notes

Do not claim that the repository auto-deploys these assets. The workspace operator connected the Git folder, started the pipeline, ran the notebooks, created the App and Genie space, and attached the resources.

---

# 9. Governance is part of the product

## On-slide content

### Controls are visible, testable, and enforced in the workflow.

- **Synthetic-only data:** no PHI and no age, race, sex, SSN, ZIP, or disability attributes
- **Data quality:** typed silver layer with named quality rules and rejected test fixtures
- **Gold-only grounding:** the App and assistant cite governed outputs
- **Human review:** all recommendations remain `pending_human_review`
- **Read-only application:** no writes to gold, schedules, or HR systems
- **Transparent economics:** role-average assumptions, never individual pay
- **Scoped access:** App service principal uses catalog, schema, table, warehouse, and Genie grants

## Visual direction

Use a layered shield graphic with Data, Model, Action, and Access controls. Keep each control to one short phrase.

## Speaker notes

Show the disabled Apply control if challenged. Fairness slices use operational groupings such as role, unit, facility, tenure, and shift—not protected classes. The 90% coverage threshold is configuration, not a clinical staffing standard.

---

# 10. Why Databricks

## On-slide content

### One governed platform closes the gap between data work and operational use.

- **Lakeflow** turns fragmented feeds into reliable, testable workforce features.
- **Unity Catalog** provides one control plane for tables, metrics, lineage, and application identities.
- **Metric views** define reusable workforce measures for Genie and BI.
- **Genie** brings governed natural-language analysis into the operating workflow.
- **Databricks Apps** turns the data product into a focused experience for workforce leaders.
- **Open implementation** keeps the logic inspectable and portable.

## Visual direction

Use six product-value pairings around a central “governed workforce intelligence” circle. This is the platform payoff slide—not another architecture diagram.

## Speaker notes

The point is not “we trained a model.” The point is that engineering, metrics, AI, governance, and the end-user application share the same governed platform and data contracts.

---

# 11. What productionization would require

## On-slide content

### Move from a synthetic prototype to a monitored planning product

1. Connect approved HRIS, scheduling, timekeeping, absence, and vacancy feeds.
2. Validate definitions, thresholds, labels, and action policies with clinical and HR owners.
3. Establish temporal validation, drift monitoring, retraining, and approval criteria.
4. Complete privacy, security, legal, and employment-use review.
5. Pilot with a small set of units and measure workflow adoption before any impact claim.

## Visual direction

Show a five-stage roadmap: Connect → Validate → Govern → Pilot → Measure. Mark the current prototype just before Connect.

## Speaker notes

Do not frame the current build as production-ready. Model Serving is optional and should be added only if production latency, lifecycle, or scaling requirements justify it.

---

# 12. The decision to take forward

## On-slide content

### If this were your workforce snapshot, which three actions would a nursing director review this week?

**CareStaff Insight**

From fragmented workforce signals to governed, human-reviewed action.

## Visual direction

End with one large question and three empty action cards. Keep the slide visually quiet so the audience answers.

## Speaker notes

Stop presenting and invite the audience to choose three actions. The next conversation is not a production commitment; it is a definition workshop covering source systems, staffing measures, acceptable labels, review owners, and success criteria.
