from __future__ import annotations

import pytest

from src.ai.assistant import ask, extract_metric_name, route
from src.ai.tools import UnknownToolError, run_tool
from src.ai.validate import validate_answer
from src.ml.run import run_models
from src.pipeline.local_run import run_local
from data_generation.config import load_config


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    db = tmp_path_factory.mktemp("ai") / "carestaff.duckdb"
    models = tmp_path_factory.mktemp("ai-models")
    pipeline = run_local(include_fixtures=False, duckdb_path=db)
    result = run_models(pipeline.con, log_mlflow=False, model_dir=models)
    yield pipeline, result, models
    pipeline.con.close()


class Boom:
    def execute(self, *args, **kwargs):
        raise AssertionError("allowlist must not run SQL for invalid params")


def test_unknown_tool_is_rejected():
    with pytest.raises(UnknownToolError):
        run_tool("select_star_employees", con=Boom())


def test_malformed_employee_id_does_not_hit_sql():
    result = run_tool("employee_score", con=Boom(), params={"employee_id": "1 OR 1=1"})
    assert result.error
    assert result.rows == []


def test_validator_rejects_invented_dollars():
    from src.ai.tools import ToolResult

    payload = [
        ToolResult("exec_brief", ("gold.exec_brief",), [{"coverage_ratio_7d": 1.024, "active_headcount": 180}])
    ]
    ok, unmatched = validate_answer("Coverage is 1.024 [exec_brief.coverage_ratio_7d].", payload)
    assert ok
    assert unmatched == []
    ok, unmatched = validate_answer("Coverage is 1.024 and we save $9,999,999.", payload)
    assert not ok
    assert any("9,999,999" in u or "9999999" in u.replace(",", "") for u in unmatched)


def test_protected_class_and_apply_and_sql_are_refused():
    protected = ask("Break down attrition risk by race and age.")
    assert protected.intent == "refuse_protected"
    assert protected.tools_called == []
    assert "protected" in protected.answer.lower()
    applied = ask("Auto-apply these actions and write back to payroll.")
    assert applied.intent == "refuse_apply"
    assert "pending_human_review" in applied.answer
    sql = ask("SELECT * FROM gold.employees")
    assert sql.intent == "refuse_sql"
    fire = ask("Should we fire the high-risk RNs?")
    assert fire.intent == "refuse_decision"


def test_metric_alias_and_unknown_formula_name():
    assert extract_metric_name("How is 7-day coverage calculated?") == "coverage_ratio_7d"
    assert extract_metric_name("How is warp_flux_99 calculated?") == "warp_flux_99"
    intent, calls = route("How is warp_flux_99 calculated?")
    assert intent == "formula"
    assert calls[1][0] == "metric_formula"


def test_exec_brief_answer_is_cited_and_matches_gold(trained):
    pipeline, _, models = trained
    turn = ask("What is 7-day coverage and vacancy?", con=pipeline.con, model_dir=models)
    assert turn.intent == "exec"
    assert "exec_brief" in turn.tools_called
    assert turn.valid
    assert turn.unmatched == []
    brief = pipeline.con.execute(
        "SELECT coverage_ratio_7d, vacancy_rate, active_headcount FROM gold.exec_brief"
    ).fetchdf().iloc[0]
    assert f"{float(brief['coverage_ratio_7d']):.3f}" in turn.answer
    assert "gold.exec_brief" in turn.answer
    assert "ungrounded" not in turn.answer.lower()
    assert "not genie" in turn.answer.lower()
    assert "not model serving" in turn.answer.lower()
    assert "genie is live" not in turn.answer.lower()


def test_formula_quotes_catalog_or_refuses_unknown(trained):
    pipeline, _, models = trained
    known = ask("How is coverage_ratio_7d calculated?", con=pipeline.con, model_dir=models)
    assert known.intent == "formula"
    assert known.valid
    formula = pipeline.con.execute(
        "SELECT formula FROM gold.metric_catalog WHERE metric_name = 'coverage_ratio_7d'"
    ).fetchone()[0]
    assert formula in known.answer
    unknown = ask("How is warp_flux_99 calculated?", con=pipeline.con, model_dir=models)
    assert unknown.valid
    assert "will not invent" in unknown.answer.lower()
    assert "warp_flux" not in unknown.answer or "not in gold.metric_catalog" in unknown.answer


def test_in_process_predict_matches_gold_score(trained):
    pipeline, result, models = trained
    eid = result.attrition_scores.sort_values("risk_rank").iloc[0]["employee_id"]
    turn = ask(f"Predict attrition risk for {eid}", con=pipeline.con, model_dir=models)
    assert turn.intent == "employee"
    assert "predict_attrition" in turn.tools_called
    assert turn.valid
    gold_p = float(result.attrition_scores.set_index("employee_id").loc[eid, "p_voluntary_90d"])
    pred = next(r for r in turn.results if r.tool_id == "predict_attrition")
    assert pred.rows
    assert abs(float(pred.rows[0]["p_voluntary_90d"]) - gold_p) < 1e-6
    assert pred.rows[0]["serving"] == "in_process_predict"
    assert pred.rows[0]["model_serving_live"] is False
    assert "ungrounded" not in turn.answer.lower()
    assert f"{gold_p:.3f}" in turn.answer
    assert "in_process_predict" in turn.answer


def test_high_risk_list_is_cited_not_discarded(trained):
    pipeline, result, models = trained
    turn = ask("Who is high risk?", con=pipeline.con, model_dir=models)
    assert turn.intent == "high_risk"
    assert turn.valid
    assert "ungrounded" not in turn.answer.lower()
    top = result.attrition_scores.sort_values("risk_rank").iloc[0]
    assert f"{float(top['p_voluntary_90d']):.3f}" in turn.answer
    assert str(top["display_name"]) in turn.answer


def test_actions_stay_pending_human_review(trained):
    pipeline, _, models = trained
    turn = ask("What actions are recommended?", con=pipeline.con, model_dir=models)
    assert turn.intent == "actions"
    assert turn.valid
    assert "pending_human_review" in turn.answer
    summary = pipeline.con.execute("SELECT applied_count FROM gold.action_summary").fetchone()[0]
    assert int(summary) == 0
    assert "applied 0" in turn.answer.lower() or "applied 0 [" in turn.answer.lower()


def test_whatif_labeled_assumed_not_savings(trained):
    pipeline, _, models = trained
    turn = ask("What if we run the bundle stabilize scenario?", con=pipeline.con, model_dir=models)
    assert turn.intent == "whatif"
    assert turn.valid
    assert "not measured savings" in turn.answer.lower() or "assumed, not measured" in turn.answer.lower()
    assert "bundle_stabilize_ot_recruit" in turn.answer
    lowered = turn.answer.lower()
    assert "we saved" not in lowered
    assert "genie is live" not in lowered


def test_ai_conf_does_not_claim_genie_or_serving():
    ai = load_config("seed").raw["ai"]
    assert ai["mode"] == "template"
    assert ai["genie_live"] is False
    assert ai["model_serving_live"] is False
