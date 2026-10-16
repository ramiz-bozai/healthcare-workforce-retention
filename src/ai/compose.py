"""Template narration. Every KPI is interpolated from a NumberBank citation."""

from __future__ import annotations

from src.ai.tools import ToolResult
from src.ai.validate import NumberBank, bank_from_results, format_value

DISCLAIMER = (
    "Not Genie. Not Model Serving. Tools ran in-process against gold. "
    "Recommended actions stay pending_human_review and are not applied. "
    "Dollar figures are role-average planning assumptions, not measured savings."
)

REFUSE_PROTECTED = (
    "I only use operational slices (role, unit, facility, tenure band, shift). "
    "Protected characteristics are not in this dataset and I will not infer them."
)
REFUSE_APPLY = (
    "I cannot apply or auto-execute playbook actions. "
    "Every recommended action is pending_human_review."
)
REFUSE_SQL = (
    "I do not run free-form SQL. Ask for a KPI, roster, forecast, formula, "
    "what-if scenario, or in-process score, and I will call an allowlisted tool."
)
REFUSE_DECISION = (
    "This is a planning signal, not an employment decision. "
    "I will not recommend firing, terminating, or blocking a shift."
)


def _sources(results: list[ToolResult]) -> str:
    parts = []
    for result in results:
        tables = ", ".join(result.tables)
        parts.append(f"{result.tool_id} ({tables})")
    return "Sources: " + "; ".join(parts) + "."


def _footer(results: list[ToolResult]) -> str:
    return _sources(results) + "\n" + DISCLAIMER


def _driver_name(raw: object) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    return text.split("=", 1)[0].strip()


def _drivers(row: dict, cols: tuple[str, ...] = ("driver_1", "driver_2", "driver_3")) -> str:
    names = [_driver_name(row.get(col)) for col in cols]
    return "/".join(name for name in names if name)


def _first(results: list[ToolResult], tool_id: str) -> ToolResult | None:
    for result in results:
        if result.tool_id == tool_id:
            return result
    return None


def _row_cite_prefix(result: ToolResult | None) -> str:
    if result is None or not result.rows:
        return result.tool_id if result else ""
    if len(result.rows) == 1:
        return result.tool_id
    return f"{result.tool_id}[0]"


def _lines_high_risk(bank: NumberBank, result: ToolResult | None, limit: int = 8) -> list[str]:
    if result is None or not result.rows:
        return ["No high-risk rows returned."]
    lines = []
    for i, row in enumerate(result.rows[:limit]):
        prefix = result.tool_id if len(result.rows) == 1 else f"{result.tool_id}[{i}]"
        name = row.get("display_name") or row.get("employee_id")
        role = row.get("role_code")
        dept = row.get("department_id")
        p = bank.cite(f"{prefix}.p_voluntary_90d")
        drivers = _drivers(row)
        extra = f" drivers {drivers}" if drivers else ""
        lines.append(f"- {name} ({role}, {dept}) p={p}{extra}")
    return lines


def _lines_units(bank: NumberBank, result: ToolResult | None) -> list[str]:
    if result is None or not result.rows:
        return ["No unit forecast rows returned."]
    lines = []
    for i, row in enumerate(result.rows):
        prefix = result.tool_id if len(result.rows) == 1 else f"{result.tool_id}[{i}]"
        dept = row.get("department_id")
        p = bank.cite(f"{prefix}.p_shortage_14d")
        flag = "flagged" if row.get("predicted_shortage_flag") else "not flagged"
        cov = bank.cite(f"{prefix}.avg_coverage_ratio")
        usd = bank.cite(f"{prefix}.planning_coverage_exposure_usd")
        lines.append(f"- {dept} p={p} ({flag}); coverage {cov}; planning exposure {usd}")
    return lines


def _scenario_line(bank: NumberBank, result: ToolResult, scenario_id: str) -> str | None:
    for i, row in enumerate(result.rows):
        if row.get("scenario_id") != scenario_id:
            continue
        prefix = result.tool_id if len(result.rows) == 1 else f"{result.tool_id}[{i}]"
        return (
            f"{scenario_id}: high-risk {bank.cite(f'{prefix}.high_risk_headcount')}; "
            f"mean p {bank.cite(f'{prefix}.mean_p_attrition')}; "
            f"attrition exposure {bank.cite(f'{prefix}.planning_attrition_exposure_usd')}; "
            f"attrition delta {bank.cite(f'{prefix}.planning_attrition_delta_usd')}; "
            f"flagged units {bank.cite(f'{prefix}.flagged_units')}; "
            f"coverage delta {bank.cite(f'{prefix}.planning_coverage_delta_usd')}"
        )
    return None


