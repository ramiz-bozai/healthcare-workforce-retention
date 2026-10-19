"""Inspect trained models. Runnable locally; paste into a Databricks notebook later.

    uv run python -m src.ml --profile seed
    uv run python notebooks/02_inspect_models.py
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
    if "employee_risk_scores" not in tables:
        con.close()
        print("Scores missing; training models into", db_path)
        run_from_path(db_path, "seed", log_mlflow=True)
        con = duckdb.connect(str(db_path), read_only=True)
    print("DuckDB:", db_path)
    print()
    print("=== Exec brief (operational KPIs + planning scores) ===")
    print(con.execute("SELECT * FROM gold.exec_brief").fetchdf().T.to_string())
    print()
    print("=== Model metrics (valid = production-honest; inference_demo_oracle uses generator future labels) ===")
    print(
        con.execute(
            """
            SELECT model, split, metric, ROUND(value, 4) AS value
            FROM gold.model_metrics
            WHERE metric IN ('roc_auc', 'avg_precision', 'brier', 'ece', 'base_rate', 'n', 'n_pos',
                             'high_risk_recall', 'leaver_mean_p', 'stayer_mean_p', 'flagged_units')
            ORDER BY model, split, metric
            """
        ).fetchdf().to_string(index=False)
    )
    print()
    print("=== Top attrition importances (permutation on valid, neg Brier) ===")
    print(
        con.execute(
            """
            SELECT feature, ROUND(importance_mean, 5) AS importance_mean
            FROM gold.model_feature_importances
            WHERE model = 'attrition'
            ORDER BY importance_mean DESC
            LIMIT 8
            """
        ).fetchdf().to_string(index=False)
    )
    print()
    print("=== Top shortage importances ===")
    print(
        con.execute(
            """
            SELECT feature, ROUND(importance_mean, 5) AS importance_mean
            FROM gold.model_feature_importances
            WHERE model = 'shortage'
            ORDER BY importance_mean DESC
            LIMIT 8
            """
        ).fetchdf().to_string(index=False)
    )
    print()
    print("=== High-risk planning list (top quantile; not an employment decision) ===")
    print(
        con.execute(
            """
            SELECT risk_rank, display_name, role_code, department_id,
                   ROUND(p_voluntary_90d, 3) AS p_voluntary_90d,
                   driver_1, label_voluntary_90d
            FROM gold.employee_risk_scores
            WHERE high_risk_flag
            ORDER BY risk_rank
            LIMIT 15
            """
        ).fetchdf().to_string(index=False)
    )
    print()
    print("=== Unit 14-day shortage forecast (latest week per unit) ===")
    print(
        con.execute(
            """
            SELECT department_id, week_end,
                   ROUND(p_shortage_14d, 3) AS p_shortage_14d,
                   predicted_shortage_flag, is_shortage_week,
                   driver_1
            FROM gold.unit_shortage_forecast
            ORDER BY shortage_rank
            """
        ).fetchdf().to_string(index=False)
    )
    print()
    print("=== Operational fairness slices with review_flag (not protected classes) ===")
    print(
        con.execute(
            """
            SELECT model, slice_column, slice_value, n,
                   ROUND(base_rate, 3) AS base_rate,
                   ROUND(selection_rate, 3) AS selection_rate,
                   review_flag
            FROM gold.model_fairness_slices
            WHERE review_flag
            ORDER BY model, slice_column, slice_value
            """
        ).fetchdf().to_string(index=False)
    )
    con.close()
    print()
    print("Do not claim Model Serving is live. Actions stay pending_human_review.")


if __name__ == "__main__":
    main()
