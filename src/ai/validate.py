"""Citation validator: every numeric claim in prose must appear in a tool result."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from src.ai.tools import ToolResult

CITE_RE = re.compile(r"\[[a-z][a-z0-9_.\[\]]*\]")
EMP_RE = re.compile(r"EMP-\d{6}")
ACT_RE = re.compile(r"ACT-\d{4}")
ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
DEPT_RE = re.compile(r"\b[A-Z]{2,5}-[A-Z0-9-]+\b")
SNAKE_DIGIT_RE = re.compile(r"\b[a-z][a-z0-9_]*\d[a-z0-9_]*\b")
BLOCKQUOTE_RE = re.compile(r"^>.*$", re.M)
FENCE_RE = re.compile(r"```.*?```", re.S)
NUMBER_RE = re.compile(
    r"\$?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?"
    r"|\$?\d+\.\d+%?"
    r"|\$?\d+%?"
)

SKIP_COLUMNS = frozenset(
    {
        "includes_model",
        "scored",
        "applied",
        "requires_human_review",
        "high_risk_flag",
        "predicted_shortage_flag",
        "is_shortage_week",
        "label_voluntary_90d",
        "label_window_complete_14d",
        "genie_live",
        "model_serving_live",
        "review_flag",
        "random_seed",
        "mode",
        "serving",
        "source",
        "playbook",
        "status",
        "uniform_status",
    }
)


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def numeric_tokens(value: float) -> set[str]:
    if not math.isfinite(value):
        return set()
    tokens: set[str] = set()
    for n in (1, 2, 3, 4, 6):
        rendered = f"{value:.{n}f}".rstrip("0").rstrip(".")
        if rendered and rendered not in {"-", "-0"}:
            tokens.add(rendered)
    if abs(value - round(value)) < 1e-6:
        as_int = int(round(value))
        tokens.add(str(as_int))
        tokens.add(f"{as_int:,}")
    if abs(value) >= 100:
        as_int = int(round(value))
        tokens.add(str(as_int))
        tokens.add(f"{as_int:,}")
        tokens.add(f"${as_int:,}")
        tokens.add(f"${as_int}")
    if abs(value) >= 1_000_000:
        mill = value / 1_000_000
        tokens.add(f"${mill:.2f}M")
        tokens.add(f"${mill:.1f}M")
        tokens.add(f"${mill:.0f}M")
        tokens.add(f"{mill:.2f}M")
        tokens.add(f"{mill:.1f}M")
    if 1000 <= abs(value) < 1_000_000:
        k = value / 1000.0
        tokens.add(f"${k:.0f}k")
        tokens.add(f"${k:.0f}K")
        tokens.add(f"{k:.0f}k")
    if 0 <= abs(value) <= 2.5:
        pct = value * 100.0
        tokens.add(f"{pct:.1f}")
        tokens.add(f"{pct:.0f}")
        tokens.add(f"{pct:.1f}%")
        tokens.add(f"{pct:.0f}%")
        tokens.add(f"{pct:.3f}")
    return {t for t in tokens if t and t not in {".", "-", "-.", "-0"}}


def format_value(key: str, value: Any) -> str:
    col = key.rsplit(".", 1)[-1]
    if value is None:
        return "null"
    if _is_bool(value):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if any(token in col for token in ("_usd", "exposure", "delta_usd")):
        return f"${round(float(value)):,.0f}"
    if any(
        token in col
        for token in (
            "rate",
            "ratio",
            "p_voluntary",
            "p_shortage",
            "mean_p",
            "probability",
            "quantile",
            "base_rate",
            "selection_rate",
            "avg_precision",
            "roc_auc",
            "brier",
            "ece",
        )
    ):
        return f"{float(value):.3f}"
    if isinstance(value, float) and abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, int):
        return f"{value:,}" if abs(value) >= 1000 else str(value)
    return str(value)


@dataclass
class NumberBank:
    values: dict[str, Any] = field(default_factory=dict)
    tokens: set[str] = field(default_factory=set)

    def add(self, cite: str, value: Any) -> None:
        self.values[cite] = value
        if value is None or _is_bool(value) or isinstance(value, str):
            return
        try:
            number = float(value)
        except (TypeError, ValueError):
            return
        self.tokens |= numeric_tokens(number)

    def ingest(self, result: ToolResult) -> None:
        for i, row in enumerate(result.rows):
            prefix = result.tool_id if len(result.rows) == 1 else f"{result.tool_id}[{i}]"
            for col, value in row.items():
                if col in SKIP_COLUMNS:
                    continue
                self.add(f"{prefix}.{col}", value)

    def cite(self, key: str) -> str:
        if key not in self.values:
            raise KeyError(f"citation {key} is not in the tool payload")
        rendered = format_value(key, self.values[key])
        return f"{rendered} [{key}]"

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


def strip_non_claims(text: str) -> str:
    stripped = FENCE_RE.sub(" ", text)
    stripped = BLOCKQUOTE_RE.sub(" ", stripped)
    stripped = CITE_RE.sub(" ", stripped)
    stripped = EMP_RE.sub(" ", stripped)
    stripped = ACT_RE.sub(" ", stripped)
    stripped = ISO_DATE_RE.sub(" ", stripped)
    stripped = DEPT_RE.sub(" ", stripped)
    stripped = SNAKE_DIGIT_RE.sub(" ", stripped)
    return stripped


def extract_numeric_claims(text: str) -> list[str]:
    return NUMBER_RE.findall(strip_non_claims(text))


def _claim_tokens(claim: str) -> set[str]:
    raw = claim.replace(",", "").replace("$", "")
    percent = raw.endswith("%")
    raw = raw.rstrip("%")
    try:
        number = float(raw)
    except ValueError:
        return {claim}
    tokens = numeric_tokens(number) | {claim, raw}
    if percent:
        tokens |= numeric_tokens(number / 100.0)
        tokens.add(f"{number:g}%")
    return tokens


def validate_answer(answer: str, results: Iterable[ToolResult]) -> tuple[bool, list[str]]:
    bank = NumberBank()
    for result in results:
        bank.ingest(result)
    unmatched = []
    for claim in extract_numeric_claims(answer):
        if _claim_tokens(claim) & bank.tokens:
            continue
        unmatched.append(claim)
    return (len(unmatched) == 0, unmatched)


def bank_from_results(results: Iterable[ToolResult]) -> NumberBank:
    bank = NumberBank()
    for result in results:
        bank.ingest(result)
    return bank
