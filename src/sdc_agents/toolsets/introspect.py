"""Introspect Toolset — read-only datasource structure extraction.

Provides SQL (SELECT-only), CSV, JSON, and MongoDB introspection tools.
No network access, no file system writes.
"""

from __future__ import annotations

import csv
import io
import json
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

# BSON type to inferred type mapping
_BSON_TYPE_MAP = {
    "string": "string",
    "int": "integer",
    "int32": "integer",
    "int64": "integer",
    "long": "integer",
    "double": "decimal",
    "decimal": "decimal",
    "decimal128": "decimal",
    "bool": "boolean",
    "date": "datetime",
    "timestamp": "datetime",
    "objectId": "objectId",
    "array": "array",
    "object": "object",
    "null": "null",
    "binData": "binary",
    "regex": "string",
}


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


def _infer_json_type(value: object) -> str:
    """Infer a type string from a Python/JSON value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "decimal"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    # For strings, use _infer_type for more specific detection
    s = str(value)
    return _infer_type([s])


def _bson_type_name(value: object) -> str:
    """Return a BSON-style type name for a Python value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    type_name = type(value).__name__
    # Handle common BSON types from motor/pymongo
    if type_name == "ObjectId":
        return "objectId"
    if type_name in ("datetime", "Timestamp"):
        return "date"
    if type_name == "Decimal128":
        return "decimal128"
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
            FunctionTool(self.introspect_json),
            FunctionTool(self.introspect_mongodb),
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

    async def introspect_json(
        self,
        datasource_name: str,
        jsonpath: Optional[str] = None,
    ) -> dict:
        """Introspect a JSON datasource to discover structure and types.

        Reads a JSON file, optionally extracts records via JSONPath, and
        infers types from values.

        Args:
            datasource_name: Name of a configured JSON datasource (from config).
            jsonpath: Optional JSONPath expression to extract records. Overrides
                the config-level jsonpath if provided.

        Returns:
            Dict with datasource name, type, columns (name, inferred_type,
            sample_values), and row_count.
        """
        start = time.monotonic()
        ds = self._get_datasource(datasource_name)

        if ds.type != "json":
            raise ValueError(
                f"Datasource '{datasource_name}' is type '{ds.type}', not 'json'"
            )

        json_path = Path(ds.path)
        if not json_path.is_file():
            raise FileNotFoundError(f"JSON file not found: {ds.path}")

        raw = json.loads(json_path.read_text())

        # Apply JSONPath extraction if specified
        jp_expr = jsonpath or ds.jsonpath
        if jp_expr:
            from jsonpath_ng import parse as jp_parse

            expression = jp_parse(jp_expr)
            matches = expression.find(raw)
            records = [m.value for m in matches]
        else:
            # If raw is a list, use directly; otherwise wrap in list
            records = raw if isinstance(raw, list) else [raw]

        # Analyze records — expect list of dicts (or mixed)
        column_values: dict[str, list] = {}
        row_count = 0
        for record in records:
            if not isinstance(record, dict):
                continue
            row_count += 1
            for key, value in record.items():
                column_values.setdefault(key, []).append(value)

        columns = []
        for name, values in column_values.items():
            # Infer type from string representations for string inference,
            # or use direct type inference for JSON native types
            str_values = [str(v) for v in values if v is not None]
            if str_values:
                inferred = _infer_type(str_values)
            else:
                inferred = "string"

            # Override with more specific JSON-native types
            non_null = [v for v in values if v is not None]
            if non_null:
                first = non_null[0]
                if isinstance(first, dict):
                    inferred = "object"
                elif isinstance(first, list):
                    inferred = "array"

            columns.append({
                "name": name,
                "inferred_type": inferred,
                "sample_values": values[:5],
            })

        result = {
            "datasource": datasource_name,
            "type": "json",
            "columns": columns,
            "row_count": row_count,
        }

        self._audit.log(
            agent="introspect",
            tool="introspect_json",
            inputs={"datasource_name": datasource_name, "jsonpath": jp_expr},
            outputs=result,
            start_time=start,
        )
        return result

    async def introspect_mongodb(
        self,
        datasource_name: str,
        collection: Optional[str] = None,
        sample_size: int = 100,
    ) -> dict:
        """Introspect a MongoDB collection to discover document structure.

        Samples documents from a MongoDB collection and analyzes field types.
        Read-only: only find() calls, no inserts/updates/deletes.

        Args:
            datasource_name: Name of a configured MongoDB datasource (from config).
            collection: Collection name. Overrides config-level collection if provided.
            sample_size: Number of documents to sample (default 100).

        Returns:
            Dict with datasource, collection, fields (name, bson_type, nullable,
            sample_values), and document_count.
        """
        start = time.monotonic()
        ds = self._get_datasource(datasource_name)

        if ds.type != "mongodb":
            raise ValueError(
                f"Datasource '{datasource_name}' is type '{ds.type}', not 'mongodb'"
            )

        coll_name = collection or ds.collection
        if not coll_name:
            raise ValueError(
                f"No collection specified for datasource '{datasource_name}'. "
                "Provide via tool parameter or datasource config."
            )

        db_name = ds.database
        if not db_name:
            raise ValueError(
                f"No database specified for datasource '{datasource_name}'. "
                "Set 'database' in datasource config."
            )

        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(ds.connection_string)
        try:
            db = client[db_name]
            coll = db[coll_name]

            # Sample documents (read-only)
            cursor = coll.find().limit(sample_size)
            docs = await cursor.to_list(length=sample_size)
            doc_count = await coll.count_documents({})

            # Analyze fields across all sampled documents
            field_info: dict[str, dict] = {}
            for doc in docs:
                for key, value in doc.items():
                    if key not in field_info:
                        field_info[key] = {
                            "types": set(),
                            "nullable": False,
                            "sample_values": [],
                        }
                    info = field_info[key]
                    btype = _bson_type_name(value)
                    info["types"].add(btype)
                    if value is None:
                        info["nullable"] = True
                    if len(info["sample_values"]) < 5:
                        # Convert ObjectId etc. to string for serialization
                        sample_val = str(value) if btype == "objectId" else value
                        info["sample_values"].append(sample_val)

                # Check for fields present in schema but missing in this doc
                for known_key in list(field_info.keys()):
                    if known_key not in doc:
                        field_info[known_key]["nullable"] = True

            fields = []
            for name, info in field_info.items():
                # Pick the most common non-null type
                types = info["types"] - {"null"}
                bson_type = next(iter(types)) if types else "null"
                fields.append({
                    "name": name,
                    "bson_type": bson_type,
                    "nullable": info["nullable"],
                    "sample_values": info["sample_values"],
                })
        finally:
            client.close()

        result = {
            "datasource": datasource_name,
            "collection": coll_name,
            "fields": fields,
            "document_count": doc_count,
        }

        self._audit.log(
            agent="introspect",
            tool="introspect_mongodb",
            inputs={
                "datasource_name": datasource_name,
                "collection": coll_name,
                "sample_size": sample_size,
            },
            outputs=result,
            start_time=start,
        )
        return result
