"""Route a question to allowlisted tools, then template-narrate with citations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from data_generation.config import GenerationConfig, load_config
from src.ai.compose import compose
from src.ai.tools import run_tool, ToolResult
from src.ai.validate import validate_answer
from src.common.paths import DEFAULT_DUCKDB, MODEL_DIR

EMP_IN_TEXT = re.compile(r"EMP-\d{6}")
DEPT_IN_TEXT = re.compile(r"\b[A-Z]{2,5}-[A-Z0-9-]{1,24}\b")
SQL_FREEFORM = re.compile(
    r"\b(select|insert|update|delete|drop|union|alter|truncate)\b.*\b(from|table|into|gold|silver|bronze)\b",
    re.I | re.S,
)
PROTECTED = re.compile(
    r"\b(race|ethnicity|gender|sex|religion|disability|ssn|social security|"
    r"zip code|zip|national origin|pregnancy|age group|age|protected class)\b",
    re.I,
)
APPLY = re.compile(
    r"\b(auto-?apply|apply these|apply all|execute the action|approve all|"
    r"write back|push to payroll|implement these actions)\b",
    re.I,
)
DECISION = re.compile(
    r"\b(fire|firing|fired|terminate|termination|demote|do not hire|block (their|the) shift)\b",
    re.I,
)

METRIC_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("coverage_ratio_7d", ("coverage_ratio_7d", "7-day coverage", "7 day coverage", "coverage ratio")),
    ("observed_attrition_rate_90d", ("observed attrition", "observed voluntary")),
    ("predicted_attrition_rate_90d", ("predicted attrition", "mean p")),
    ("planning_attrition_exposure_usd", ("attrition exposure", "replacement cost")),
    ("planning_coverage_exposure_usd", ("coverage exposure",)),
    ("vacancy_rate", ("vacancy rate", "vacancy")),
    ("active_headcount", ("active headcount", "headcount")),
    ("overtime_hours_30d", ("overtime hours", "overtime")),
    ("unplanned_absence_rate_30d", ("unplanned absence", "callout")),
    ("trailing_coverage_gap_hours_14d", ("coverage gap", "gap hours")),
    ("high_risk_headcount", ("high-risk headcount", "high risk headcount")),
    ("label_voluntary_90d", ("voluntary 90", "attrition label")),
    ("is_shortage_day", ("shortage day",)),
    ("label_shortage_next_14d", ("shortage label", "14-day shortage label")),
)

REQUIRED_GOLD = (
    "exec_brief",
    "employee_risk_scores",
    "unit_shortage_forecast",
    "recommended_actions",
    "whatif_scenarios",
    "metric_catalog",
    "action_summary",
    "model_metrics",
)


@dataclass
class AssistantTurn:
    question: str
    intent: str
    tools_called: list[str]
    results: list[ToolResult] = field(default_factory=list)
    answer: str = ""
    valid: bool = False
    unmatched: list[str] = field(default_factory=list)
    mode: str = "template"
    genie_live: bool = False
    model_serving_live: bool = False


def _gold_tables(con) -> set[str]:
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'gold'"
    ).fetchall()
    return {r[0] for r in rows}


def extract_metric_name(question: str) -> str | None:
    lowered = question.lower()
    for metric, aliases in METRIC_ALIASES:
        for alias in aliases:
            if alias in lowered:
                return metric
    match = re.search(r"\b([a-z]+_[a-z0-9_]+)\b", lowered)
    if match:
        return match.group(1)
    return None


def route(question: str) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
    q = question.strip()
    if not q:
        return "unknown", [("policy", {}), ("exec_brief", {})]
    if SQL_FREEFORM.search(q):
        return "refuse_sql", []
    if PROTECTED.search(q):
        return "refuse_protected", []
    if APPLY.search(q):
        return "refuse_apply", []
    if DECISION.search(q):
        return "refuse_decision", []

    lowered = q.lower()
    emp = EMP_IN_TEXT.search(q)
    dept = DEPT_IN_TEXT.search(q)
    calls: list[tuple[str, dict[str, Any]]] = [("policy", {})]

    formula_ask = any(tok in lowered for tok in ("formula", "how is", "calculated", "definition of"))
    if formula_ask:
        metric = extract_metric_name(q)
        if metric:
            calls.append(("metric_formula", {"metric_name": metric}))
        else:
            calls.append(("metric_catalog", {}))
        return "formula", calls

    if emp and any(tok in lowered for tok in ("score", "predict", "risk", "p for", "probability")):
        calls.append(("employee_score", {"employee_id": emp.group()}))
        calls.append(("predict_attrition", {"employee_id": emp.group()}))
        return "employee", calls

    if dept and any(tok in lowered for tok in ("score", "predict", "shortage")):
        calls.append(("unit_shortage", {}))
        calls.append(("predict_shortage", {"department_id": dept.group()}))
        return "shortage", calls

    if any(tok in lowered for tok in ("what-if", "what if", "scenario", "bundle", "stabilize", "assumed delta")):
        calls.append(("whatif_scenarios", {}))
        calls.append(("action_summary", {}))
        return "whatif", calls

    if any(tok in lowered for tok in ("action", "playbook", "recommend", "outreach", "pending")):
        calls.append(("action_summary", {}))
        calls.append(("recommended_actions", {"limit": 8}))
        return "actions", calls

    if any(tok in lowered for tok in ("high-risk", "high risk", "who might leave", "attrition risk", "leavers")):
        calls.append(("exec_brief", {}))
        calls.append(("high_risk_list", {"limit": 8}))
        return "high_risk", calls

    if any(tok in lowered for tok in ("shortage", "which unit", "short staff", "flagged unit", "14-day", "14 day")):
        calls.append(("exec_brief", {}))
        calls.append(("unit_shortage", {}))
        return "shortage", calls

    if any(tok in lowered for tok in ("roc-auc", "roc_auc", "brier", "calibration", "valid split", "auc")):
        calls.append(("model_metrics_valid", {}))
        return "metrics", calls

    if any(tok in lowered for tok in ("fairness", "disparity", "slice")):
        calls.append(("fairness_review", {}))
        return "fairness", calls

    if any(
        tok in lowered
        for tok in (
            "coverage",
            "vacancy",
            "headcount",
            "kpi",
            "overtime",
            "exposure",
            "dollar",
            "brief",
            "executive",
        )
    ):
        calls.append(("exec_brief", {}))
        return "exec", calls

    calls.append(("exec_brief", {}))
    calls.append(("action_summary", {}))
    return "unknown", calls


UNGROUNDED = (
    "I cannot answer with ungrounded numbers. The template produced values that "
    "were not in the tool payload, so the prose was discarded."
)


def ask(
    question: str,
    *,
    con=None,
    duckdb_path: Path | str | None = None,
    model_dir: Path | str | None = None,
    profile: str = "seed",
    cfg: GenerationConfig | None = None,
) -> AssistantTurn:
    config = cfg or load_config(profile)
    ai = config.raw.get("ai", {})
    mode = str(ai.get("mode", "template"))
    genie_live = bool(ai.get("genie_live", False))
    serving_live = bool(ai.get("model_serving_live", False))
    intent, planned = route(question)
    own = False
    connection = con
    if intent.startswith("refuse"):
        answer = compose(intent, [])
        return AssistantTurn(
            question=question,
            intent=intent,
            tools_called=[],
            results=[],
            answer=answer,
            valid=True,
            unmatched=[],
            mode=mode,
            genie_live=genie_live,
            model_serving_live=serving_live,
        )
    if connection is None:
        path = Path(duckdb_path or DEFAULT_DUCKDB)
        if not path.exists():
            raise FileNotFoundError(f"{path} missing. Run `uv run python -m src.pipeline` then `uv run python -m src.ml`.")
        connection = duckdb.connect(str(path), read_only=True)
        own = True
    try:
        missing = [name for name in REQUIRED_GOLD if name not in _gold_tables(connection)]
        if missing:
            raise FileNotFoundError(
                f"Gold tables missing {missing}. Run `uv run python -m src.pipeline` then `uv run python -m src.ml`."
            )
        results: list[ToolResult] = []
        called: list[str] = []
        models = Path(model_dir) if model_dir else MODEL_DIR
        for tool_id, params in planned:
            result = run_tool(
                tool_id,
                con=connection,
                params=params,
                cfg=config,
                model_dir=models,
            )
            results.append(result)
            called.append(tool_id)
        try:
            answer = compose(intent, results)
        except KeyError as exc:
            answer = f"Tool payload missing {exc}. I will not invent the number.\n\n" + compose(
                "unknown", results
            )
        valid, unmatched = validate_answer(answer, results)
        if not valid:
            answer = UNGROUNDED + " Tools: " + ", ".join(called) + "."
            valid, unmatched = validate_answer(answer, results)
        return AssistantTurn(
            question=question,
            intent=intent,
            tools_called=called,
            results=results,
            answer=answer,
            valid=valid,
            unmatched=unmatched,
            mode=mode,
            genie_live=genie_live,
            model_serving_live=serving_live,
        )
    finally:
        if own and connection is not None:
            connection.close()
