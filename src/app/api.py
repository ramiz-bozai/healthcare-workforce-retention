"""JSON payloads for the React workbench. Reads gold. Does not apply actions."""

from __future__ import annotations

from src.ai.assistant import ask, route
from src.app.format import (
    ACTION_DISPLAY_COLS,
    ATTRITION_DISPLAY_COLS,
    DISCLAIMER,
    SHORTAGE_DISPLAY_COLS,
    WHATIF_DISPLAY_COLS,
)
from src.app.jsonutil import records, row
from src.app.load import (
    load_action_summary,
    load_actions,
    load_exec_brief,
    load_fairness_review,
    load_metric_catalog,
    load_oracle_labels,
    load_risk_scores,
    load_shortage,
    load_valid_metrics,
    load_whatif,
    model_dir,
    overview_cards,
    require_gold,
)
from src.ai.tools import run_tool
from src.app.genie import ask_genie, is_live
from data_generation.config import load_config
from src.ml.whatif import STATUS

SAMPLE_QUESTIONS = [
    "What is 7-day coverage and vacancy?",
    "Who is high risk?",
    "Which units are flagged for 14-day shortage?",
    "What actions are recommended?",
    "What if we run the bundle stabilize scenario?",
    "How is coverage_ratio_7d calculated?",
    "Predict attrition risk for EMP-000001",
    "What is the valid ROC-AUC?",
    "Break down attrition risk by race.",
]


def _cols(frame, columns: tuple[str, ...]):
    keep = [c for c in columns if c in frame.columns]
    return records(frame[keep])


def overview_payload(con) -> dict:
    require_gold(con)
    cfg = load_config("seed")
    brief = load_exec_brief(con)
    summary = load_action_summary(con)
    brief_row = brief.iloc[0]
    scores = load_risk_scores(con)
    high = scores.loc[scores["high_risk_flag"].astype(bool)].head(6)
    pct = int(round((1.0 - float(cfg.raw["models"]["attrition_high_risk_quantile"])) * 100))
    return {
        "as_of": cfg.as_of_date.isoformat(),
        "high_risk_percentile": pct,
        "disclaimer": DISCLAIMER,
        "note": str(brief_row.get("model_note") or brief_row.get("assumption_note") or DISCLAIMER),
        "cards": overview_cards(brief_row),
        "summary": row(summary),
        "preview_risk": _cols(high, ATTRITION_DISPLAY_COLS),
        "preview_units": _cols(load_shortage(con).head(6), SHORTAGE_DISPLAY_COLS),
        "genie_live": is_live(),
        "model_serving_live": bool(cfg.raw["ai"]["model_serving_live"]),
        "mode": "genie" if is_live() else cfg.raw["ai"]["mode"],
        "serving": "in_process_predict",
    }


def attrition_payload(con) -> dict:
    scores = load_risk_scores(con)
    high = scores.loc[scores["high_risk_flag"].astype(bool)].copy()
    return {
        "n_high": int(len(high)),
        "n_active": int(len(scores)),
        "high_risk": _cols(high, ATTRITION_DISPLAY_COLS),
        "employees": records(scores[["employee_id", "display_name", "role_code", "department_id"]]),
        "cite": "gold.employee_risk_scores WHERE high_risk_flag",
        "status": STATUS,
    }


def attrition_detail_payload(con, employee_id: str) -> dict:
    scores = load_risk_scores(con)
    hit = scores.loc[scores["employee_id"] == employee_id]
    if hit.empty:
        raise FileNotFoundError(f"No gold.employee_risk_scores row for {employee_id}")
    row_score = records(hit)[0]
    pred = run_tool("predict_attrition", con=con, params={"employee_id": employee_id}, model_dir=model_dir())
    actions = load_actions(con)
    mine = actions.loc[actions["subject_id"] == employee_id]
    oracle = load_oracle_labels(con)
    ora = oracle.loc[oracle["employee_id"] == employee_id]
    slices = load_fairness_review(con)
    return {
        "score": row_score,
        "predict": {"rows": pred.rows, "error": pred.error, "serving": "in_process_predict"},
        "actions": _cols(mine, ACTION_DISPLAY_COLS),
        "oracle": records(ora),
        "fairness": records(slices),
        "status": STATUS,
    }


