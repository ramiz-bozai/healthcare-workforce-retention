from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

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
    assert "not genie" in lowered
    assert "not model serving" in lowered
    assert "pending_human_review" in lowered


def test_apply_control_is_disabled_in_source():
    text = (ROOT / "src" / "app" / "workbench.py").read_text()
    assert "Apply selected action" in text
    assert "disabled=True" in text
    assert "read_only=True" in (ROOT / "src" / "app" / "load.py").read_text()


def test_app_overview_and_actions(app_db, monkeypatch):
    from streamlit.testing.v1 import AppTest

    db, models, _ = app_db
    monkeypatch.setenv("CARESTTAFF_DUCKDB", str(db))
    monkeypatch.setenv("CARESTTAFF_MODEL_DIR", str(models))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45)
    at.run()
    assert not at.exception, at.exception
    labels = [m.label for m in at.metric]
    values = [str(m.value) for m in at.metric]
    assert "Active headcount" in labels
    assert "180" in values
    captions = " ".join(str(c.value) for c in at.caption).lower()
    assert "not genie" in captions
    assert "not model serving" in captions

    at.sidebar.radio[0].set_value("Actions & what-if").run()
    assert not at.exception, at.exception
    assert at.button
    assert bool(at.button[0].disabled)
    for page in ("Attrition risk", "Unit shortage", "Ask", "Policy"):
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, (page, at.exception)
    con = duckdb.connect(str(db), read_only=True)
    applied = con.execute("SELECT applied_count FROM gold.action_summary").fetchone()[0]
    con.close()
    assert int(applied) == 0


def test_risk_scores_omit_oracle_label_by_default(app_db):
    db, _, _ = app_db
    con = duckdb.connect(str(db), read_only=True)
    scores = load_risk_scores(con)
    assert "label_voluntary_90d" not in scores.columns
    assert "salary" not in scores.columns
    n_high = int(scores["high_risk_flag"].astype(bool).sum())
    assert 20 <= n_high <= 40
    con.close()
