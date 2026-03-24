"""Introspect Toolset — read-only datasource structure extraction.

Provides SQL (SELECT-only), CSV, JSON, MongoDB, and BigQuery introspection tools.
No network access, no file system writes.
"""

from __future__ import annotations

import asyncio
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

# BigQuery schema type to inferred type mapping
_BIGQUERY_TYPE_MAP = {
    "STRING": "string",
    "INT64": "integer",
    "INTEGER": "integer",
    "FLOAT64": "decimal",
    "FLOAT": "decimal",
    "NUMERIC": "decimal",
    "BIGNUMERIC": "decimal",
    "BOOL": "boolean",
    "BOOLEAN": "boolean",
    "DATE": "date",
    "DATETIME": "datetime",
    "TIMESTAMP": "datetime",
    "TIME": "time",
    "BYTES": "string",
    "JSON": "object",
    "STRUCT": "object",
    "RECORD": "object",
    "ARRAY": "array",
    "GEOGRAPHY": "string",
}

# SQL type name to inferred type mapping (case-insensitive lookup via upper())
_SQL_TYPE_MAP = {
    "INTEGER": "integer",
    "INT": "integer",
    "SMALLINT": "integer",
    "BIGINT": "integer",
    "TINYINT": "integer",
    "MEDIUMINT": "integer",
    "SERIAL": "integer",
    "REAL": "decimal",
    "FLOAT": "decimal",
    "DOUBLE": "decimal",
    "DOUBLE PRECISION": "decimal",
    "NUMERIC": "decimal",
    "DECIMAL": "decimal",
    "MONEY": "decimal",
    "VARCHAR": "string",
    "CHAR": "string",
    "CHARACTER VARYING": "string",
    "TEXT": "string",
    "CLOB": "string",
    "NVARCHAR": "string",
    "NCHAR": "string",
    "NTEXT": "string",
    "BOOLEAN": "boolean",
    "BOOL": "boolean",
    "DATE": "date",
    "DATETIME": "datetime",
    "DATETIME2": "datetime",
    "TIMESTAMP": "datetime",
    "TIMESTAMP WITHOUT TIME ZONE": "datetime",
    "TIMESTAMP WITH TIME ZONE": "datetime",
    "TIME": "time",
    "TIME WITHOUT TIME ZONE": "time",
    "TIME WITH TIME ZONE": "time",
    "BLOB": "binary",
    "BYTEA": "binary",
    "BINARY": "binary",
    "VARBINARY": "binary",
    "IMAGE": "binary",
    "JSON": "object",
    "JSONB": "object",
    "XML": "string",
    "UUID": "UUID",
    "UNIQUEIDENTIFIER": "UUID",
    "ARRAY": "array",
    "INET": "string",
    "CIDR": "string",
    "MACADDR": "string",
}


def _sql_type_to_inferred(sql_type_str: str) -> str:
    """Map a raw SQL type string to an inferred type.

    Handles parameterized types like VARCHAR(255) by stripping the parenthetical.
    """
    # Strip parenthetical (e.g., "VARCHAR(255)" -> "VARCHAR")
    base = sql_type_str.split("(")[0].strip().upper()
    return _SQL_TYPE_MAP.get(base, "string")


