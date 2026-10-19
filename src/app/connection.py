"""Gold connection: DuckDB locally, Databricks SQL warehouse in a workspace App."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd

from src.common.paths import DEFAULT_DUCKDB

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GOLD = re.compile(r"\bgold\.(\w+)")
_SILVER = re.compile(r"\bsilver\.(\w+)")
_INFO_GOLD = re.compile(
    r"SELECT\s+table_name\s+FROM\s+information_schema\.tables\s+"
    r"WHERE\s+table_schema\s*=\s*'gold'",
    re.I,
)


def _ident(value: str, label: str) -> str:
    if not _IDENT.match(value):
        raise ValueError(f"Invalid {label}")
    return value


def rewrite_workspace_sql(sql: str, catalog: str, schema: str) -> str:
    catalog = _ident(catalog, "catalog")
    schema = _ident(schema, "schema")
    if _INFO_GOLD.search(sql):
        return (
            f"SELECT regexp_replace(table_name, '^gold_', '') AS table_name "
            f"FROM {catalog}.information_schema.tables "
            f"WHERE table_schema = '{schema}' AND table_name LIKE 'gold_%'"
        )
    out = _GOLD.sub(rf"{catalog}.{schema}.gold_\1", sql)
    out = _SILVER.sub(rf"{catalog}.{schema}.silver_\1", out)
    return out


class QueryResult:
    def __init__(self, frame: pd.DataFrame):
        self._frame = frame

    def fetchdf(self) -> pd.DataFrame:
        return self._frame

    def fetchone(self):
        if self._frame.empty:
            return None
        return tuple(self._frame.iloc[0].tolist())

    def fetchall(self):
        return [tuple(row) for row in self._frame.itertuples(index=False, name=None)]


class WarehouseConnection:
    def __init__(self, warehouse_id: str, catalog: str, schema: str):
        from databricks import sql
        from databricks.sdk.core import Config

        cfg = Config()
        host = os.environ.get("DATABRICKS_SERVER_HOSTNAME") or os.environ.get("DATABRICKS_HOST") or cfg.host
        host = str(host).replace("https://", "").replace("http://", "").rstrip("/")
        http_path = os.environ.get("DATABRICKS_HTTP_PATH") or f"/sql/1.0/warehouses/{warehouse_id}"
        self._catalog = catalog
        self._schema = schema
        self._conn = sql.connect(
            server_hostname=host,
            http_path=http_path,
            credentials_provider=lambda: cfg.authenticate,
        )

    def execute(self, sql: str, params=None) -> QueryResult:
        rewritten = rewrite_workspace_sql(sql, self._catalog, self._schema)
        with self._conn.cursor() as cursor:
            if params is None:
                cursor.execute(rewritten)
            else:
                cursor.execute(rewritten, params)
            try:
                table = cursor.fetchall_arrow()
                frame = table.to_pandas()
            except Exception:
                rows = cursor.fetchall()
                names = [c[0] for c in (cursor.description or [])]
                frame = pd.DataFrame(rows, columns=names or None)
        return QueryResult(frame)

    def close(self) -> None:
        self._conn.close()


def warehouse_configured() -> bool:
    return bool(
        os.environ.get("DATABRICKS_WAREHOUSE_ID")
        and os.environ.get("CARESTTAFF_CATALOG")
        and os.environ.get("CARESTTAFF_SCHEMA")
    )


def open_gold(*, duckdb_path: Path | None = None):
    if warehouse_configured():
        return WarehouseConnection(
            os.environ["DATABRICKS_WAREHOUSE_ID"],
            os.environ["CARESTTAFF_CATALOG"],
            os.environ["CARESTTAFF_SCHEMA"],
        )
    import duckdb

    db = Path(os.environ.get("CARESTTAFF_DUCKDB", duckdb_path or DEFAULT_DUCKDB))
    if not db.exists():
        raise FileNotFoundError(
            f"{db} missing. Run `uv run python -m src.pipeline` then `uv run python -m src.ml`, "
            "or set DATABRICKS_WAREHOUSE_ID, CARESTTAFF_CATALOG, and CARESTTAFF_SCHEMA."
        )
    return duckdb.connect(str(db), read_only=True)