def compose_exec(bank: NumberBank, results: list[ToolResult]) -> str:
    brief = _first(results, "exec_brief")
    pfx = _row_cite_prefix(brief)
    policy = _first(results, "policy")
    pol = _row_cite_prefix(policy)
    lookback = int(bank.get(f"{pol}.coverage_lookback_days"))
    horizon = int(bank.get(f"{pol}.attrition_horizon_days"))
    shortage_h = int(bank.get(f"{pol}.shortage_primary_horizon_days"))
    ot_days = int(bank.get(f"{pol}.overtime_lookback_days"))
    pct = int(bank.get(f"{pol}.high_risk_percentile"))
    lines = [
        f"As of {bank.cite(f'{pol}.as_of_date')}:",
        f"- Active headcount {bank.cite(f'{pfx}.active_headcount')}",
        f"- Vacancy rate {bank.cite(f'{pfx}.vacancy_rate')} (open FTE {bank.cite(f'{pfx}.open_fte')})",
        f"- {lookback}-day coverage ratio {bank.cite(f'{pfx}.coverage_ratio_7d')}",
        f"- Observed voluntary exits in {horizon} days "
        f"{bank.cite(f'{pfx}.observed_voluntary_exits_90d')} "
        f"(rate {bank.cite(f'{pfx}.observed_attrition_rate_90d')})",
        f"- High-risk planning list (top {pct} percent) "
        f"{bank.cite(f'{pfx}.high_risk_headcount')}; mean predicted p "
        f"{bank.cite(f'{pfx}.predicted_attrition_rate_90d')}",
        f"- Planning attrition exposure {bank.cite(f'{pfx}.planning_attrition_exposure_usd')}",
        f"- Predicted shortage units ({shortage_h}-day) "
        f"{bank.cite(f'{pfx}.predicted_shortage_units_14d')}; coverage exposure "
        f"{bank.cite(f'{pfx}.planning_coverage_exposure_usd')}",
        f"- Overtime hours ({ot_days}-day) {bank.cite(f'{pfx}.overtime_hours_30d')}",
    ]
    return "\n".join(lines)


def compose_high_risk(bank: NumberBank, results: list[ToolResult]) -> str:
    brief = _first(results, "exec_brief")
    pfx = _row_cite_prefix(brief)
    policy = _first(results, "policy")
    pol = _row_cite_prefix(policy)
    risk = _first(results, "high_risk_list")
    pct = int(bank.get(f"{pol}.high_risk_percentile"))
    header = (
        f"High-risk is the top {pct} percent by calibrated p "
        f"at {bank.cite(f'{pol}.as_of_date')} — a planning list, not an employment decision. "
        f"Headcount {bank.cite(f'{pfx}.high_risk_headcount')}; planning exposure "
        f"{bank.cite(f'{pfx}.planning_attrition_exposure_usd')}."
    )
    return header + "\n" + "\n".join(_lines_high_risk(bank, risk))


def compose_shortage(bank: NumberBank, results: list[ToolResult]) -> str:
    brief = _first(results, "exec_brief")
    pfx = _row_cite_prefix(brief)
    policy = _first(results, "policy")
    pol = _row_cite_prefix(policy)
    units = _first(results, "unit_shortage")
    shortage_h = int(bank.get(f"{pol}.shortage_primary_horizon_days"))
    header = (
        f"Units flagged when calibrated p(shortage in next {shortage_h} days) is at least "
        f"{bank.cite(f'{pol}.shortage_flag_min_probability')}. "
        f"Flagged units {bank.cite(f'{pfx}.predicted_shortage_units_14d')}; "
        f"planning coverage exposure {bank.cite(f'{pfx}.planning_coverage_exposure_usd')}."
    )
    return header + "\n" + "\n".join(_lines_units(bank, units))


def compose_actions(bank: NumberBank, results: list[ToolResult]) -> str:
    summary = _first(results, "action_summary")
    spx = _row_cite_prefix(summary)
    actions = _first(results, "recommended_actions")
    header = (
        f"Recommended actions {bank.cite(f'{spx}.recommended_action_count')}; "
        f"pending human review {bank.cite(f'{spx}.pending_human_review_count')}; "
        f"applied {bank.cite(f'{spx}.applied_count')}. Closed playbook only. Nothing is auto-applied."
    )
    lines = [header]
    if actions and actions.rows:
        for i, row in enumerate(actions.rows):
            prefix = actions.tool_id if len(actions.rows) == 1 else f"{actions.tool_id}[{i}]"
            lines.append(
                f"- {row.get('action_id')} {row.get('display_name')} "
                f"{row.get('playbook_action')} p {bank.cite(f'{prefix}.baseline_p')} → "
                f"{bank.cite(f'{prefix}.scenario_p')}; assumed delta "
                f"{bank.cite(f'{prefix}.planning_delta_usd')}; status {row.get('status')}; "
                f"applied {format_value(f'{prefix}.applied', row.get('applied'))}"
            )
    return "\n".join(lines)


def compose_whatif(bank: NumberBank, results: list[ToolResult]) -> str:
    scenarios = _first(results, "whatif_scenarios") or _first(results, "whatif_scenario")
    if scenarios is None or not scenarios.rows:
        return "No what-if scenarios returned."
    lines = [
        "What-if perturbs a copy of features. It is not written back to gold. "
        "Deltas are assumed, not measured savings."
    ]
    for scenario_id in (
        "baseline",
        "stabilize_high_risk",
        "cut_ot_high_risk",
        "recruit_short_units",
        "review_ot_short_units",
        "bundle_stabilize_ot_recruit",
    ):
        line = _scenario_line(bank, scenarios, scenario_id)
        if line:
            lines.append(f"- {line}")
    return "\n".join(lines)


