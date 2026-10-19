from __future__ import annotations

from src.app.genie import is_live, space_id


def test_genie_is_not_live_without_env(monkeypatch):
    for key in ("GENIE_SPACE_ID", "DATABRICKS_GENIE_SPACE_ID", "CARESTAFF_GENIE_SPACE_ID"):
        monkeypatch.delenv(key, raising=False)
    assert space_id() is None
    assert is_live() is False


def test_genie_space_id_from_env(monkeypatch):
    monkeypatch.delenv("DATABRICKS_GENIE_SPACE_ID", raising=False)
    monkeypatch.delenv("CARESTAFF_GENIE_SPACE_ID", raising=False)
    monkeypatch.setenv("GENIE_SPACE_ID", "01abc")
    assert space_id() == "01abc"
    assert is_live() is True