def _make_column(
    name: str,
    data_type: str,
    sample_values: list | None = None,
    description: str = "",
    enumeration: dict | None = None,
    units: str = "",
    nullable: bool | None = None,
    constraints: dict | None = None,
    range_values: str = "",
    relationships: str = "",
    business_rules: str = "",
    examples: str = "",
    metadata: dict | None = None,
) -> dict:
    """Build a standardized column dict for introspection output."""
    return {
        "name": name,
        "data_type": data_type,
        "sample_values": sample_values or [],
        "description": description,
        "enumeration": enumeration,
        "units": units,
        "nullable": nullable,
        "constraints": constraints or {},
        "range_values": range_values,
        "relationships": relationships,
        "business_rules": business_rules,
        "examples": examples,
        "metadata": metadata or {},
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
            FunctionTool(self.introspect_sql_schema),
            FunctionTool(self.introspect_csv),
            FunctionTool(self.introspect_json),
            FunctionTool(self.introspect_mongodb),
            FunctionTool(self.introspect_bigquery),
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

    async def introspect_csv(self, datasource_name: str, max_rows: int = 100) -> dict:
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
            columns.append(
                _make_column(
                    name=name,
                    data_type=_infer_type(values),
                    sample_values=values[:5],
                )
            )

        # Merge sidecar metadata if configured
        metadata_path = ds.metadata_path
        if metadata_path:
            meta_file = Path(metadata_path)
            if meta_file.is_file():
                sidecar = json.loads(meta_file.read_text())
                col_meta = sidecar.get("columns", {})
                for col in columns:
                    meta = col_meta.get(col["name"], {})
                    desc = meta.get("description") or meta.get("label", "")
                    if desc:
                        col["description"] = desc
                    if meta.get("value_labels"):
                        col["enumeration"] = meta["value_labels"]
                    if meta.get("units"):
                        col["units"] = meta["units"]
                    if meta.get("range_values"):
                        col["range_values"] = meta["range_values"]
                    if meta.get("relationships"):
                        col["relationships"] = meta["relationships"]
                    if meta.get("business_rules"):
                        col["business_rules"] = meta["business_rules"]
                    if meta.get("examples"):
                        col["examples"] = meta["examples"]
                    if meta.get("metadata"):
                        col["metadata"].update(meta["metadata"])

        result = {
            "datasource": datasource_name,
            "type": "csv",
            "columns": columns,
            "row_count": row_count,
        }

        # Write to introspection cache for downstream toolsets
        cache_path = self._cache.introspection_path(datasource_name)
        cache_path.write_text(json.dumps(result, indent=2, default=str))

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
            raise ValueError(f"Datasource '{datasource_name}' is type '{ds.type}', not 'json'")

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

            columns.append(
                _make_column(
                    name=name,
                    data_type=inferred,
                    sample_values=values[:5],
                )
            )

        # Merge sidecar metadata if configured
        metadata_path = ds.metadata_path
        if metadata_path:
            meta_file = Path(metadata_path)
            if meta_file.is_file():
                sidecar = json.loads(meta_file.read_text())
                col_meta = sidecar.get("columns", {})
                for col in columns:
                    meta = col_meta.get(col["name"], {})
                    desc = meta.get("description") or meta.get("label", "")
                    if desc:
                        col["description"] = desc
                    if meta.get("value_labels"):
                        col["enumeration"] = meta["value_labels"]
                    if meta.get("units"):
                        col["units"] = meta["units"]
                    if meta.get("range_values"):
                        col["range_values"] = meta["range_values"]
                    if meta.get("relationships"):
                        col["relationships"] = meta["relationships"]
                    if meta.get("business_rules"):
                        col["business_rules"] = meta["business_rules"]
                    if meta.get("examples"):
                        col["examples"] = meta["examples"]
                    if meta.get("metadata"):
                        col["metadata"].update(meta["metadata"])

        result = {
            "datasource": datasource_name,
            "type": "json",
            "columns": columns,
            "row_count": row_count,
        }

        # Write to introspection cache for downstream toolsets
        cache_path = self._cache.introspection_path(datasource_name)
        cache_path.write_text(json.dumps(result, indent=2, default=str))

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
            raise ValueError(f"Datasource '{datasource_name}' is type '{ds.type}', not 'mongodb'")

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

            # Try to fetch JSON Schema validator for native metadata
            validator_schema: dict | None = None
            try:
                coll_info = await db.command("listCollections", filter={"name": coll_name})
                first_batch = coll_info.get("cursor", {}).get("firstBatch", [])
                if first_batch:
                    options = first_batch[0].get("options", {})
                    validator = options.get("validator", {})
                    validator_schema = validator.get("$jsonSchema")
            except Exception:
                pass  # No validator — proceed with sampling only

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

            # Extract validator metadata per field
            validator_props = {}
            validator_required: set = set()
            if validator_schema:
                validator_props = validator_schema.get("properties", {})
                validator_required = set(validator_schema.get("required", []))

            fields = []
            for name, info in field_info.items():
                # Pick the most common non-null type
                types = info["types"] - {"null"}
                bson_type = next(iter(types)) if types else "null"

                # Build constraints and metadata from validator
                description = ""
                enumeration = None
                constraints: dict = {}
                range_values = ""
                business_rules = ""
                field_metadata = {"bson_type": bson_type}

                vprop = validator_props.get(name, {})
                if vprop:
                    if vprop.get("description"):
                        description = vprop["description"]
                    if vprop.get("enum"):
                        enumeration = {str(v): str(v) for v in vprop["enum"]}
                    if "minimum" in vprop or "maximum" in vprop:
                        if "minimum" in vprop:
                            constraints["min"] = vprop["minimum"]
                        if "maximum" in vprop:
                            constraints["max"] = vprop["maximum"]
                        parts = []
                        if "minimum" in vprop:
                            parts.append(f"min={vprop['minimum']}")
                        if "maximum" in vprop:
                            parts.append(f"max={vprop['maximum']}")
                        range_values = ", ".join(parts)
                    if vprop.get("pattern"):
                        constraints["pattern"] = vprop["pattern"]
                        business_rules = f"pattern: {vprop['pattern']}"

                # Merge validator required with sampling-based nullable
                nullable = info["nullable"]
                if name in validator_required and not info["nullable"]:
                    nullable = False

                col = _make_column(
                    name=name,
                    data_type=_BSON_TYPE_MAP.get(bson_type, "string"),
                    sample_values=info["sample_values"],
                    description=description,
                    enumeration=enumeration,
                    nullable=nullable,
                    constraints=constraints,
                    range_values=range_values,
                    business_rules=business_rules,
                    metadata=field_metadata,
                )
                # Preserve backward-compat bson_type at top level
                col["bson_type"] = bson_type
                fields.append(col)
        finally:
            client.close()

        result = {
            "datasource": datasource_name,
            "collection": coll_name,
            "columns": fields,
            "row_count": doc_count,
        }

        # Write to introspection cache for downstream toolsets
        cache_path = self._cache.introspection_path(datasource_name)
        cache_path.write_text(json.dumps(result, indent=2, default=str))

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

    async def introspect_bigquery(
        self,
        datasource_name: str,
        dataset: Optional[str] = None,
        table: Optional[str] = None,
        max_rows: int = 100,
    ) -> dict:
        """Introspect a BigQuery dataset or table to discover structure and types.

        Read-only: uses list_rows and schema access only.

        Args:
            datasource_name: Name of a configured BigQuery datasource (from config).
            dataset: Dataset name. Overrides config-level dataset if provided.
            table: Table name. If omitted, lists all tables in the dataset.
            max_rows: Maximum rows to sample for type inference (default 100).

        Returns:
            Dict with datasource, type, dataset, table (if specified),
            columns (name, inferred_type, sample_values), and row_count.
        """
        start = time.monotonic()
        ds = self._get_datasource(datasource_name)

        if ds.type != "bigquery":
            raise ValueError(f"Datasource '{datasource_name}' is type '{ds.type}', not 'bigquery'")

        project = ds.project
        if not project:
            raise ValueError(
                f"No project specified for datasource '{datasource_name}'. "
                "Set 'project' in datasource config."
            )

        ds_name = dataset or ds.dataset

        from google.cloud import bigquery

        def _bq_field_to_column(field) -> dict:
            """Convert a BigQuery SchemaField to a standardized column dict."""
            inferred = _BIGQUERY_TYPE_MAP.get(field.field_type, "string")
            # Native metadata extraction
            nullable = None
            if field.mode == "REQUIRED":
                nullable = False
            elif field.mode in ("NULLABLE", "REPEATED"):
                nullable = True

            relationships = ""
            if field.field_type in ("STRUCT", "RECORD") and field.fields:
                child_names = ", ".join(f.name for f in field.fields)
                relationships = f"STRUCT with fields: {child_names}"

            return _make_column(
                name=field.name,
                data_type=inferred,
                description=field.description or "",
                nullable=nullable,
                relationships=relationships,
                metadata={
                    "bigquery_type": field.field_type,
                    "bigquery_mode": field.mode,
                },
            )

        def _run_sync():
            client = bigquery.Client(project=project)
            try:
                if table:
                    # Introspect a specific table
                    table_ref = f"{project}.{ds_name}.{table}" if ds_name else f"{project}.{table}"
                    bq_table = client.get_table(table_ref)

                    # Get schema fields
                    columns = [_bq_field_to_column(f) for f in bq_table.schema]

                    # Get sample rows
                    rows_iter = client.list_rows(bq_table, max_results=max_rows)
                    rows = list(rows_iter)
                    for row in rows:
                        for col in columns:
                            if len(col["sample_values"]) < 5:
                                val = row.get(col["name"])
                                col["sample_values"].append(str(val) if val is not None else None)

                    return {
                        "datasource": datasource_name,
                        "type": "bigquery",
                        "dataset": ds_name,
                        "table": table,
                        "columns": columns,
                        "row_count": bq_table.num_rows,
                    }
                else:
                    # List tables in dataset
                    if not ds_name:
                        raise ValueError(
                            f"No dataset specified for datasource '{datasource_name}'. "
                            "Provide via tool parameter or datasource config."
                        )
                    tables = list(client.list_tables(f"{project}.{ds_name}"))
                    table_list = []
                    for tbl in tables:
                        full_table = client.get_table(tbl.reference)
                        columns = [_bq_field_to_column(f) for f in full_table.schema]
                        table_list.append(
                            {
                                "table": tbl.table_id,
                                "columns": columns,
                                "row_count": full_table.num_rows,
                            }
                        )
                    # Flatten all table columns into top-level columns list
                    all_columns = []
                    for tbl_info in table_list:
                        for col in tbl_info["columns"]:
                            col["metadata"]["source_table"] = tbl_info["table"]
                            all_columns.append(col)
                    return {
                        "datasource": datasource_name,
                        "type": "bigquery",
                        "dataset": ds_name,
                        "columns": all_columns,
                        "row_count": sum(t.get("row_count", 0) or 0 for t in table_list),
                        "tables": table_list,
                    }
            finally:
                client.close()

        result = await asyncio.to_thread(_run_sync)

        # Write to introspection cache for downstream toolsets
        cache_path = self._cache.introspection_path(datasource_name)
        cache_path.write_text(json.dumps(result, indent=2, default=str))

        self._audit.log(
            agent="introspect",
            tool="introspect_bigquery",
            inputs={
                "datasource_name": datasource_name,
                "dataset": ds_name,
                "table": table,
                "max_rows": max_rows,
            },
            outputs=result,
            start_time=start,
        )
        return result

    async def introspect_sql_schema(
        self,
        datasource_name: str,
        table_name: str | None = None,
    ) -> dict:
        """Introspect a SQL database schema using catalog metadata.

        Uses SQLAlchemy's inspector to extract column types, nullability,
        primary keys, foreign keys, check constraints, and defaults.

        Args:
            datasource_name: Name of a configured SQL datasource (from config).
            table_name: Specific table to introspect. If omitted, introspects
                all tables in the database.

        Returns:
            Dict with datasource, type, and tables (each with columns in
            standardized 13-field format).
        """
        start = time.monotonic()
        ds = self._get_datasource(datasource_name)

        if ds.type != "sql":
            raise ValueError(f"Datasource '{datasource_name}' is type '{ds.type}', not 'sql'")

        from sqlalchemy import inspect as sa_inspect
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(ds.connection_string)
        try:

            def _inspect_sync(conn):
                inspector = sa_inspect(conn)
                table_names = [table_name] if table_name else inspector.get_table_names()
                tables = []
                for tbl in table_names:
                    # Get primary keys
                    try:
                        pk_info = inspector.get_pk_constraint(tbl)
                        pk_cols = set(pk_info.get("constrained_columns", []))
                    except Exception:
                        pk_cols = set()

                    # Get foreign keys
                    fk_map: dict[str, str] = {}
                    try:
                        for fk in inspector.get_foreign_keys(tbl):
                            ref_table = fk.get("referred_table", "")
                            ref_cols = fk.get("referred_columns", [])
                            for i, col_name in enumerate(fk.get("constrained_columns", [])):
                                ref_col = ref_cols[i] if i < len(ref_cols) else ""
                                fk_map[col_name] = f"{ref_table}.{ref_col}"
                    except Exception:
                        pass

                    # Get check constraints
                    check_map: dict[str, list[str]] = {}
                    try:
                        for ck in inspector.get_check_constraints(tbl):
                            sqltext = ck.get("sqltext", "")
                            # Try to associate with columns mentioned in the expression
                            for col_info in inspector.get_columns(tbl):
                                if col_info["name"] in sqltext:
                                    check_map.setdefault(col_info["name"], []).append(sqltext)
                    except Exception:
                        pass

                    # Get columns
                    columns = []
                    for col_info in inspector.get_columns(tbl):
                        col_name = col_info["name"]
                        raw_type = str(col_info["type"])
                        inferred = _sql_type_to_inferred(raw_type)

                        # Build constraints
                        constraints: dict = {}
                        if col_name in pk_cols:
                            constraints["primary_key"] = True
                        if col_info.get("autoincrement") is True:
                            constraints["autoincrement"] = True
                        if col_info.get("default") is not None:
                            default_val = col_info["default"]
                            if hasattr(default_val, "arg"):
                                constraints["default"] = str(default_val.arg)
                            else:
                                constraints["default"] = str(default_val)

                        # Relationships from FK
                        relationships = fk_map.get(col_name, "")

                        # Business rules from CHECK constraints
                        checks = check_map.get(col_name, [])
                        business_rules = "; ".join(checks) if checks else ""

                        # Description from column comment (PostgreSQL/MySQL)
                        description = col_info.get("comment", "") or ""

                        columns.append(
                            _make_column(
                                name=col_name,
                                data_type=inferred,
                                nullable=col_info.get("nullable"),
                                description=description,
                                constraints=constraints,
                                relationships=relationships,
                                business_rules=business_rules,
                                metadata={"sql_type": raw_type},
                            )
                        )
                    tables.append(
                        {
                            "table": tbl,
                            "columns": columns,
                        }
                    )
                return tables

            async with engine.connect() as conn:
                tables = await conn.run_sync(_inspect_sync)
        finally:
            await engine.dispose()

        # Flatten all table columns into top-level columns list
        all_columns = []
        for tbl_info in tables:
            for col in tbl_info["columns"]:
                col["metadata"]["source_table"] = tbl_info["table"]
                all_columns.append(col)

        result = {
            "datasource": datasource_name,
            "type": "sql",
            "columns": all_columns,
            "row_count": 0,
            "tables": tables,
        }

        # Write to introspection cache for downstream toolsets
        cache_path = self._cache.introspection_path(datasource_name)
        cache_path.write_text(json.dumps(result, indent=2, default=str))

        self._audit.log(
            agent="introspect",
            tool="introspect_sql_schema",
            inputs={"datasource_name": datasource_name, "table_name": table_name},
            outputs=result,
            start_time=start,
        )
        return result
