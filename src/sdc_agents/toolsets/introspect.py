"""Introspect Toolset — read-only datasource structure extraction.

Provides SQL (SELECT-only) and CSV introspection tools.
No network access, no file system writes.
"""

from __future__ import annotations

import csv
import io
import re
import time
from pathlib import Path
from typing import Optional

from google.adk.tools import FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.cache import CacheManager
from sdc_agents.common.config import SDCAgentsConfig

# Regex to reject write operations — anchored to start of statement
_WRITE_PATTERN = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE)\b",
    re.IGNORECASE,
)

# Type inference patterns ordered by specificity
_BOOL_VALUES = {"true", "false", "yes", "no", "1", "0", "t", "f", "y", "n"}
_INTEGER_PATTERN = re.compile(r"^-?\d+$")
_DECIMAL_PATTERN = re.compile(r"^-?\d+\.\d+$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_PATTERN = re.compile(r"^https?://\S+$")
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def _infer_type(values: list[str]) -> str:
    """Infer the most specific type from a list of sample string values.

    Order: boolean > integer > decimal > date > datetime > time > email > URL > UUID > string
    """
    non_empty = [v.strip() for v in values if v.strip()]
    if not non_empty:
        return "string"

    # Check each type — all non-empty values must match
    if all(v.lower() in _BOOL_VALUES for v in non_empty):
        return "boolean"
    if all(_INTEGER_PATTERN.match(v) for v in non_empty):
        return "integer"
    if all(_DECIMAL_PATTERN.match(v) for v in non_empty):
        return "decimal"
    if all(_DATE_PATTERN.match(v) for v in non_empty):
        return "date"
    if all(_DATETIME_PATTERN.match(v) for v in non_empty):
        return "datetime"
    if all(_TIME_PATTERN.match(v) for v in non_empty):
        return "time"
    if all(_EMAIL_PATTERN.match(v) for v in non_empty):
        return "email"
    if all(_URL_PATTERN.match(v) for v in non_empty):
        return "URL"
    if all(_UUID_PATTERN.match(v) for v in non_empty):
        return "UUID"
    return "string"


class IntrospectToolset(BaseToolset):
    """Scoped toolset for datasource structure extraction.

    Read-only access to configured datasources. SQL queries are
    restricted to SELECT statements only.
    """

    def __init__(self, config: SDCAgentsConfig, **kwargs):
        super().__init__(**kwargs)
        self._config = config
        self._cache = CacheManager(config.cache.root)
        self._cache.ensure_dirs()
        self._audit = AuditLogger(config.audit.path, config.audit.log_level)

    async def get_tools(self, readonly_context=None) -> list:
        """Return the introspection tools as FunctionTool instances."""
        tools = [
            FunctionTool(self.introspect_sql),
            FunctionTool(self.introspect_csv),
        ]
        if readonly_context and self.tool_filter:
            return [t for t in tools if self._is_tool_selected(t, readonly_context)]
        return tools

    def _get_datasource(self, name: str):
        """Look up a datasource by name from config. Raises KeyError if unknown."""
        if name not in self._config.datasources:
            raise KeyError(
                f"Unknown datasource '{name}'. "
                f"Available: {list(self._config.datasources.keys())}"
            )
        return self._config.datasources[name]

    async def introspect_sql(self, datasource_name: str, query: str) -> list[dict]:
        """Execute a read-only SQL query against a configured datasource.

        Only SELECT statements are allowed. INSERT, UPDATE, DELETE, DROP,
        ALTER, CREATE, TRUNCATE, REPLACE, and MERGE are rejected.

        Args:
            datasource_name: Name of a configured SQL datasource (from config).
            query: SQL SELECT query to execute.

        Returns:
            List of row dictionaries with column names as keys.
        """
        start = time.monotonic()
        ds = self._get_datasource(datasource_name)

        if ds.type != "sql":
            raise ValueError(f"Datasource '{datasource_name}' is type '{ds.type}', not 'sql'")

        # Enforce read-only
        if _WRITE_PATTERN.match(query):
            raise PermissionError(
                f"Write operations are not allowed. Only SELECT queries are permitted. "
                f"Rejected query: {query[:100]}"
            )

        import sqlalchemy
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(ds.connection_string)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(sqlalchemy.text(query))
                columns = list(result.keys())
                rows = [dict(zip(columns, row)) for row in result.fetchall()]
        finally:
            await engine.dispose()

        self._audit.log(
            agent="introspect",
            tool="introspect_sql",
            inputs={"datasource_name": datasource_name, "query": query},
            outputs=rows,
            start_time=start,
        )
        return rows

    async def introspect_csv(
        self, datasource_name: str, max_rows: int = 100
    ) -> dict:
        """Introspect a CSV datasource to discover column structure and types.

        Reads the CSV file, infers types from sample values, and returns
        column metadata.

        Args:
            datasource_name: Name of a configured CSV datasource (from config).
            max_rows: Maximum rows to read for type inference (default 100).

        Returns:
            Dict with datasource name, type, columns (name, inferred_type,
            sample_values), and row_count.
        """
        start = time.monotonic()
        ds = self._get_datasource(datasource_name)

        if ds.type != "csv":
            raise ValueError(f"Datasource '{datasource_name}' is type '{ds.type}', not 'csv'")

        csv_path = Path(ds.path)
        if not csv_path.is_file():
            raise FileNotFoundError(f"CSV file not found: {ds.path}")

        content = csv_path.read_text()
        reader = csv.DictReader(io.StringIO(content))
        fieldnames = reader.fieldnames or []

        # Collect values per column
        column_values: dict[str, list[str]] = {name: [] for name in fieldnames}
        row_count = 0
        for row in reader:
            if row_count >= max_rows:
                break
            for name in fieldnames:
                column_values[name].append(row.get(name, ""))
            row_count += 1

        columns = []
        for name in fieldnames:
            values = column_values[name]
            columns.append({
                "name": name,
                "inferred_type": _infer_type(values),
                "sample_values": values[:5],
            })

        result = {
            "datasource": datasource_name,
            "type": "csv",
            "columns": columns,
            "row_count": row_count,
        }

        self._audit.log(
            agent="introspect",
            tool="introspect_csv",
            inputs={"datasource_name": datasource_name, "max_rows": max_rows},
            outputs=result,
            start_time=start,
        )
        return result
