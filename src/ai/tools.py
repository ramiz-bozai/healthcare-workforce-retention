"""Allowlisted gold tools. Same catalog a workspace Genie space would expose.

This module is not Genie and is not Model Serving. It runs in-process against
DuckDB (or any connection with the same gold table names). No free-form SQL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from data_generation.config import GenerationConfig, load_config
from src.common.paths import MODEL_DIR
from src.ml.predict import load_local_models

EMPLOYEE_ID_RE = re.compile(r"^EMP-\d{6}$")
DEPARTMENT_ID_RE = re.compile(r"^[A-Z]{2,5}-[A-Z0-9-]{1,24}$")
METRIC_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,80}$")
SCENARIO_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,80}$")
PLAYBOOK = (
    "schedule_stabilize",
    "manager_outreach",
    "workload_balance",
    "recruit_prioritize",
    "float_ot_review",
)

MAX_ROWS = 12


class UnknownToolError(ValueError):
    pass


class InvalidToolParamError(ValueError):
    pass


@dataclass
class ToolResult:
    tool_id: str
    tables: tuple[str, ...]
    rows: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(value).date().isoformat()
    if isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int,)) and not isinstance(value, bool):
        return int(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        value = value.item()
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value
    if isinstance(value, float):
        return float(value)
    return value


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for raw in frame.to_dict(orient="records"):
        out.append({str(k): jsonable(v) for k, v in raw.items()})
    return out


def _limit(params: dict[str, Any], default: int = 8) -> int:
    raw = params.get("limit", default)
    try:
        n = int(raw)
    except (TypeError, ValueError) as exc:
        raise InvalidToolParamError("limit must be an integer") from exc
    return max(1, min(n, MAX_ROWS))


def _require(params: dict[str, Any], key: str, pattern: re.Pattern[str]) -> str:
    value = str(params.get(key, "")).strip()
    if not pattern.match(value):
        raise InvalidToolParamError(f"invalid {key}")
    return value


def policy_row(cfg: GenerationConfig) -> dict[str, Any]:
    raw = cfg.raw
    labels = raw["labels"]
    models = raw["models"]
    actions = raw["actions"]
    ai = raw.get("ai", {})
    q = float(models["attrition_high_risk_quantile"])
    return {
        "as_of_date": cfg.as_of_date.isoformat(),
        "random_seed": int(cfg.random_seed),
        "attrition_horizon_days": int(labels["attrition_horizon_days"]),
        "shortage_primary_horizon_days": int(labels["shortage_primary_horizon_days"]),
        "shortage_secondary_horizon_days": int(labels["shortage_secondary_horizon_days"]),
        "coverage_lookback_days": 7,
        "overtime_lookback_days": 30,
        "overtime_window_start_offset_days": 29,
        "shortage_coverage_ratio_threshold": float(labels["shortage_coverage_ratio_threshold"]),
        "shortage_open_shift_share_threshold": float(labels["shortage_open_shift_share_threshold"]),
        "attrition_high_risk_quantile": q,
        "high_risk_percentile": int(round((1.0 - q) * 100)),
        "shortage_flag_min_probability": float(models["shortage_flag_min_probability"]),
        "require_human_review": bool(actions["require_human_review"]),
        "playbook": ",".join(actions["playbook"]),
        "replacement_multiplier": float(cfg.cost.replacement_multiplier),
        "agency_to_staff_hourly_ratio": float(cfg.cost.agency_to_staff_hourly_ratio),
        "hours_per_year": int(cfg.cost.hours_per_year),
        "mode": str(ai.get("mode", "template")),
        "genie_live": bool(ai.get("genie_live", False)),
        "model_serving_live": bool(ai.get("model_serving_live", False)),
        "serving": "in_process_predict",
        "source": "conf/default.yaml",
    }


def tool_policy(_con, params: dict[str, Any], cfg: GenerationConfig, _model_dir: Path | None) -> ToolResult:
    return ToolResult("policy", ("conf/default.yaml",), [policy_row(cfg)])


def tool_exec_brief(con, params: dict[str, Any], cfg: GenerationConfig, _model_dir: Path | None) -> ToolResult:
    df = con.execute("SELECT * FROM gold.exec_brief").fetchdf()
    return ToolResult("exec_brief", ("gold.exec_brief",), records(df))


def tool_executive_kpis(con, params: dict[str, Any], cfg: GenerationConfig, _model_dir: Path | None) -> ToolResult:
    df = con.execute("SELECT * FROM gold.executive_kpis").fetchdf()
    return ToolResult("executive_kpis", ("gold.executive_kpis",), records(df))


def tool_metric_formula(con, params: dict[str, Any], cfg: GenerationConfig, _model_dir: Path | None) -> ToolResult:
    name = _require(params, "metric_name", METRIC_NAME_RE)
    df = con.execute(
        """
        SELECT metric_name, table_name, grain, formula, includes_model
        FROM gold.metric_catalog
        WHERE metric_name = ?
        """,
        [name],
    ).fetchdf()
    return ToolResult("metric_formula", ("gold.metric_catalog",), records(df))


def tool_metric_catalog(con, params: dict[str, Any], cfg: GenerationConfig, _model_dir: Path | None) -> ToolResult:
    df = con.execute(
        """
        SELECT metric_name, table_name, grain, formula
        FROM gold.metric_catalog
        ORDER BY metric_name
        """
    ).fetchdf()
    return ToolResult("metric_catalog", ("gold.metric_catalog",), records(df))


def tool_high_risk_list(con, params: dict[str, Any], cfg: GenerationConfig, _model_dir: Path | None) -> ToolResult:
    limit = _limit(params, 8)
    df = con.execute(
        f"""
        SELECT employee_id, display_name, role_code, department_id, facility_id,
               p_voluntary_90d, high_risk_flag, risk_rank,
               driver_1, driver_2, driver_3, planning_replacement_usd
        FROM gold.employee_risk_scores
        WHERE high_risk_flag
        ORDER BY risk_rank
        LIMIT {limit}
        """
    ).fetchdf()
    return ToolResult("high_risk_list", ("gold.employee_risk_scores",), records(df))


def tool_employee_score(con, params: dict[str, Any], cfg: GenerationConfig, _model_dir: Path | None) -> ToolResult:
    eid = _require(params, "employee_id", EMPLOYEE_ID_RE)
    df = con.execute(
        """
        SELECT employee_id, display_name, role_code, department_id, facility_id,
               p_voluntary_90d, high_risk_flag, risk_rank,
               driver_1, driver_2, driver_3, planning_replacement_usd
        FROM gold.employee_risk_scores
        WHERE employee_id = ?
        """,
        [eid],
    ).fetchdf()
    return ToolResult("employee_score", ("gold.employee_risk_scores",), records(df))


def tool_unit_shortage(con, params: dict[str, Any], cfg: GenerationConfig, _model_dir: Path | None) -> ToolResult:
    df = con.execute(
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
    return ToolResult("unit_shortage", ("gold.unit_shortage_forecast",), records(df))


def tool_recommended_actions(con, params: dict[str, Any], cfg: GenerationConfig, _model_dir: Path | None) -> ToolResult:
    limit = _limit(params, 8)
    playbook = params.get("playbook_action")
    if playbook:
        if playbook not in PLAYBOOK:
            raise InvalidToolParamError("invalid playbook_action")
        df = con.execute(
            f"""
            SELECT action_id, subject_type, subject_id, display_name, department_id,
                   playbook_action, baseline_p, scenario_p, planning_delta_usd,
                   scored, status, requires_human_review, applied
            FROM gold.recommended_actions
            WHERE playbook_action = ?
            ORDER BY baseline_p DESC
            LIMIT {limit}
            """,
            [playbook],
        ).fetchdf()
    else:
        df = con.execute(
            f"""
            SELECT action_id, subject_type, subject_id, display_name, department_id,
                   playbook_action, baseline_p, scenario_p, planning_delta_usd,
                   scored, status, requires_human_review, applied
            FROM gold.recommended_actions
            ORDER BY baseline_p DESC
            LIMIT {limit}
            """
        ).fetchdf()
    return ToolResult("recommended_actions", ("gold.recommended_actions",), records(df))


def tool_action_summary(con, params: dict[str, Any], cfg: GenerationConfig, _model_dir: Path | None) -> ToolResult:
    df = con.execute("SELECT * FROM gold.action_summary").fetchdf()
    return ToolResult("action_summary", ("gold.action_summary",), records(df))


def tool_whatif_scenarios(con, params: dict[str, Any], cfg: GenerationConfig, _model_dir: Path | None) -> ToolResult:
    df = con.execute(
        """
        SELECT scenario_id, playbook_action, scope, n_employees, n_units, scored,
               mean_p_attrition, high_risk_headcount, planning_attrition_exposure_usd,
               planning_attrition_delta_usd, mean_p_shortage, flagged_units,
               planning_coverage_exposure_usd, planning_coverage_delta_usd
        FROM gold.whatif_scenarios
        ORDER BY CASE scenario_id WHEN 'baseline' THEN 0 ELSE 1 END, scenario_id
        """
    ).fetchdf()
    return ToolResult("whatif_scenarios", ("gold.whatif_scenarios",), records(df))


def tool_whatif_scenario(con, params: dict[str, Any], cfg: GenerationConfig, _model_dir: Path | None) -> ToolResult:
    sid = _require(params, "scenario_id", SCENARIO_ID_RE)
    df = con.execute(
        """
        SELECT scenario_id, playbook_action, scope, n_employees, n_units, scored,
               mean_p_attrition, high_risk_headcount, planning_attrition_exposure_usd,
               planning_attrition_delta_usd, mean_p_shortage, flagged_units,
               planning_coverage_exposure_usd, planning_coverage_delta_usd
        FROM gold.whatif_scenarios
        WHERE scenario_id = ?
        """,
        [sid],
    ).fetchdf()
    return ToolResult("whatif_scenario", ("gold.whatif_scenarios",), records(df))


def tool_model_metrics_valid(con, params: dict[str, Any], cfg: GenerationConfig, _model_dir: Path | None) -> ToolResult:
    df = con.execute(
        """
        SELECT model, split, metric, value
        FROM gold.model_metrics
        WHERE split IN ('valid', 'valid_persistence_baseline')
          AND metric IN ('roc_auc', 'avg_precision', 'brier', 'ece', 'base_rate',
                         'n', 'n_pos', 'high_risk_recall', 'flagged_units')
        ORDER BY model, split, metric
        """
    ).fetchdf()
    return ToolResult("model_metrics_valid", ("gold.model_metrics",), records(df))


def tool_fairness_review(con, params: dict[str, Any], cfg: GenerationConfig, _model_dir: Path | None) -> ToolResult:
    df = con.execute(
        """
        SELECT model, slice_column, slice_value, n, base_rate, selection_rate, review_flag
        FROM gold.model_fairness_slices
        WHERE review_flag
        ORDER BY model, slice_column, slice_value
        """
    ).fetchdf()
    return ToolResult("fairness_review", ("gold.model_fairness_slices",), records(df))


def tool_predict_attrition(con, params: dict[str, Any], cfg: GenerationConfig, model_dir: Path | None) -> ToolResult:
    eid = _require(params, "employee_id", EMPLOYEE_ID_RE)
    frame = con.execute(
        """
        SELECT *
        FROM gold.employee_month_features
        WHERE employee_id = ? AND is_inference_snapshot
        """,
        [eid],
    ).fetchdf()
    if frame.empty:
        return ToolResult("predict_attrition", ("gold.employee_month_features", "in_process_predict"), [])
    try:
        models = load_local_models(model_dir or MODEL_DIR)
    except FileNotFoundError as exc:
        return ToolResult(
            "predict_attrition",
            ("gold.employee_month_features", "in_process_predict"),
            [],
            error=str(exc),
        )
    p = float(models.predict_attrition(frame)[0])
    names = con.execute(
        "SELECT display_name, role_code, department_id FROM gold.employee_risk_scores WHERE employee_id = ?",
        [eid],
    ).fetchdf()
    row = {
        "employee_id": eid,
        "display_name": names.iloc[0]["display_name"] if len(names) else None,
        "role_code": names.iloc[0]["role_code"] if len(names) else frame.iloc[0].get("role_code"),
        "department_id": names.iloc[0]["department_id"] if len(names) else frame.iloc[0].get("department_id"),
        "p_voluntary_90d": p,
        "serving": "in_process_predict",
        "model_serving_live": False,
        "genie_live": False,
    }
    return ToolResult(
        "predict_attrition",
        ("gold.employee_month_features", "in_process_predict"),
        [row],
    )


def tool_predict_shortage(con, params: dict[str, Any], cfg: GenerationConfig, model_dir: Path | None) -> ToolResult:
    dept = _require(params, "department_id", DEPARTMENT_ID_RE)
    frame = con.execute(
        """
        SELECT *
        FROM gold.unit_week_features
        WHERE department_id = ?
        ORDER BY week_end DESC
        LIMIT 1
        """,
        [dept],
    ).fetchdf()
    if frame.empty:
        return ToolResult("predict_shortage", ("gold.unit_week_features", "in_process_predict"), [])
    try:
        models = load_local_models(model_dir or MODEL_DIR)
    except FileNotFoundError as exc:
        return ToolResult(
            "predict_shortage",
            ("gold.unit_week_features", "in_process_predict"),
            [],
            error=str(exc),
        )
    p = float(models.predict_shortage(frame)[0])
    row = {
        "department_id": dept,
        "week_end": jsonable(frame.iloc[0]["week_end"]),
        "p_shortage_14d": p,
        "serving": "in_process_predict",
        "model_serving_live": False,
        "genie_live": False,
    }
    return ToolResult(
        "predict_shortage",
        ("gold.unit_week_features", "in_process_predict"),
        [row],
    )


Handler = Callable[[Any, dict[str, Any], GenerationConfig, Path | None], ToolResult]

TOOLS: dict[str, Handler] = {
    "policy": tool_policy,
    "exec_brief": tool_exec_brief,
    "executive_kpis": tool_executive_kpis,
    "metric_formula": tool_metric_formula,
    "metric_catalog": tool_metric_catalog,
    "high_risk_list": tool_high_risk_list,
    "employee_score": tool_employee_score,
    "unit_shortage": tool_unit_shortage,
    "recommended_actions": tool_recommended_actions,
    "action_summary": tool_action_summary,
    "whatif_scenarios": tool_whatif_scenarios,
    "whatif_scenario": tool_whatif_scenario,
    "model_metrics_valid": tool_model_metrics_valid,
    "fairness_review": tool_fairness_review,
    "predict_attrition": tool_predict_attrition,
    "predict_shortage": tool_predict_shortage,
}

TOOL_TABLES: dict[str, tuple[str, ...]] = {
    "policy": ("conf/default.yaml",),
    "exec_brief": ("gold.exec_brief",),
    "executive_kpis": ("gold.executive_kpis",),
    "metric_formula": ("gold.metric_catalog",),
    "metric_catalog": ("gold.metric_catalog",),
    "high_risk_list": ("gold.employee_risk_scores",),
    "employee_score": ("gold.employee_risk_scores",),
    "unit_shortage": ("gold.unit_shortage_forecast",),
    "recommended_actions": ("gold.recommended_actions",),
    "action_summary": ("gold.action_summary",),
    "whatif_scenarios": ("gold.whatif_scenarios",),
    "whatif_scenario": ("gold.whatif_scenarios",),
    "model_metrics_valid": ("gold.model_metrics",),
    "fairness_review": ("gold.model_fairness_slices",),
    "predict_attrition": ("gold.employee_month_features", "in_process_predict"),
    "predict_shortage": ("gold.unit_week_features", "in_process_predict"),
}


def run_tool(
    tool_id: str,
    *,
    con=None,
    params: dict[str, Any] | None = None,
    cfg: GenerationConfig | None = None,
    model_dir: Path | None = None,
) -> ToolResult:
    if tool_id not in TOOLS:
        raise UnknownToolError(tool_id)
    handler = TOOLS[tool_id]
    config = cfg or load_config("seed")
    try:
        return handler(con, params or {}, config, model_dir)
    except InvalidToolParamError as exc:
        return ToolResult(tool_id, TOOL_TABLES[tool_id], [], error=str(exc))
