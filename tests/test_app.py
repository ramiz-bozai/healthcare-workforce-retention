from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from src.app.api import SAMPLE_QUESTIONS, actions_payload, overview_payload
from src.app.format import (
    ACTION_DISPLAY_COLS,
    ATTRITION_DISPLAY_COLS,
    DISCLAIMER,
    SHORTAGE_DISPLAY_COLS,
    WHATIF_DISPLAY_COLS,
    assert_display_columns_safe,
)
from src.app.load import (
    load_action_summary,
    load_actions,
    load_exec_brief,
    load_risk_scores,
    overview_cards,
)
from src.ml.run import run_models
from src.pipeline.local_run import run_local

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def app_db(tmp_path_factory):
    db = tmp_path_factory.mktemp("app") / "carestaff.duckdb"
    models = tmp_path_factory.mktemp("app-models")
    pipeline = run_local(include_fixtures=False, duckdb_path=db)
    result = run_models(pipeline.con, log_mlflow=False, model_dir=models)
    pipeline.con.close()
    yield db, models, result


def test_display_columns_exclude_protected_attributes():
    assert_display_columns_safe(ATTRITION_DISPLAY_COLS)
    assert_display_columns_safe(SHORTAGE_DISPLAY_COLS)
    assert_display_columns_safe(ACTION_DISPLAY_COLS)
    assert_display_columns_safe(WHATIF_DISPLAY_COLS)
    with pytest.raises(AssertionError):
        assert_display_columns_safe(("employee_age",))


def test_overview_cards_match_exec_brief(app_db):
    db, _, result = app_db
    con = duckdb.connect(str(db), read_only=True)
    brief = load_exec_brief(con).iloc[0]
    cards = {c["column"]: c for c in overview_cards(brief)}
    gold = result.exec_brief.iloc[0]
    assert cards["coverage_ratio_7d"]["cite"] == "gold.exec_brief.coverage_ratio_7d"
    assert cards["coverage_ratio_7d"]["value"].startswith(f"{float(gold['coverage_ratio_7d']):.3f}")
    assert cards["active_headcount"]["value"] == "180"
    assert int(gold["high_risk_headcount"]) == int(float(cards["high_risk_headcount"]["value"].replace(",", "")))
    summary = load_action_summary(con).iloc[0]
    assert int(summary["applied_count"]) == 0
    actions = load_actions(con)
    assert set(actions["status"].unique()) == {"pending_human_review"}
    assert not bool(actions["applied"].astype(bool).any())
    con.close()


def test_disclaimer_does_not_claim_genie_or_serving():
    lowered = DISCLAIMER.lower()
    assert "not model serving" in lowered
    assert "pending_human_review" in lowered
    assert "genie is live" not in lowered


def test_apply_control_is_disabled_in_source():
    ui = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    assert "Apply selected action" in ui
    assert "disabled={!data.apply_enabled}" in ui
    api = (ROOT / "src" / "app" / "api.py").read_text()
    assert '"apply_enabled": False' in api
    assert "read_only=True" in (ROOT / "src" / "app" / "connection.py").read_text()
    assert not (ROOT / "src" / "app" / "workbench.py").exists()


def test_app_overview_and_actions(app_db, monkeypatch):
    db, models, _ = app_db
    monkeypatch.setenv("CARESTAFF_DUCKDB", str(db))
    monkeypatch.setenv("CARESTAFF_MODEL_DIR", str(models))
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID", raising=False)

    from fastapi.testclient import TestClient

    from app import app

    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["apply_enabled"] is False
    assert health.json()["serving"] == "in_process_predict"
    assert health.json()["data_serving"] == "duckdb"

    overview = client.get("/api/overview")
    assert overview.status_code == 200, overview.text
    body = overview.json()
    cards = {c["column"]: c for c in body["cards"]}
    assert cards["active_headcount"]["value"] == "180"
    assert body["genie_live"] is False
    assert body["model_serving_live"] is False
    assert "not model serving" in body["disclaimer"].lower()
    assert body["preview_risk"]
    assert "display_name" in body["preview_risk"][0]

    actions = client.get("/api/actions")
    assert actions.status_code == 200
    payload = actions.json()
    assert payload["apply_enabled"] is False
    assert payload["status"] == "pending_human_review"

    for path in ("/api/attrition", "/api/shortage", "/api/policy"):
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)

    asked = client.post("/api/ask", json={"question": "What is 7-day coverage and vacancy?"})
    assert asked.status_code == 200
    turn = asked.json()
    assert turn["genie_live"] is False
    assert turn["model_serving_live"] is False
    assert turn["valid"] is True

    refused = client.post("/api/ask", json={"question": "Break down attrition risk by race."})
    assert refused.status_code == 200
    assert refused.json()["intent"] == "refuse_protected"

    monkeypatch.setenv("GENIE_SPACE_ID", "space-should-not-be-called")
    def boom(*_a, **_k):
        raise AssertionError("protected questions must not call Genie")
    monkeypatch.setattr("src.app.api.ask_genie", boom)
    still = client.post("/api/ask", json={"question": "Break down attrition risk by race."})
    assert still.json()["intent"] == "refuse_protected"

    con = duckdb.connect(str(db), read_only=True)
    applied = con.execute("SELECT applied_count FROM gold.action_summary").fetchone()[0]
    payload_direct = actions_payload(con)
    overview_direct = overview_payload(con)
    con.close()
    assert int(applied) == 0
    assert payload_direct["apply_enabled"] is False
    assert overview_direct["summary"]["applied_count"] == 0
    assert "Break down attrition risk by race." in SAMPLE_QUESTIONS


def test_risk_scores_omit_oracle_label_by_default(app_db):
    db, _, _ = app_db
    con = duckdb.connect(str(db), read_only=True)
    scores = load_risk_scores(con)
    assert "label_voluntary_90d" not in scores.columns
    assert "salary" not in scores.columns
    n_high = int(scores["high_risk_flag"].astype(bool).sum())
    assert 20 <= n_high <= 40
    con.close()