def compose_formula(bank: NumberBank, results: list[ToolResult]) -> str:
    formula = _first(results, "metric_formula")
    if formula is None or not formula.rows:
        return (
            "That metric is not in gold.metric_catalog. I will not invent a formula. "
            "Ask for a name from the catalog."
        )
    row = formula.rows[0]
    pfx = _row_cite_prefix(formula)
    return (
        f"{bank.cite(f'{pfx}.metric_name')} is stored on {bank.cite(f'{pfx}.table_name')} "
        f"at grain {bank.cite(f'{pfx}.grain')}. Formula:\n"
        f"> {row.get('formula')}"
    )


def compose_employee(bank: NumberBank, results: list[ToolResult]) -> str:
    scored = _first(results, "employee_score")
    pred = _first(results, "predict_attrition")
    if scored is None or not scored.rows:
        return "That employee_id is not on the as_of risk list."
    row = scored.rows[0]
    spx = _row_cite_prefix(scored)
    lines = [
        f"{row.get('display_name')} ({row.get('role_code')}, {row.get('department_id')}) "
        f"gold p {bank.cite(f'{spx}.p_voluntary_90d')}; high-risk flag "
        f"{format_value(f'{spx}.high_risk_flag', row.get('high_risk_flag'))}; rank "
        f"{bank.cite(f'{spx}.risk_rank')}; planning replacement "
        f"{bank.cite(f'{spx}.planning_replacement_usd')}.",
        f"Drivers: {_drivers(row)}.",
    ]
    if pred and pred.rows:
        ppx = _row_cite_prefix(pred)
        serving = pred.rows[0].get("serving")
        lines.append(
            f"In-process predict p {bank.cite(f'{ppx}.p_voluntary_90d')} ({serving})."
        )
    elif pred and pred.error:
        lines.append(f"In-process predict unavailable: {pred.error}")
    return "\n".join(lines)


def compose_metrics(bank: NumberBank, results: list[ToolResult]) -> str:
    metrics = _first(results, "model_metrics_valid")
    if metrics is None or not metrics.rows:
        return "No valid-split metrics returned."
    lines = ["Production-honest valid split (labels fully realized by as_of). Not inference-oracle."]
    for i, row in enumerate(metrics.rows):
        prefix = metrics.tool_id if len(metrics.rows) == 1 else f"{metrics.tool_id}[{i}]"
        lines.append(
            f"- {row.get('model')} {row.get('split')} {row.get('metric')} "
            f"{bank.cite(f'{prefix}.value')}"
        )
    return "\n".join(lines)


def compose_fairness(bank: NumberBank, results: list[ToolResult]) -> str:
    slices = _first(results, "fairness_review")
    header = (
        "Fairness slices are operational only (role, facility, tenure band, shift, unit). "
        "Protected classes are not in the data."
    )
    if slices is None or not slices.rows:
        return header + "\nNo slices currently carry review_flag."
    lines = [header]
    for i, row in enumerate(slices.rows):
        prefix = slices.tool_id if len(slices.rows) == 1 else f"{slices.tool_id}[{i}]"
        lines.append(
            f"- {row.get('model')} {row.get('slice_column')}={row.get('slice_value')} "
            f"n {bank.cite(f'{prefix}.n')}; base rate {bank.cite(f'{prefix}.base_rate')}; "
            f"selection {bank.cite(f'{prefix}.selection_rate')}"
        )
    return "\n".join(lines)


def compose_unknown(bank: NumberBank, results: list[ToolResult]) -> str:
    brief = _first(results, "exec_brief")
    if brief and brief.rows:
        return (
            "I did not match a more specific tool path. Executive snapshot from gold.exec_brief:\n"
            + compose_exec(bank, results)
        )
    return (
        "I can answer from allowlisted tools only: exec KPIs, high-risk list, unit shortage, "
        "metric formulas, pending actions, what-if scenarios, valid metrics, "
        "or in-process predict for an employee_id / department_id."
    )


TEMPLATES = {
    "exec": compose_exec,
    "high_risk": compose_high_risk,
    "shortage": compose_shortage,
    "actions": compose_actions,
    "whatif": compose_whatif,
    "formula": compose_formula,
    "employee": compose_employee,
    "metrics": compose_metrics,
    "fairness": compose_fairness,
    "unknown": compose_unknown,
}

REFUSALS = {
    "refuse_protected": REFUSE_PROTECTED,
    "refuse_apply": REFUSE_APPLY,
    "refuse_sql": REFUSE_SQL,
    "refuse_decision": REFUSE_DECISION,
}


def compose(intent: str, results: list[ToolResult]) -> str:
    if intent in REFUSALS:
        return REFUSALS[intent]
    bank = bank_from_results(results)
    body = TEMPLATES.get(intent, compose_unknown)(bank, results)
    if not results:
        return body
    return body + "\n\n" + _footer(results)
