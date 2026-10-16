"""Read gold tables for the workbench. No derived KPIs. No writes."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pandas as pd

from src.app.format import cite_value, driver_names
from src.common.paths import DEFAULT_DUCKDB, MODEL_DIR

REQUIRED_APP_GOLD = (
    "exec_brief",
    "executive_kpis",
    "employee_risk_scores",
    "unit_shortage_forecast",
    "recommended_actions",
    "whatif_scenarios",
    "action_summary",
    "metric_catalog",
    "model_metrics",
    "model_fairness_slices",
)

OVERVIEW_FIELDS = (
    ("Active headcount", "active_headcount"),
    ("7-day coverage", "coverage_ratio_7d"),
    ("Vacancy rate", "vacancy_rate"),
    ("Open FTE", "open_fte"),
    ("Observed 90d voluntary exits", "observed_voluntary_exits_90d"),
    ("Observed 90d attrition rate", "observed_attrition_rate_90d"),
    ("High-risk headcount", "high_risk_headcount"),
    ("Mean predicted p(leave 90d)", "predicted_attrition_rate_90d"),
    ("Planning attrition exposure", "planning_attrition_exposure_usd"),
    ("Flagged shortage units (14d)", "predicted_shortage_units_14d"),
    ("Planning coverage exposure", "planning_coverage_exposure_usd"),
    ("Overtime hours (30d)", "overtime_hours_30d"),
)


def duckdb_path() -> Path:
    return Path(os.environ.get("CARESTTAFF_DUCKDB", DEFAULT_DUCKDB))


def model_dir() -> Path:
    return Path(os.environ.get("CARESTTAFF_MODEL_DIR", MODEL_DIR))


def connect(path: Path | None = None):
    db = path or duckdb_path()
    if not db.exists():
        raise FileNotFoundError(
            f"{db} missing. Run `uv run python -m src.pipeline` then `uv run python -m src.ml`."
        )
    return duckdb.connect(str(db), read_only=True)


def gold_tables(con) -> set[str]:
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'gold'"
    ).fetchall()
    return {r[0] for r in rows}


def require_gold(con) -> None:
    missing = [name for name in REQUIRED_APP_GOLD if name not in gold_tables(con)]
    if missing:
        raise FileNotFoundError(
            f"Gold tables missing {missing}. Run `uv run python -m src.pipeline` then `uv run python -m src.ml`."
        )


def load_exec_brief(con) -> pd.DataFrame:
    return con.execute("SELECT * FROM gold.exec_brief").fetchdf()


def load_action_summary(con) -> pd.DataFrame:
    return con.execute("SELECT * FROM gold.action_summary").fetchdf()


def load_metric_catalog(con) -> pd.DataFrame:
    return con.execute(
        "SELECT metric_name, table_name, grain, formula, includes_model FROM gold.metric_catalog ORDER BY metric_name"
    ).fetchdf()


def load_risk_scores(con) -> pd.DataFrame:
    frame = con.execute(
        """
        SELECT employee_id, display_name, role_code, department_id, facility_id,
               p_voluntary_90d, high_risk_flag, risk_rank,
               driver_1, driver_2, driver_3, planning_replacement_usd
        FROM gold.employee_risk_scores
        ORDER BY risk_rank
        """
    ).fetchdf()
    frame = frame.copy()
    frame["drivers"] = [
        driver_names(a, b, c) for a, b, c in zip(frame["driver_1"], frame["driver_2"], frame["driver_3"])
    ]
    return frame


def load_oracle_labels(con) -> pd.DataFrame:
    return con.execute(
        "SELECT employee_id, label_voluntary_90d FROM gold.employee_risk_scores ORDER BY risk_rank"
    ).fetchdf()


def load_shortage(con) -> pd.DataFrame:
    frame = con.execute(
        """
        SELECT department_id, week_start, week_end,
               avg_coverage_ratio, avg_open_shift_share,
               p_shortage_14d, predicted_shortage_flag, shortage_rank,
               driver_1, driver_2, driver_3,
               trailing_gap_hours_14d, planning_coverage_exposure_usd
        FROM gold.unit_shortage_forecast
        ORDER BY shortage_rank
        """
    ).fetchdf()
    frame = frame.copy()
    frame["drivers"] = [
        driver_names(a, b, c) for a, b, c in zip(frame["driver_1"], frame["driver_2"], frame["driver_3"])
    ]
    return frame


def load_actions(con) -> pd.DataFrame:
    return con.execute(
        """
        SELECT action_id, subject_type, subject_id, display_name, department_id,
               playbook_action, baseline_p, scenario_p, planning_delta_usd,
               scored, status, requires_human_review, applied
        FROM gold.recommended_actions
        ORDER BY baseline_p DESC
        """
    ).fetchdf()


def load_whatif(con) -> pd.DataFrame:
    return con.execute(
        """
        SELECT scenario_id, playbook_action, scope, n_employees, n_units, scored,
               mean_p_attrition, high_risk_headcount, planning_attrition_exposure_usd,
               planning_attrition_delta_usd, mean_p_shortage, flagged_units,
               planning_coverage_exposure_usd, planning_coverage_delta_usd
        FROM gold.whatif_scenarios
        ORDER BY CASE scenario_id WHEN 'baseline' THEN 0 ELSE 1 END, scenario_id
        """
    ).fetchdf()


def load_valid_metrics(con) -> pd.DataFrame:
    return con.execute(
        """
        SELECT model, split, metric, value
        FROM gold.model_metrics
        WHERE split IN ('valid', 'valid_persistence_baseline')
          AND metric IN ('roc_auc', 'avg_precision', 'brier', 'ece', 'base_rate',
                         'n', 'n_pos', 'high_risk_recall', 'flagged_units')
        ORDER BY model, split, metric
        """
    ).fetchdf()


def load_fairness_review(con) -> pd.DataFrame:
    return con.execute(
        """
        SELECT model, slice_column, slice_value, n, base_rate, selection_rate, review_flag
        FROM gold.model_fairness_slices
        WHERE review_flag
        ORDER BY model, slice_column, slice_value
        """
    ).fetchdf()


def overview_cards(brief_row: pd.Series | dict) -> list[dict[str, str]]:
    row = dict(brief_row)
    cards = []
    for label, column in OVERVIEW_FIELDS:
        cards.append(
            {
                "label": label,
                "column": column,
                "value": cite_value("exec_brief", column, row.get(column)),
                "cite": f"gold.exec_brief.{column}",
            }
        )
    return cards
