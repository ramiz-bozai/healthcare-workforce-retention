"""Train and score CareStaff Insight models.

    uv run python -m src.ml --profile seed
"""

from __future__ import annotations

import argparse

from src.common.paths import DEFAULT_DUCKDB
from src.ml.run import run_from_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Train attrition + shortage models and score as_of.")
    parser.add_argument("--profile", choices=("seed", "demo"), default="seed")
    parser.add_argument("--duckdb", default=DEFAULT_DUCKDB)
    parser.add_argument("--skip-mlflow", action="store_true")
    args = parser.parse_args()
    result = run_from_path(args.duckdb, args.profile, log_mlflow=not args.skip_mlflow)
    brief = result.exec_brief.iloc[0]
    print("MLflow run:", result.mlflow_run_id or "(skipped)")
    print("Attrition valid ROC-AUC:", result.attrition.metrics["valid"].get("roc_auc"))
    print("Attrition valid Brier:", result.attrition.metrics["valid"].get("brier"))
    print("Shortage valid ROC-AUC:", result.shortage.metrics["valid"].get("roc_auc"))
    print("Shortage valid Brier:", result.shortage.metrics["valid"].get("brier"))
    print("High-risk headcount:", int(brief["high_risk_headcount"]))
    print("Predicted attrition rate (mean p):", round(float(brief["predicted_attrition_rate_90d"]), 4))
    print("Flagged shortage units:", int(brief["predicted_shortage_units_14d"]))
    print("Planning attrition exposure USD:", round(float(brief["planning_attrition_exposure_usd"]), 0))
    print("Planning coverage exposure USD:", round(float(brief["planning_coverage_exposure_usd"]), 0))
    print("Recommended actions:", len(result.recommended_actions), "all pending_human_review")
    bundle = result.whatif_scenarios.loc[
        result.whatif_scenarios["scenario_id"] == "bundle_stabilize_ot_recruit"
    ].iloc[0]
    print(
        "Bundle planning attrition delta USD:",
        round(float(bundle["planning_attrition_delta_usd"]), 0),
        "(assumed, not applied)",
    )
    print("In-process predict only. Not Model Serving. Not an employment decision.")


if __name__ == "__main__":
    main()
