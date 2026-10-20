"""Gold connection: DuckDB locally; Lakebase + SQL warehouse in a workspace App."""

from __future__ import annotations

import os
import re
import threading
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
_GOLD_REFS = re.compile(r"\bgold\.(\w+)")
_LAKEBASE_TABLES = {
    "exec_brief": "gold_exec_brief_serving",
    "employee_risk_scores": "gold_employee_risk_scores_serving",
    "unit_shortage_forecast": "gold_unit_shortage_forecast_serving",
}
_lakebase_pool = None
_lakebase_pool_lock = threading.Lock()


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


def rewrite_lakebase_sql(sql: str, schema: str) -> str:
    schema = _ident(schema, "Lakebase schema")
    refs = set(_GOLD_REFS.findall(sql))
    unsupported = refs - _LAKEBASE_TABLES.keys()
    if not refs or unsupported:
        raise ValueError(f"Query is not served by Lakebase: {sorted(unsupported or refs)}")
    out = sql
    for logical_name in refs:
        table = _LAKEBASE_TABLES[logical_name]
        out = re.sub(
            rf"\bgold\.{re.escape(logical_name)}\b",
            f'"{schema}"."{table}"',
            out,
        )
    return out.replace("?", "%s")


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


def _get_lakebase_pool():
    global _lakebase_pool
    if _lakebase_pool is not None:
        return _lakebase_pool
    with _lakebase_pool_lock:
        if _lakebase_pool is not None:
            return _lakebase_pool

        import psycopg
        from databricks.sdk import WorkspaceClient
        from psycopg.conninfo import make_conninfo
        from psycopg_pool import ConnectionPool

        client = WorkspaceClient()
        endpoint = os.environ["LAKEBASE_ENDPOINT"]

        class OAuthConnection(psycopg.Connection):
            @classmethod
            def connect(cls, conninfo="", **kwargs):
                credential = client.postgres.generate_database_credential(endpoint=endpoint)
                kwargs["password"] = credential.token
                return super().connect(conninfo, **kwargs)

        conninfo = make_conninfo(
            dbname=os.environ["PGDATABASE"],
            user=os.environ["PGUSER"],
            host=os.environ["PGHOST"],
            port=os.environ.get("PGPORT", "5432"),
            sslmode=os.environ.get("PGSSLMODE", "require"),
            options="-c default_transaction_read_only=on",
        )
        _lakebase_pool = ConnectionPool(
            conninfo=conninfo,
            connection_class=OAuthConnection,
            min_size=0,
            max_size=5,
            max_lifetime=3000,
            open=True,
        )
        return _lakebase_pool


class LakebaseConnection:
    def __init__(self, schema: str):
        self._schema = _ident(schema, "Lakebase schema")
        self._pool = _get_lakebase_pool()

    def execute(self, sql: str, params=None) -> QueryResult:
        rewritten = rewrite_lakebase_sql(sql, self._schema)
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(rewritten, params)
                rows = cursor.fetchall()
                names = [
                    getattr(column, "name", None) or column[0]
                    for column in (cursor.description or [])
                ]
        return QueryResult(pd.DataFrame(rows, columns=names or None))

    def close(self) -> None:
        # The process-level pool is intentionally reused across HTTP requests.
        pass


class HybridConnection:
    """Route low-latency serving tables to Lakebase and all other gold to SQL."""

    def __init__(self, warehouse: WarehouseConnection, lakebase: LakebaseConnection):
        self._warehouse = warehouse
        self._lakebase = lakebase

    def execute(self, sql: str, params=None) -> QueryResult:
        refs = set(_GOLD_REFS.findall(sql))
        if refs and refs <= _LAKEBASE_TABLES.keys():
            return self._lakebase.execute(sql, params)
        return self._warehouse.execute(sql, params)

    def close(self) -> None:
        self._warehouse.close()
        self._lakebase.close()


def warehouse_id() -> str | None:
    return os.environ.get("DATABRICKS_WAREHOUSE_ID") or os.environ.get("DATABRICKS_SQL_WAREHOUSE_ID") or None


def warehouse_configured() -> bool:
    return bool(
        warehouse_id()
        and os.environ.get("CARESTAFF_CATALOG")
        and os.environ.get("CARESTAFF_SCHEMA")
    )


def lakebase_configured() -> bool:
    return bool(
        os.environ.get("LAKEBASE_ENDPOINT")
        and os.environ.get("PGHOST")
        and os.environ.get("PGDATABASE")
        and os.environ.get("PGUSER")
        and os.environ.get("CARESTAFF_LAKEBASE_SCHEMA")
    )


def open_gold(*, duckdb_path: Path | None = None):
    if warehouse_configured():
        warehouse = WarehouseConnection(
            warehouse_id(),
            os.environ["CARESTAFF_CATALOG"],
            os.environ["CARESTAFF_SCHEMA"],
        )
        if lakebase_configured():
            return HybridConnection(
                warehouse,
                LakebaseConnection(os.environ["CARESTAFF_LAKEBASE_SCHEMA"]),
            )
        if os.environ.get("DATABRICKS_APP_NAME") or os.environ.get("DATABRICKS_APP_PORT"):
            warehouse.close()
            raise FileNotFoundError(
                "This Databricks App has no Lakebase serving resource. "
                "Attach the Autoscaling database with resource key postgres, "
                "create the three *_serving synced tables, then redeploy."
            )
        return warehouse
    if os.environ.get("DATABRICKS_APP_NAME") or os.environ.get("DATABRICKS_APP_PORT"):
        raise FileNotFoundError(
            "This Databricks App has no SQL warehouse ID. "
            "Add a SQL warehouse resource with key sql-warehouse (Can use), "
            "grant the app SP SELECT on healthcare_ops.carestaff_insight, then redeploy."
        )
    import duckdb

    db = Path(os.environ.get("CARESTAFF_DUCKDB", duckdb_path or DEFAULT_DUCKDB))
    if not db.exists():
        raise FileNotFoundError(
            f"{db} missing. Run `uv run python -m src.pipeline` then `uv run python -m src.ml`, "
            "or set DATABRICKS_WAREHOUSE_ID, CARESTAFF_CATALOG, and CARESTAFF_SCHEMA."
        )
    return duckdb.connect(str(db), read_only=True)
