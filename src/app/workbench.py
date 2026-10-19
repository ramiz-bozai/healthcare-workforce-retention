"""CareStaff Insight Streamlit workbench. Gold tables + allowlisted Ask. No applies."""

from __future__ import annotations

import streamlit as st

from data_generation.config import load_config
from src.ai.assistant import ask
from src.ai.tools import run_tool
from src.app.format import (
    ACTION_DISPLAY_COLS,
    ATTRITION_DISPLAY_COLS,
    DISCLAIMER,
    SHORTAGE_DISPLAY_COLS,
    WHATIF_DISPLAY_COLS,
    cite_value,
)
from src.app.load import (
    connect,
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
from src.ml.whatif import STATUS

PAGES = (
    "Overview",
    "Attrition risk",
    "Unit shortage",
    "Actions & what-if",
    "Ask",
    "Policy",
)

SAMPLE_QUESTIONS = (
    "What is 7-day coverage and vacancy?",
    "Who is high risk?",
    "Which units are flagged for 14-day shortage?",
    "What actions are recommended?",
    "What if we run the bundle stabilize scenario?",
    "How is coverage_ratio_7d calculated?",
    "Predict attrition risk for EMP-000001",
    "What is the valid ROC-AUC?",
)


def _con():
    if "gold_con" not in st.session_state:
        st.session_state.gold_con = connect()
        require_gold(st.session_state.gold_con)
    return st.session_state.gold_con


def _caption(cite: str) -> None:
    st.caption(cite)


def _metrics(cards: list[dict[str, str]], n_cols: int = 4) -> None:
    for i in range(0, len(cards), n_cols):
        cols = st.columns(n_cols)
        chunk = cards[i : i + n_cols]
        for col, card in zip(cols, chunk):
            col.metric(card["label"], card["value"])
            col.caption(card["cite"])


def page_overview(con) -> None:
    cfg = load_config("seed")
    pct = int(round((1.0 - float(cfg.raw["models"]["attrition_high_risk_quantile"])) * 100))
    brief = load_exec_brief(con).iloc[0]
    summary = load_action_summary(con).iloc[0]
    st.subheader("Executive snapshot")
    st.write(
        f"As of **{brief['as_of_date']}**. High-risk is the top {pct}% planning list — "
        "not an employment decision."
    )
    _metrics(overview_cards(brief))
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Recommended actions", cite_value("action_summary", "recommended_action_count", summary["recommended_action_count"]))
    c1.caption("gold.action_summary.recommended_action_count")
    c2.metric("Pending human review", cite_value("action_summary", "pending_human_review_count", summary["pending_human_review_count"]))
    c2.caption("gold.action_summary.pending_human_review_count")
    c3.metric("Applied", cite_value("action_summary", "applied_count", summary["applied_count"]))
    c3.caption("gold.action_summary.applied_count")
    st.info(str(brief.get("model_note") or brief.get("assumption_note") or DISCLAIMER))


def page_attrition(con) -> None:
    scores = load_risk_scores(con)
    high = scores.loc[scores["high_risk_flag"].astype(bool)].copy()
    st.subheader("High-risk planning list")
    st.write(
        f"{len(high)} of {len(scores)} active employees. Ranked by calibrated "
        "p(voluntary in 90 days). Not an employment decision."
    )
    st.dataframe(high[list(ATTRITION_DISPLAY_COLS)], hide_index=True, use_container_width=True)
    _caption("gold.employee_risk_scores WHERE high_risk_flag")
    chart = high.set_index("display_name")["p_voluntary_90d"].head(15)
    st.bar_chart(chart)
    _caption("gold.employee_risk_scores.p_voluntary_90d (display only)")

    options = [f"{row.display_name} · {row.employee_id}" for row in scores.itertuples()]
    picked = st.selectbox("Employee drill-down", options, index=0)
    eid = picked.rsplit("·", 1)[-1].strip()
    row = scores.loc[scores["employee_id"] == eid].iloc[0]
    left, right = st.columns(2)
    left.metric("Gold p(leave 90d)", cite_value("employee_risk_scores", "p_voluntary_90d", row["p_voluntary_90d"]))
    left.caption("gold.employee_risk_scores.p_voluntary_90d")
    left.write(f"Drivers: {row['drivers']}")
    left.write(f"Planning replacement: {cite_value('employee_risk_scores', 'planning_replacement_usd', row['planning_replacement_usd'])}")
    pred = run_tool("predict_attrition", con=con, params={"employee_id": eid}, model_dir=model_dir())
    if pred.rows:
        p = pred.rows[0]["p_voluntary_90d"]
        right.metric("In-process predict", cite_value("predict_attrition", "p_voluntary_90d", p))
        right.caption("in_process_predict · not Model Serving")
        right.write(f"serving = {pred.rows[0].get('serving')}")
    else:
        right.warning(pred.error or "No in-process score for that employee_id.")

    actions = load_actions(con)
    mine = actions.loc[actions["subject_id"] == eid]
    st.write("Recommended actions for this employee")
    if len(mine):
        st.dataframe(mine[list(ACTION_DISPLAY_COLS)], hide_index=True, use_container_width=True)
        _caption("gold.recommended_actions")
        st.caption(f"status is {STATUS} on every row. applied is false.")
    else:
        st.write("No playbook row for this employee.")

    with st.expander("Demo oracle — generator labels after as_of (not available in production)"):
        oracle = load_oracle_labels(con)
        show = high.merge(oracle, on="employee_id", how="left")
        st.dataframe(
            show[["risk_rank", "display_name", "employee_id", "p_voluntary_90d", "label_voluntary_90d"]],
            hide_index=True,
            use_container_width=True,
        )
        _caption("gold.employee_risk_scores.label_voluntary_90d · inference_demo_oracle")

    with st.expander("Operational fairness slices with review_flag"):
        slices = load_fairness_review(con)
        if len(slices):
            st.dataframe(slices, hide_index=True, use_container_width=True)
            _caption("gold.model_fairness_slices WHERE review_flag · role/facility/tenure/shift/unit only")
        else:
            st.write("No slices currently carry review_flag.")


def page_shortage(con) -> None:
    units = load_shortage(con)
    st.subheader("14-day unit shortage forecast")
    flagged = int(units["predicted_shortage_flag"].astype(bool).sum())
    st.write(f"{flagged} of {len(units)} units flagged at the policy probability cut.")
    st.dataframe(units[list(SHORTAGE_DISPLAY_COLS)], hide_index=True, use_container_width=True)
    _caption("gold.unit_shortage_forecast")
    st.bar_chart(units.set_index("department_id")["p_shortage_14d"])
    _caption("gold.unit_shortage_forecast.p_shortage_14d (display only)")
    actions = load_actions(con)
    unit_actions = actions.loc[actions["subject_type"] == "department"]
    st.write("Unit playbook rows")
    st.dataframe(unit_actions[list(ACTION_DISPLAY_COLS)], hide_index=True, use_container_width=True)
    _caption("gold.recommended_actions WHERE subject_type = department")


def page_actions(con) -> None:
    summary = load_action_summary(con).iloc[0]
    actions = load_actions(con)
    scenarios = load_whatif(con)
    st.subheader("Closed playbook")
    c1, c2, c3 = st.columns(3)
    c1.metric("Recommended", cite_value("action_summary", "recommended_action_count", summary["recommended_action_count"]))
    c2.metric("Pending human review", cite_value("action_summary", "pending_human_review_count", summary["pending_human_review_count"]))
    c3.metric("Applied", cite_value("action_summary", "applied_count", summary["applied_count"]))
    st.caption("gold.action_summary · every recommended_actions.status is pending_human_review")

    playbook = ["(all)"] + sorted(actions["playbook_action"].astype(str).unique().tolist())
    picked = st.selectbox("Playbook action", playbook)
    shown = actions if picked == "(all)" else actions.loc[actions["playbook_action"] == picked]
    st.dataframe(shown[list(ACTION_DISPLAY_COLS)], hide_index=True, use_container_width=True)
    _caption("gold.recommended_actions")
    st.button(
        "Apply selected action",
        disabled=True,
        help="Blocked. Decision 12: status is always pending_human_review. Gold is not written.",
    )
    st.warning("Apply is disabled. Nothing in this app writes to gold, silver, or the schedule.")

    st.subheader("What-if (assumed feature shifts, not savings)")
    st.dataframe(scenarios[list(WHATIF_DISPLAY_COLS)], hide_index=True, use_container_width=True)
    _caption("gold.whatif_scenarios")
    chart = scenarios.set_index("scenario_id")["high_risk_headcount"]
    st.bar_chart(chart)
    _caption("gold.whatif_scenarios.high_risk_headcount (display only)")
    st.info(
        "What-if perturbs a copy of features. It is not written back to gold. "
        "Deltas are assumed, not measured savings."
    )


def page_ask(con) -> None:
    st.subheader("Allowlisted assistant")
    st.write(
        "Template mode. Numbers come from gold SQL tools or in-process predict. "
        "Genie is not live."
    )
    sample = st.selectbox("Sample question", SAMPLE_QUESTIONS)
    question = st.text_input("Question", value=sample)
    if st.button("Ask", type="primary") and question.strip():
        turn = ask(question, con=con, model_dir=model_dir())
        st.markdown(turn.answer)
        st.caption(
            f"intent={turn.intent} · tools={','.join(turn.tools_called) or '-'} · "
            f"valid={turn.valid} · mode={turn.mode} · genie_live={turn.genie_live} · "
            f"model_serving_live={turn.model_serving_live}"
        )
        if not turn.valid:
            st.error(f"Validator unmatched: {turn.unmatched}")


def page_policy(con) -> None:
    cfg = load_config("seed")
    ai = cfg.raw["ai"]
    labels = cfg.raw["labels"]
    models = cfg.raw["models"]
    st.subheader("Locked policy")
    st.write(
        {
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
        }
    )
    _caption("conf/default.yaml")
    st.subheader("Metric catalog")
    st.dataframe(load_metric_catalog(con), hide_index=True, use_container_width=True)
    _caption("gold.metric_catalog — if a metric is not here, do not say it")
    st.subheader("Production-honest valid metrics")
    st.dataframe(load_valid_metrics(con), hide_index=True, use_container_width=True)
    _caption("gold.model_metrics WHERE split is valid")


def main() -> None:
    st.set_page_config(page_title="CareStaff Insight", layout="wide")
    cfg = load_config("seed")
    ai = cfg.raw.get("ai", {})
    with st.sidebar:
        st.title("CareStaff Insight")
        st.caption("Workforce retention planning · synthetic")
        st.write(f"as_of **{cfg.as_of_date.isoformat()}**")
        st.write(f"Genie live: **{bool(ai.get('genie_live', False))}**")
        st.write(f"Model Serving live: **{bool(ai.get('model_serving_live', False))}**")
        st.write("Predict: **in-process**")
        page = st.radio("Workbench", PAGES, index=0)
        st.divider()
        st.caption(DISCLAIMER)
    try:
        con = _con()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()
        return
    pages = {
        "Overview": page_overview,
        "Attrition risk": page_attrition,
        "Unit shortage": page_shortage,
        "Actions & what-if": page_actions,
        "Ask": page_ask,
        "Policy": page_policy,
    }
    pages[page](con)
    st.divider()
    st.caption(DISCLAIMER)
