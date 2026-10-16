from __future__ import annotations

from pathlib import Path

from data_generation.config import load_config

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs" / "fe_bar.md"


def test_fe_bar_pack_forbids_live_claims():
    text = PACK.read_text().lower().replace("*", "")
    assert "genie is not live" in text
    assert "not model serving" in text
    assert "pending_human_review" in text
    assert "does not deploy" in text
    assert "not savings" in text
    assert "planning list" in text
    assert "solution builder" in text
    assert "phi" in text
    for banned in (
        "genie is live",
        "model serving is live",
        "pipeline is live",
        "databricks app is live",
    ):
        assert banned not in text


def test_fe_bar_pack_points_at_inspect_surfaces():
    text = PACK.read_text()
    for needle in (
        "conf/default.yaml",
        "gold.exec_brief",
        "gold.executive_kpis",
        "gold.metric_catalog",
        "Ellis M.",
        "docs/workspace.md",
        "notebooks/00_fe_bar.py",
    ):
        assert needle in text, needle


def test_conf_still_does_not_claim_genie_or_serving():
    ai = load_config("seed").raw["ai"]
    assert ai["genie_live"] is False
    assert ai["model_serving_live"] is False
    assert ai["mode"] == "template"