def shortage_payload(con) -> dict:
    units = load_shortage(con)
    flagged = int(units["predicted_shortage_flag"].astype(bool).sum())
    actions = load_actions(con)
    unit_actions = actions.loc[actions["subject_type"] == "department"]
    return {
        "n_flagged": flagged,
        "n_units": int(len(units)),
        "units": _cols(units, SHORTAGE_DISPLAY_COLS),
        "actions": _cols(unit_actions, ACTION_DISPLAY_COLS),
        "cite": "gold.unit_shortage_forecast",
    }


def actions_payload(con, playbook: str | None = None) -> dict:
    summary = load_action_summary(con)
    actions = load_actions(con)
    scenarios = load_whatif(con)
    options = sorted(actions["playbook_action"].astype(str).unique().tolist())
    shown = actions if not playbook or playbook == "(all)" else actions.loc[actions["playbook_action"] == playbook]
    return {
        "summary": row(summary),
        "playbooks": ["(all)"] + options,
        "actions": _cols(shown, ACTION_DISPLAY_COLS),
        "scenarios": _cols(scenarios, WHATIF_DISPLAY_COLS),
        "apply_enabled": False,
        "status": STATUS,
        "cite": "gold.recommended_actions",
    }


def policy_payload(con) -> dict:
    cfg = load_config("seed")
    ai = cfg.raw["ai"]
    labels = cfg.raw["labels"]
    models = cfg.raw["models"]
    return {
        "policy": {
            "as_of_date": cfg.as_of_date.isoformat(),
            "random_seed": cfg.random_seed,
            "ai.mode": ai["mode"],
            "ai.genie_live": ai["genie_live"],
            "ai.model_serving_live": ai["model_serving_live"],
            "serving": "in_process_predict",
            "attrition_horizon_days": labels["attrition_horizon_days"],
            "shortage_primary_horizon_days": labels["shortage_primary_horizon_days"],
            "coverage_threshold": labels["shortage_coverage_ratio_threshold"],
            "open_shift_threshold": labels["shortage_open_shift_share_threshold"],
            "high_risk_quantile": models["attrition_high_risk_quantile"],
            "require_human_review": cfg.raw["actions"]["require_human_review"],
            "playbook": cfg.raw["actions"]["playbook"],
            "cost_note": cfg.cost.note,
        },
        "metrics": records(load_metric_catalog(con)),
        "valid_metrics": records(load_valid_metrics(con)),
        "disclaimer": DISCLAIMER,
        "sample_questions": SAMPLE_QUESTIONS,
        "genie_live": is_live(),
    }


def _template_ask(con, question: str) -> dict:
    turn = ask(question, con=con, model_dir=model_dir())
    return {
        "question": turn.question,
        "answer": turn.answer,
        "intent": turn.intent,
        "tools_called": turn.tools_called,
        "valid": turn.valid,
        "unmatched": turn.unmatched,
        "mode": turn.mode,
        "genie_live": False,
        "model_serving_live": turn.model_serving_live,
        "conversation_id": None,
        "sql": [],
        "rows": [],
        "suggested": [],
        "error": None,
    }


def ask_payload(con, question: str, conversation_id: str | None = None) -> dict:
    intent, _planned = route(question)
    if intent.startswith("refuse") or not is_live():
        return _template_ask(con, question)
    try:
        return ask_genie(question, conversation_id)
    except Exception as exc:
        fallback = _template_ask(con, question)
        fallback["mode"] = "template_fallback"
        fallback["error"] = str(exc)
        fallback["answer"] = (
            f"Genie did not answer ({exc}). Falling back to allowlisted gold tools.\n\n"
            + fallback["answer"]
        )
        return fallback
