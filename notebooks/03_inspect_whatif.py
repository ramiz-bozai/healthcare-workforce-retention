"""Inspect what-if scenarios and pending actions.

    uv run python -m src.ml --profile seed
    uv run python notebooks/03_inspect_whatif.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import duckdb

from src.common.paths import DEFAULT_DUCKDB
from src.ml.run import run_from_path


def main() -> None:
    db_path = DEFAULT_DUCKDB
    con = duckdb.connect(str(db_path))
    tables = {
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'gold'"
        ).fetchall()
    }
    if "recommended_actions" not in tables:
        con.close()
        print("Actions missing; training + what-if into", db_path)
        run_from_path(db_path, "seed", log_mlflow=True)
        con = duckdb.connect(str(db_path), read_only=True)
    print("DuckDB:", db_path)
    print()
    print("=== Action summary (nothing is applied) ===")
    print(con.execute("SELECT * FROM gold.action_summary").fetchdf().T.to_string())
    print()
    print("=== Recommended actions by playbook ===")
    print(
        con.execute(
            """
            SELECT playbook_action, COUNT(*) AS n,
                   SUM(CAST(scored AS INTEGER)) AS scored_n,
                   SUM(CAST(requires_human_review AS INTEGER)) AS pending_n
            FROM gold.recommended_actions
            GROUP BY 1
            ORDER BY 1
            """
        ).fetchdf().to_string(index=False)
    )
    print()
    print("=== What-if scenarios (planning estimates, not savings) ===")
    print(
        con.execute(
            """
            SELECT scenario_id, playbook_action, n_employees, n_units,
                   ROUND(mean_p_attrition, 4) AS mean_p_attrition,
                   high_risk_headcount,
                   ROUND(planning_attrition_delta_usd, 0) AS attrition_delta_usd,
                   flagged_units,
                   ROUND(planning_coverage_delta_usd, 0) AS coverage_delta_usd
            FROM gold.whatif_scenarios
            ORDER BY CASE scenario_id WHEN 'baseline' THEN 0 ELSE 1 END, scenario_id
            """
        ).fetchdf().to_string(index=False)
    )
    print()
    print("=== Example employee actions (top p) ===")
    print(
        con.execute(
            """
            SELECT action_id, display_name, playbook_action,
                   ROUND(baseline_p, 3) AS baseline_p,
                   ROUND(scenario_p, 3) AS scenario_p,
                   status, applied
            FROM gold.recommended_actions
            WHERE subject_type = 'employee'
            ORDER BY baseline_p DESC
            LIMIT 12
            """
        ).fetchdf().to_string(index=False)
    )
    print()
    print("=== Unit actions ===")
    print(
        con.execute(
            """
            SELECT action_id, department_id, playbook_action,
                   ROUND(baseline_p, 3) AS baseline_p,
                   ROUND(scenario_p, 3) AS scenario_p,
                   status
            FROM gold.recommended_actions
            WHERE subject_type = 'department'
            ORDER BY department_id, playbook_action
            """
        ).fetchdf().to_string(index=False)
    )
    con.close()
    print()
    print("Do not apply these. Status is pending_human_review. Not Model Serving.")


if __name__ == "__main__":
    main()
