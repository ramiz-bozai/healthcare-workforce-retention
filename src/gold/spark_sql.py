"""Rewrite DuckDB gold SQL into Spark SQL for the Lakeflow recipe.

Local tests assert the rewrite; the DLT module is not executed here.
"""

from __future__ import annotations

import re

_CREATE = re.compile(
    r"CREATE OR REPLACE TABLE gold\.\w+\s+AS\s+",
    re.IGNORECASE,
)
_DAY_SERIES = re.compile(
    r"FROM generate_series\(\s*DATE '([^']+)',\s*DATE '([^']+)',\s*INTERVAL 1 DAY\s*\) AS t\(d\)",
    re.IGNORECASE,
)
_MONTH_SERIES = re.compile(
    r"FROM generate_series\(\s*date_trunc\('month',\s*DATE '([^']+)'\),\s*"
    r"date_trunc\('month',\s*DATE '([^']+)'\)\s*-\s*INTERVAL 1 MONTH,\s*"
    r"INTERVAL 1 MONTH\s*\) AS t\(d\)",
    re.IGNORECASE | re.DOTALL,
)
_DATE_DIFF = re.compile(r"date_diff\('day',\s*([^,]+),\s*([^)]+)\)", re.IGNORECASE)


def to_spark_select(sql: str) -> str:
    """Return a Spark SELECT that reads LIVE.silver_* / LIVE.gold_* tables."""
    s = _CREATE.sub("", sql.strip(), count=1)
    s = _MONTH_SERIES.sub(
        r"FROM (SELECT explode(sequence("
        r"date_trunc('MONTH', DATE '\1'), "
        r"add_months(date_trunc('MONTH', DATE '\2'), -1), "
        r"INTERVAL 1 MONTH)) AS d)",
        s,
    )
    s = _DAY_SERIES.sub(
        r"FROM (SELECT explode(sequence(DATE '\1', DATE '\2', INTERVAL 1 DAY)) AS d)",
        s,
    )
    s = _DATE_DIFF.sub(r"datediff(\2, \1)", s)
    s = re.sub(r"\bVARCHAR\b(?!\s*\()", "STRING", s)
    s = re.sub(r"\bgold\.(\w+)", r"LIVE.gold_\1", s)
    s = re.sub(r"\bsilver\.(\w+)", r"LIVE.silver_\1", s)
    return s.strip()
