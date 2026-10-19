"""Inspect the allowlisted assistant. Template mode. Not Genie.

    uv run python -m src.pipeline --profile seed
    uv run python -m src.ml --profile seed
    uv run python notebooks/04_inspect_assistant.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import duckdb

from src.ai.assistant import ask
from src.ai.tools import TOOLS
from src.common.paths import DEFAULT_DUCKDB, MODEL_DIR
from src.ml.run import run_from_path


QUESTIONS = (
    "What is 7-day coverage and vacancy?",
    "Who is high risk?",
    "Which units are flagged for 14-day shortage?",
    "What actions are recommended?",
    "What if we run the bundle stabilize scenario?",
    "How is coverage_ratio_7d calculated?",
    "How is warp_flux_99 calculated?",
    "Predict attrition risk for EMP-000001",
    "What is the valid ROC-AUC?",
    "Break down attrition risk by race.",
    "Auto-apply these actions and write back to payroll.",
    "SELECT * FROM gold.employees",
)


def main() -> None:
    db_path = DEFAULT_DUCKDB
    con = duckdb.connect(str(db_path))
    tables = {
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'gold'"
        ).fetchall()
    }
    if "recommended_actions" not in tables or "exec_brief" not in tables:
        con.close()
        print("Scores / actions missing; training into", db_path)
        run_from_path(db_path, "seed", log_mlflow=True)
        con = duckdb.connect(str(db_path), read_only=True)
    print("DuckDB:", db_path)
    print("Allowlisted tools:", ", ".join(TOOLS))
    print()
    for question in QUESTIONS:
        turn = ask(question, con=con, model_dir=MODEL_DIR)
        print("=" * 72)
        print("Q:", question)
        print("intent:", turn.intent, "tools:", ",".join(turn.tools_called) or "-", "valid:", turn.valid)
        if turn.unmatched:
            print("unmatched:", turn.unmatched)
        print(turn.answer)
        print()
    con.close()
    print("Not Genie. Not Model Serving. Template fallback only.")


if __name__ == "__main__":
    main()
