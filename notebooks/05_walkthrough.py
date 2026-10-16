"""Walkthrough of the Streamlit workbench data. Local; paste into a Databricks notebook later.

    uv run python -m src.pipeline --profile seed
    uv run python -m src.ml --profile seed
    uv run python notebooks/05_walkthrough.py
    uv run streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app.load import (
    connect,
    load_action_summary,
    load_exec_brief,
    load_risk_scores,
    load_shortage,
    load_whatif,
    overview_cards,
    require_gold,
)
from src.common.paths import DEFAULT_DUCKDB
from src.ml.run import run_from_path


def main() -> None:
    db_path = DEFAULT_DUCKDB
    try:
        con = connect(db_path)
        require_gold(con)
    except FileNotFoundError:
        print("Gold missing; training into", db_path)
        run_from_path(db_path, "seed", log_mlflow=True)
        con = connect(db_path)
        require_gold(con)
    print("DuckDB:", db_path)
    print()
    print("=== Overview cards (same values the app shows from gold.exec_brief) ===")
    brief = load_exec_brief(con).iloc[0]
    for card in overview_cards(brief):
        print(f"{card['label']:36} {card['value']:>16}  {card['cite']}")
    print()
    summary = load_action_summary(con).iloc[0]
    print("=== Action summary ===")
    print("recommended", int(summary["recommended_action_count"]))
    print("pending_human_review", int(summary["pending_human_review_count"]))
    print("applied", int(summary["applied_count"]))
    print("status", summary["uniform_status"])
    print()
    scores = load_risk_scores(con)
    high = scores.loc[scores["high_risk_flag"].astype(bool)]
    print("=== High-risk (top of gold.employee_risk_scores) ===")
    print(
        high[["risk_rank", "display_name", "role_code", "department_id", "p_voluntary_90d", "drivers"]]
        .head(8)
        .to_string(index=False)
    )
    print()
    print("=== Unit shortage ===")
    print(
        load_shortage(con)[
            ["shortage_rank", "department_id", "p_shortage_14d", "predicted_shortage_flag"]
        ].to_string(index=False)
    )
    print()
    print("=== What-if high-risk headcount ===")
    print(load_whatif(con)[["scenario_id", "high_risk_headcount", "planning_attrition_delta_usd"]].to_string(index=False))
    con.close()
    print()
    print("Open the workbench:")
    print("  uv run streamlit run app.py")
    print("Pages: Overview, Attrition risk, Unit shortage, Actions & what-if, Ask, Policy.")
    print("Apply is disabled. Not Genie. Not Model Serving.")


if __name__ == "__main__":
    main()
