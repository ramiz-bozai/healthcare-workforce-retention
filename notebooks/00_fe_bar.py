"""Print FE Bar talk-track numbers from gold. Quote only what this prints.

    uv run python notebooks/00_fe_bar.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_generation.config import load_config
from src.ai.assistant import ask
from src.app.load import (
    connect,
    load_action_summary,
    load_exec_brief,
    load_risk_scores,
    load_whatif,
    overview_cards,
    require_gold,
)
from src.common.paths import MODEL_DIR
from src.ml.run import run_from_path


def main() -> None:
    cfg = load_config("seed")
    ai = cfg.raw["ai"]
    try:
        con = connect()
        require_gold(con)
    except FileNotFoundError:
        print("Gold missing; running pipeline + models into default DuckDB")
        run_from_path(profile="seed", log_mlflow=False)
        con = connect()
        require_gold(con)

    print("CareStaff Insight — FE Bar numbers (cite these, do not round in your head)")
    print(f"as_of {cfg.as_of_date.isoformat()}  seed {cfg.random_seed}")
    print(f"genie_live={ai['genie_live']}  model_serving_live={ai['model_serving_live']}  mode={ai['mode']}")
    print()
    brief = load_exec_brief(con).iloc[0]
    for card in overview_cards(brief):
        print(f"{card['label']:36} {card['value']:>16}  {card['cite']}")
    summary = load_action_summary(con).iloc[0]
    print()
    print(
        "actions",
        int(summary["recommended_action_count"]),
        "pending",
        int(summary["pending_human_review_count"]),
        "applied",
        int(summary["applied_count"]),
        summary["uniform_status"],
    )
    scores = load_risk_scores(con)
    top = scores.iloc[0]
    print(
        f"rank1 {top['display_name']} {top['role_code']} {top['department_id']} "
        f"p={float(top['p_voluntary_90d']):.3f} drivers={top['drivers']}"
    )
    whatif = load_whatif(con).set_index("scenario_id")
    if "bundle_stabilize_ot_recruit" in whatif.index:
        b = whatif.loc["bundle_stabilize_ot_recruit"]
        base = whatif.loc["baseline"]
        print(
            "bundle high-risk",
            int(base["high_risk_headcount"]),
            "->",
            int(b["high_risk_headcount"]),
            "attrition_delta_usd",
            round(float(b["planning_attrition_delta_usd"])),
            "(assumed, not savings)",
        )
    print()
    print("Refuse checks (no tools on protected / apply):")
    for q in ("Break down attrition risk by race.", "Auto-apply these actions and write back to payroll."):
        turn = ask(q, con=con, model_dir=MODEL_DIR)
        print(f"  {turn.intent:20} {q}")
    con.close()
    print()
    print("Talk track: docs/fe_bar.md")
    print("Workspace (you click Start): docs/workspace.md")
    print("Not Genie. Not Model Serving. Apply stays disabled.")


if __name__ == "__main__":
    main()
