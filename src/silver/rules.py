"""Load DQ rules from conf/dq_rules.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.common.paths import DQ_RULES_PATH


@dataclass(frozen=True)
class DqRule:
    id: str
    table: str
    severity: str
    record_key: str
    description: str
    sql: str
    row_predicate: str | None


def _render(sql: str, as_of: str, history_start: str) -> str:
    return sql.replace("__AS_OF__", as_of).replace("__HISTORY_START__", history_start)


def load_rules(
    as_of: str,
    history_start: str,
    path: Path | None = None,
) -> list[DqRule]:
    raw = yaml.safe_load((path or DQ_RULES_PATH).read_text())
    rules = []
    for item in raw["rules"]:
        pred = item.get("row_predicate")
        rules.append(
            DqRule(
                id=item["id"],
                table=item["table"],
                severity=item["severity"],
                record_key=item["record_key"],
                description=item["description"],
                sql=_render(item["sql"], as_of, history_start),
                row_predicate=_render(pred, as_of, history_start) if pred else None,
            )
        )
    return rules


def spark_row_expectations(table: str, rules: list[DqRule]) -> dict[str, str]:
    """Per-row Lakeflow/DLT expects. Uniqueness and FK rules are omitted."""
    return {rule.id: rule.row_predicate for rule in rules if rule.table == table and rule.row_predicate}


# Composite key used to drop error rows from silver.
SILVER_KEY_SQL = {
    "employees": "employee_id",
    "schedule_assignments": "assignment_id",
    "time_cards": "time_card_id",
    "absences": "absence_id",
    "staffing_requirements": "department_id || '|' || CAST(requirement_date AS VARCHAR) || '|' || shift_code",
    "attrition_events": "employee_id || '|' || CAST(separation_date AS VARCHAR)",
    "facilities": "facility_id",
    "departments": "department_id",
    "roles": "role_code",
    "shifts": "shift_code",
    "compensation_bands": "role_code || '|' || band_code",
    "role_cost_assumptions": "role_code",
    "census_proxy": "department_id || '|' || CAST(census_date AS VARCHAR)",
    "open_positions": "position_id",
}
