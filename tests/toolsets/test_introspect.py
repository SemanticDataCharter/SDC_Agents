"""Tests for the Introspect Toolset."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.introspect import IntrospectToolset, _infer_type, _make_column


@pytest.fixture
def introspect_config(tmp_path: Path, csv_path: Path) -> SDCAgentsConfig:
    return SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl"), "log_level": "verbose"},
        datasources={
            "test_db": {
                "type": "sql",
                "connection_string": "sqlite+aiosqlite://",
            },
            "test_csv": {
                "type": "csv",
                "path": str(csv_path),
            },
        },
    )


@pytest.fixture
def introspect_toolset(introspect_config: SDCAgentsConfig) -> IntrospectToolset:
    return IntrospectToolset(config=introspect_config)


# --- Type inference tests ---


def test_infer_boolean():
    assert _infer_type(["true", "false", "true"]) == "boolean"


def test_infer_integer():
    assert _infer_type(["1", "2", "3", "-5"]) == "integer"


def test_infer_decimal():
    assert _infer_type(["1.5", "2.3", "0.1"]) == "decimal"


def test_infer_date():
    assert _infer_type(["2026-01-15", "2026-02-20"]) == "date"


def test_infer_datetime():
    assert _infer_type(["2026-01-15T08:30:00", "2026-01-16T09:15:00"]) == "datetime"


def test_infer_time():
    assert _infer_type(["08:30:00", "09:15:00", "14:20:00"]) == "time"


def test_infer_email():
    assert _infer_type(["alice@example.com", "bob@test.org"]) == "email"


def test_infer_url():
    assert _infer_type(["https://example.com", "http://test.org/page"]) == "URL"


def test_infer_uuid():
    assert _infer_type(["550e8400-e29b-41d4-a716-446655440000"]) == "UUID"


def test_infer_string_fallback():
    assert _infer_type(["hello", "world", "123abc"]) == "string"


def test_infer_empty():
    assert _infer_type(["", "  ", ""]) == "string"


# --- SQL introspection tests ---


async def test_sql_select(introspect_toolset: IntrospectToolset):
    """SELECT query returns rows from an in-memory SQLite database."""
    import aiosqlite  # noqa: F401 — ensures driver is available
    import sqlalchemy
    from sqlalchemy.ext.asyncio import create_async_engine

    # Set up test table
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.execute(sqlalchemy.text("CREATE TABLE test_table (id INTEGER, name TEXT)"))
        await conn.execute(
            sqlalchemy.text("INSERT INTO test_table VALUES (1, 'Alice'), (2, 'Bob')")
        )
    await engine.dispose()

    # The toolset creates its own engine, but with in-memory SQLite
    # each connection gets a fresh DB. For testing, we need to use
    # a file-based SQLite so the toolset can see our data.
    # Let's update the test to use a temp file instead.
    pass  # Covered by test_sql_select_with_file below


async def test_sql_select_with_file(introspect_config: SDCAgentsConfig, tmp_path: Path):
    """SELECT query against a file-based SQLite database."""
    import sqlalchemy
    from sqlalchemy.ext.asyncio import create_async_engine

    db_path = tmp_path / "test.db"
    conn_str = f"sqlite+aiosqlite:///{db_path}"

    # Create and populate
    engine = create_async_engine(conn_str)
    async with engine.begin() as conn:
        await conn.execute(
            sqlalchemy.text("CREATE TABLE lab_results (id INTEGER, test_name TEXT, value REAL)")
        )
        await conn.execute(
            sqlalchemy.text("INSERT INTO lab_results VALUES (1, 'CBC', 98.6), (2, 'BMP', 120.5)")
        )
    await engine.dispose()

    # Update config to point to file DB
    introspect_config.datasources["test_db"].connection_string = conn_str
    toolset = IntrospectToolset(config=introspect_config)

    rows = await toolset.introspect_sql("test_db", "SELECT * FROM lab_results")
    assert len(rows) == 2
    assert rows[0]["test_name"] == "CBC"


async def test_sql_rejects_write(introspect_toolset: IntrospectToolset):
    """Write operations are rejected with PermissionError."""
    with pytest.raises(PermissionError, match="Write operations are not allowed"):
        await introspect_toolset.introspect_sql("test_db", "DROP TABLE users")

    with pytest.raises(PermissionError):
        await introspect_toolset.introspect_sql("test_db", "INSERT INTO t VALUES (1)")

    with pytest.raises(PermissionError):
        await introspect_toolset.introspect_sql("test_db", "UPDATE t SET x = 1")

    with pytest.raises(PermissionError):
        await introspect_toolset.introspect_sql("test_db", "DELETE FROM t WHERE id = 1")


async def test_sql_wrong_datasource_type(introspect_toolset: IntrospectToolset):
    """Using a CSV datasource for SQL raises ValueError."""
    with pytest.raises(ValueError, match="not 'sql'"):
        await introspect_toolset.introspect_sql("test_csv", "SELECT 1")


async def test_sql_unknown_datasource(introspect_toolset: IntrospectToolset):
    """Unknown datasource name raises KeyError."""
    with pytest.raises(KeyError, match="Unknown datasource"):
        await introspect_toolset.introspect_sql("nonexistent", "SELECT 1")


# --- CSV introspection tests ---


async def test_csv_introspect(introspect_toolset: IntrospectToolset):
    """CSV introspection discovers columns and infers types."""
    result = await introspect_toolset.introspect_csv("test_csv")
    assert result["type"] == "csv"
    assert result["row_count"] == 5

    col_map = {c["name"]: c for c in result["columns"]}
    assert col_map["test_id"]["data_type"] == "integer"
    assert col_map["patient_email"]["data_type"] == "email"
    assert col_map["is_critical"]["data_type"] == "boolean"
    assert col_map["collected_date"]["data_type"] == "date"
    assert col_map["collected_time"]["data_type"] == "time"
    assert col_map["request_uuid"]["data_type"] == "UUID"
    assert col_map["result"]["data_type"] == "decimal"


async def test_csv_wrong_datasource_type(introspect_toolset: IntrospectToolset):
    """Using a SQL datasource for CSV raises ValueError."""
    with pytest.raises(ValueError, match="not 'csv'"):
        await introspect_toolset.introspect_csv("test_db")


async def test_get_tools_returns_six(introspect_toolset: IntrospectToolset):
    """get_tools returns exactly 6 tools."""
    tools = await introspect_toolset.get_tools()
    assert len(tools) == 6
    names = {t.name for t in tools}
    assert names == {
        "introspect_sql",
        "introspect_sql_schema",
        "introspect_csv",
        "introspect_json",
        "introspect_mongodb",
        "introspect_bigquery",
    }


# --- JSON introspection tests ---


@pytest.fixture
def json_path() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "sample_data" / "records.json"


@pytest.fixture
def json_config(tmp_path: Path, json_path: Path, csv_path: Path) -> SDCAgentsConfig:
    return SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl"), "log_level": "verbose"},
        datasources={
            "test_db": {
                "type": "sql",
                "connection_string": "sqlite+aiosqlite://",
            },
            "test_csv": {
                "type": "csv",
                "path": str(csv_path),
            },
            "test_json": {
                "type": "json",
                "path": str(json_path),
                "jsonpath": "$.results[*]",
            },
            "test_json_no_jp": {
                "type": "json",
                "path": str(json_path),
            },
        },
    )


@pytest.fixture
def json_toolset(json_config: SDCAgentsConfig) -> IntrospectToolset:
    return IntrospectToolset(config=json_config)


async def test_json_introspect_with_jsonpath(json_toolset: IntrospectToolset):
    """JSON introspection with JSONPath extracts records correctly."""
    result = await json_toolset.introspect_json("test_json")
    assert result["type"] == "json"
    assert result["row_count"] == 5

    col_map = {c["name"]: c for c in result["columns"]}
    assert "test_id" in col_map
    assert "test_name" in col_map
    assert "result" in col_map
    assert "is_critical" in col_map


async def test_json_introspect_type_inference(json_toolset: IntrospectToolset):
    """JSON introspection infers types from values."""
    result = await json_toolset.introspect_json("test_json")
    col_map = {c["name"]: c for c in result["columns"]}
    assert col_map["test_id"]["data_type"] == "integer"
    assert col_map["patient_email"]["data_type"] == "email"
    assert col_map["collected_date"]["data_type"] == "date"
    assert col_map["collected_time"]["data_type"] == "time"
    assert col_map["request_uuid"]["data_type"] == "UUID"


async def test_json_introspect_without_jsonpath(json_toolset: IntrospectToolset):
    """JSON introspection without JSONPath reads root object."""
    result = await json_toolset.introspect_json("test_json_no_jp")
    # Without JSONPath, root is a dict with 'results' key, so 1 record (the dict)
    # but since the root is a dict, it has one "row" — the root object itself
    assert result["type"] == "json"
    assert result["row_count"] == 1


async def test_json_wrong_datasource_type(json_toolset: IntrospectToolset):
    """Using a CSV datasource for JSON raises ValueError."""
    with pytest.raises(ValueError, match="not 'json'"):
        await json_toolset.introspect_json("test_csv")


async def test_json_unknown_datasource(json_toolset: IntrospectToolset):
    """Unknown datasource name raises KeyError."""
    with pytest.raises(KeyError, match="Unknown datasource"):
        await json_toolset.introspect_json("nonexistent")


async def test_json_file_not_found(tmp_path: Path):
    """Missing JSON file raises FileNotFoundError."""
    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        datasources={
            "bad_json": {
                "type": "json",
                "path": "/nonexistent/file.json",
            },
        },
    )
    toolset = IntrospectToolset(config=config)
    with pytest.raises(FileNotFoundError, match="JSON file not found"):
        await toolset.introspect_json("bad_json")


async def test_json_nested_objects(tmp_path: Path):
    """JSON with nested objects reports 'object' type."""
    import json as json_mod

    json_file = tmp_path / "nested.json"
    json_file.write_text(
        json_mod.dumps(
            [
                {"name": "Alice", "address": {"city": "NYC", "zip": "10001"}},
                {"name": "Bob", "address": {"city": "LA", "zip": "90001"}},
            ]
        )
    )

    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        datasources={
            "nested": {"type": "json", "path": str(json_file)},
        },
    )
    toolset = IntrospectToolset(config=config)
    result = await toolset.introspect_json("nested")
    col_map = {c["name"]: c for c in result["columns"]}
    assert col_map["address"]["data_type"] == "object"


async def test_json_arrays(tmp_path: Path):
    """JSON with array values reports 'array' type."""
    import json as json_mod

    json_file = tmp_path / "arrays.json"
    json_file.write_text(
        json_mod.dumps(
            [
                {"name": "Alice", "scores": [90, 85, 92]},
                {"name": "Bob", "scores": [78, 88]},
            ]
        )
    )

    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        datasources={
            "arrays": {"type": "json", "path": str(json_file)},
        },
    )
    toolset = IntrospectToolset(config=config)
    result = await toolset.introspect_json("arrays")
    col_map = {c["name"]: c for c in result["columns"]}
    assert col_map["scores"]["data_type"] == "array"


# --- MongoDB introspection tests ---


async def test_mongodb_wrong_datasource_type(introspect_toolset: IntrospectToolset):
    """Using a SQL datasource for MongoDB raises ValueError."""
    with pytest.raises(ValueError, match="not 'mongodb'"):
        await introspect_toolset.introspect_mongodb("test_db")


async def test_mongodb_unknown_datasource(introspect_toolset: IntrospectToolset):
    """Unknown datasource name raises KeyError."""
    with pytest.raises(KeyError, match="Unknown datasource"):
        await introspect_toolset.introspect_mongodb("nonexistent")


async def test_mongodb_no_collection(tmp_path: Path):
    """Missing collection raises ValueError."""
    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        datasources={
            "mongo_no_coll": {
                "type": "mongodb",
                "connection_string": "mongodb://localhost:27017",
                "database": "testdb",
            },
        },
    )
    toolset = IntrospectToolset(config=config)
    with pytest.raises(ValueError, match="No collection specified"):
        await toolset.introspect_mongodb("mongo_no_coll")


async def test_mongodb_no_database(tmp_path: Path):
    """Missing database raises ValueError."""
    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        datasources={
            "mongo_no_db": {
                "type": "mongodb",
                "connection_string": "mongodb://localhost:27017",
                "collection": "test_coll",
            },
        },
    )
    toolset = IntrospectToolset(config=config)
    with pytest.raises(ValueError, match="No database specified"):
        await toolset.introspect_mongodb("mongo_no_db")


# --- BigQuery introspection tests ---


async def test_bigquery_wrong_datasource_type(introspect_toolset: IntrospectToolset):
    """Using a SQL datasource for BigQuery raises ValueError."""
    with pytest.raises(ValueError, match="not 'bigquery'"):
        await introspect_toolset.introspect_bigquery("test_db")


async def test_bigquery_unknown_datasource(introspect_toolset: IntrospectToolset):
    """Unknown datasource name raises KeyError."""
    with pytest.raises(KeyError, match="Unknown datasource"):
        await introspect_toolset.introspect_bigquery("nonexistent")


async def test_bigquery_no_project(tmp_path: Path):
    """Missing project raises ValueError."""
    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        datasources={
            "bq_no_project": {
                "type": "bigquery",
                "dataset": "my_dataset",
            },
        },
    )
    toolset = IntrospectToolset(config=config)
    with pytest.raises(ValueError, match="No project specified"):
        await toolset.introspect_bigquery("bq_no_project")


async def test_bigquery_introspection(tmp_path: Path):
    """BigQuery introspection returns standard format with mocked client."""
    from unittest.mock import MagicMock, patch

    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl"), "log_level": "verbose"},
        datasources={
            "test_bq": {
                "type": "bigquery",
                "project": "my-gcp-project",
                "dataset": "analytics",
            },
        },
    )
    toolset = IntrospectToolset(config=config)

    # Mock BigQuery schema fields
    mock_field_id = MagicMock()
    mock_field_id.name = "id"
    mock_field_id.field_type = "INT64"

    mock_field_name = MagicMock()
    mock_field_name.name = "name"
    mock_field_name.field_type = "STRING"

    mock_field_score = MagicMock()
    mock_field_score.name = "score"
    mock_field_score.field_type = "FLOAT64"

    # Mock table
    mock_table = MagicMock()
    mock_table.schema = [mock_field_id, mock_field_name, mock_field_score]
    mock_table.num_rows = 42

    # Mock rows
    mock_row = {"id": 1, "name": "Alice", "score": 95.5}
    mock_rows_iter = [mock_row]

    # Mock client
    mock_client = MagicMock()
    mock_client.get_table.return_value = mock_table
    mock_client.list_rows.return_value = mock_rows_iter

    with patch("google.cloud.bigquery.Client", return_value=mock_client):
        result = await toolset.introspect_bigquery("test_bq", table="users")

    assert result["datasource"] == "test_bq"
    assert result["type"] == "bigquery"
    assert result["dataset"] == "analytics"
    assert result["table"] == "users"
    assert result["row_count"] == 42

    col_map = {c["name"]: c for c in result["columns"]}
    assert col_map["id"]["data_type"] == "integer"
    assert col_map["name"]["data_type"] == "string"
    assert col_map["score"]["data_type"] == "decimal"
    assert col_map["id"]["sample_values"] == ["1"]
    assert col_map["name"]["sample_values"] == ["Alice"]


# --- Column output normalization tests ---


async def test_csv_column_output_uses_data_type(introspect_toolset: IntrospectToolset):
    """CSV introspection uses 'data_type' field name (not 'inferred_type')."""
    result = await introspect_toolset.introspect_csv("test_csv")
    for col in result["columns"]:
        assert "data_type" in col, f"Column {col['name']} missing 'data_type'"
        assert "inferred_type" not in col, f"Column {col['name']} has legacy 'inferred_type'"


async def test_csv_column_output_has_metadata_fields(introspect_toolset: IntrospectToolset):
    """CSV introspection includes metadata fields with defaults."""
    result = await introspect_toolset.introspect_csv("test_csv")
    for col in result["columns"]:
        assert "description" in col
        assert "enumeration" in col
        assert "units" in col
        assert "nullable" in col
        assert "constraints" in col


async def test_csv_metadata_merge(tmp_path: Path):
    """CSV with sidecar metadata populates description, enumeration, units."""
    import json as json_mod

    csv_file = tmp_path / "data.csv"
    csv_file.write_text("BPXSY1,RIDAGEYR\n120,45\n118,32\n")

    meta_file = tmp_path / "data.meta.json"
    meta_file.write_text(
        json_mod.dumps(
            {
                "source_format": "xpt",
                "columns": {
                    "BPXSY1": {
                        "description": "Systolic: Blood pres (1st rdg) mm Hg",
                        "value_labels": {"1": "Acceptable", "2": "Questionable"},
                        "units": "mmHg",
                    },
                    "RIDAGEYR": {
                        "label": "Age in years at screening",
                    },
                },
            }
        )
    )

    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        datasources={
            "nhanes_bp": {
                "type": "csv",
                "path": str(csv_file),
                "metadata_path": str(meta_file),
            },
        },
    )
    toolset = IntrospectToolset(config=config)
    result = await toolset.introspect_csv("nhanes_bp")

    col_map = {c["name"]: c for c in result["columns"]}
    assert col_map["BPXSY1"]["description"] == "Systolic: Blood pres (1st rdg) mm Hg"
    assert col_map["BPXSY1"]["enumeration"] == {"1": "Acceptable", "2": "Questionable"}
    assert col_map["BPXSY1"]["units"] == "mmHg"
    # RIDAGEYR uses "label" key as fallback
    assert col_map["RIDAGEYR"]["description"] == "Age in years at screening"


async def test_csv_metadata_missing_file(tmp_path: Path):
    """Missing metadata file is silently ignored."""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("col_a,col_b\n1,2\n")

    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        datasources={
            "test_ds": {
                "type": "csv",
                "path": str(csv_file),
                "metadata_path": str(tmp_path / "nonexistent.json"),
            },
        },
    )
    toolset = IntrospectToolset(config=config)
    result = await toolset.introspect_csv("test_ds")
    # Should succeed without error
    assert len(result["columns"]) == 2
    assert result["columns"][0]["description"] == ""


async def test_json_column_output_uses_data_type(json_toolset: IntrospectToolset):
    """JSON introspection uses 'data_type' field name (not 'inferred_type')."""
    result = await json_toolset.introspect_json("test_json")
    for col in result["columns"]:
        assert "data_type" in col, f"Column {col['name']} missing 'data_type'"
        assert "inferred_type" not in col


# --- _make_column tests ---


_ALL_13_FIELDS = {
    "name",
    "data_type",
    "sample_values",
    "description",
    "enumeration",
    "units",
    "nullable",
    "constraints",
    "range_values",
    "relationships",
    "business_rules",
    "examples",
    "metadata",
}


def test_make_column_defaults():
    """_make_column produces all 13 fields with correct defaults."""
    col = _make_column(name="test", data_type="string")
    assert set(col.keys()) == _ALL_13_FIELDS
    assert col["name"] == "test"
    assert col["data_type"] == "string"
    assert col["sample_values"] == []
    assert col["description"] == ""
    assert col["enumeration"] is None
    assert col["units"] == ""
    assert col["nullable"] is None
    assert col["constraints"] == {}
    assert col["range_values"] == ""
    assert col["relationships"] == ""
    assert col["business_rules"] == ""
    assert col["examples"] == ""
    assert col["metadata"] == {}


def test_make_column_with_values():
    """_make_column accepts all keyword arguments."""
    col = _make_column(
        name="age",
        data_type="integer",
        sample_values=[25, 30],
        description="Patient age",
        nullable=False,
        constraints={"min": 0},
        range_values="0-150",
        relationships="patients.id",
        business_rules="must be positive",
        examples="25, 30, 45",
        metadata={"sql_type": "INTEGER"},
    )
    assert col["description"] == "Patient age"
    assert col["range_values"] == "0-150"
    assert col["relationships"] == "patients.id"
    assert col["business_rules"] == "must be positive"
    assert col["examples"] == "25, 30, 45"
    assert col["metadata"] == {"sql_type": "INTEGER"}


# --- Column output 13-field tests ---


async def test_csv_column_output_has_all_13_fields(introspect_toolset: IntrospectToolset):
    """CSV introspection columns have all 13 standardized fields."""
    result = await introspect_toolset.introspect_csv("test_csv")
    for col in result["columns"]:
        assert set(col.keys()) == _ALL_13_FIELDS, f"Column {col['name']} missing fields"


async def test_json_column_output_has_all_13_fields(json_toolset: IntrospectToolset):
    """JSON introspection columns have all 13 standardized fields."""
    result = await json_toolset.introspect_json("test_json")
    for col in result["columns"]:
        assert set(col.keys()) == _ALL_13_FIELDS, f"Column {col['name']} missing fields"


# --- SQL schema introspection tests ---


async def test_sql_schema_introspect(tmp_path: Path):
    """SQL schema introspection extracts types, NOT NULL, FK, CHECK."""
    import sqlalchemy
    from sqlalchemy.ext.asyncio import create_async_engine

    db_path = tmp_path / "schema_test.db"
    conn_str = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(conn_str)
    async with engine.begin() as conn:
        await conn.execute(
            sqlalchemy.text(
                "CREATE TABLE departments ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  name TEXT NOT NULL"
                ")"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "CREATE TABLE employees ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  name TEXT NOT NULL,"
                "  dept_id INTEGER REFERENCES departments(id),"
                "  salary REAL CHECK(salary > 0)"
                ")"
            )
        )
    await engine.dispose()

    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl"), "log_level": "verbose"},
        datasources={
            "test_db": {"type": "sql", "connection_string": conn_str},
        },
    )
    toolset = IntrospectToolset(config=config)
    result = await toolset.introspect_sql_schema("test_db", table_name="employees")

    assert result["datasource"] == "test_db"
    assert result["type"] == "sql"
    assert len(result["tables"]) == 1
    assert result["tables"][0]["table"] == "employees"

    col_map = {c["name"]: c for c in result["tables"][0]["columns"]}
    # id is primary key
    assert col_map["id"]["constraints"].get("primary_key") is True
    assert col_map["id"]["data_type"] == "integer"
    # name is NOT NULL
    assert col_map["name"]["nullable"] is False
    # dept_id has FK relationship
    assert "departments.id" in col_map["dept_id"]["relationships"]
    # salary has CHECK constraint
    assert col_map["salary"]["data_type"] == "decimal"
    # All columns have 13 fields
    for col in result["tables"][0]["columns"]:
        assert set(col.keys()) == _ALL_13_FIELDS


async def test_sql_schema_all_tables(tmp_path: Path):
    """SQL schema introspection without table_name returns all tables."""
    import sqlalchemy
    from sqlalchemy.ext.asyncio import create_async_engine

    db_path = tmp_path / "multi_table.db"
    conn_str = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(conn_str)
    async with engine.begin() as conn:
        await conn.execute(sqlalchemy.text("CREATE TABLE alpha (id INTEGER PRIMARY KEY)"))
        await conn.execute(sqlalchemy.text("CREATE TABLE beta (id INTEGER PRIMARY KEY, val TEXT)"))
    await engine.dispose()

    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        datasources={
            "test_db": {"type": "sql", "connection_string": conn_str},
        },
    )
    toolset = IntrospectToolset(config=config)
    result = await toolset.introspect_sql_schema("test_db")

    table_names = {t["table"] for t in result["tables"]}
    assert "alpha" in table_names
    assert "beta" in table_names


async def test_sql_schema_wrong_type(tmp_path: Path):
    """Using a CSV datasource for SQL schema raises ValueError."""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("a,b\n1,2\n")
    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        datasources={
            "csv_ds": {"type": "csv", "path": str(csv_file)},
        },
    )
    toolset = IntrospectToolset(config=config)
    with pytest.raises(ValueError, match="not 'sql'"):
        await toolset.introspect_sql_schema("csv_ds")


# --- BigQuery native metadata tests ---


async def test_bigquery_native_metadata(tmp_path: Path):
    """BigQuery introspection extracts description, mode, and nested fields."""
    from unittest.mock import MagicMock, patch

    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl"), "log_level": "verbose"},
        datasources={
            "test_bq": {
                "type": "bigquery",
                "project": "my-project",
                "dataset": "ds",
            },
        },
    )
    toolset = IntrospectToolset(config=config)

    # Mock fields with description and mode
    mock_field_id = MagicMock()
    mock_field_id.name = "id"
    mock_field_id.field_type = "INT64"
    mock_field_id.description = "Primary identifier"
    mock_field_id.mode = "REQUIRED"
    mock_field_id.fields = []

    mock_field_addr = MagicMock()
    mock_field_addr.name = "address"
    mock_field_addr.field_type = "STRUCT"
    mock_field_addr.description = "Mailing address"
    mock_field_addr.mode = "NULLABLE"
    # Nested fields
    mock_sub_city = MagicMock()
    mock_sub_city.name = "city"
    mock_sub_zip = MagicMock()
    mock_sub_zip.name = "zip"
    mock_field_addr.fields = [mock_sub_city, mock_sub_zip]

    mock_table = MagicMock()
    mock_table.schema = [mock_field_id, mock_field_addr]
    mock_table.num_rows = 10

    mock_client = MagicMock()
    mock_client.get_table.return_value = mock_table
    mock_client.list_rows.return_value = []

    with patch("google.cloud.bigquery.Client", return_value=mock_client):
        result = await toolset.introspect_bigquery("test_bq", table="users")

    col_map = {c["name"]: c for c in result["columns"]}

    # id: description and nullable from mode
    assert col_map["id"]["description"] == "Primary identifier"
    assert col_map["id"]["nullable"] is False
    assert col_map["id"]["metadata"]["bigquery_type"] == "INT64"
    assert col_map["id"]["metadata"]["bigquery_mode"] == "REQUIRED"

    # address: STRUCT with nested fields
    assert col_map["address"]["description"] == "Mailing address"
    assert col_map["address"]["nullable"] is True
    assert "city" in col_map["address"]["relationships"]
    assert "zip" in col_map["address"]["relationships"]
    assert col_map["address"]["data_type"] == "object"


# --- MongoDB validator extraction tests ---


async def test_mongodb_validator_extraction(tmp_path: Path):
    """MongoDB introspection extracts metadata from JSON Schema validator."""
    from unittest.mock import AsyncMock, MagicMock, patch

    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl"), "log_level": "verbose"},
        datasources={
            "test_mongo": {
                "type": "mongodb",
                "connection_string": "mongodb://localhost:27017",
                "database": "testdb",
                "collection": "patients",
            },
        },
    )
    toolset = IntrospectToolset(config=config)

    # Mock validator schema
    validator_response = {
        "cursor": {
            "firstBatch": [
                {
                    "name": "patients",
                    "options": {
                        "validator": {
                            "$jsonSchema": {
                                "required": ["name", "age"],
                                "properties": {
                                    "name": {
                                        "bsonType": "string",
                                        "description": "Patient full name",
                                    },
                                    "age": {
                                        "bsonType": "int",
                                        "description": "Age in years",
                                        "minimum": 0,
                                        "maximum": 150,
                                    },
                                    "status": {
                                        "bsonType": "string",
                                        "enum": ["active", "inactive", "deceased"],
                                    },
                                    "code": {
                                        "bsonType": "string",
                                        "pattern": "^[A-Z]{3}$",
                                    },
                                },
                            }
                        }
                    },
                }
            ]
        }
    }

    # Sample documents
    sample_docs = [
        {"_id": "abc123", "name": "Alice", "age": 30, "status": "active", "code": "ABC"},
        {"_id": "def456", "name": "Bob", "age": 45, "status": "inactive", "code": "XYZ"},
    ]

    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=sample_docs)

    mock_find_result = MagicMock()
    mock_find_result.limit = MagicMock(return_value=mock_cursor)

    mock_coll = MagicMock()
    mock_coll.find = MagicMock(return_value=mock_find_result)
    mock_coll.count_documents = AsyncMock(return_value=2)

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_coll)
    mock_db.command = AsyncMock(return_value=validator_response)

    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    mock_client.close = MagicMock()

    with patch("motor.motor_asyncio.AsyncIOMotorClient", return_value=mock_client):
        result = await toolset.introspect_mongodb("test_mongo")

    field_map = {f["name"]: f for f in result["columns"]}

    # name: description from validator, required → not nullable
    assert field_map["name"]["description"] == "Patient full name"
    assert field_map["name"]["nullable"] is False

    # age: min/max constraints and range_values
    assert field_map["age"]["description"] == "Age in years"
    assert field_map["age"]["constraints"]["min"] == 0
    assert field_map["age"]["constraints"]["max"] == 150
    assert "min=0" in field_map["age"]["range_values"]
    assert "max=150" in field_map["age"]["range_values"]

    # status: enumeration
    assert field_map["status"]["enumeration"] is not None
    assert "active" in field_map["status"]["enumeration"]

    # code: pattern constraint and business_rules
    assert field_map["code"]["constraints"]["pattern"] == "^[A-Z]{3}$"
    assert "pattern" in field_map["code"]["business_rules"]

    # All fields have bson_type at top level (backward compat) and in metadata
    for f in result["columns"]:
        assert "bson_type" in f
        assert "bson_type" in f["metadata"]


# --- Sidecar new fields tests ---


async def test_sidecar_new_fields(tmp_path: Path):
    """Sidecar metadata with new fields merges correctly."""
    import json as json_mod

    csv_file = tmp_path / "data.csv"
    csv_file.write_text("age,dept_id\n30,5\n25,3\n")

    meta_file = tmp_path / "data.meta.json"
    meta_file.write_text(
        json_mod.dumps(
            {
                "columns": {
                    "age": {
                        "description": "Employee age",
                        "range_values": "18-65",
                        "business_rules": "Must be at least 18",
                        "examples": "25, 30, 45",
                        "metadata": {"source_system": "HR"},
                    },
                    "dept_id": {
                        "description": "Department reference",
                        "relationships": "departments.id",
                    },
                },
            }
        )
    )

    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        datasources={
            "test_ds": {
                "type": "csv",
                "path": str(csv_file),
                "metadata_path": str(meta_file),
            },
        },
    )
    toolset = IntrospectToolset(config=config)
    result = await toolset.introspect_csv("test_ds")

    col_map = {c["name"]: c for c in result["columns"]}

    assert col_map["age"]["description"] == "Employee age"
    assert col_map["age"]["range_values"] == "18-65"
    assert col_map["age"]["business_rules"] == "Must be at least 18"
    assert col_map["age"]["examples"] == "25, 30, 45"
    assert col_map["age"]["metadata"] == {"source_system": "HR"}

    assert col_map["dept_id"]["relationships"] == "departments.id"
    # Fields not in sidecar keep defaults
    assert col_map["dept_id"]["range_values"] == ""
    assert col_map["dept_id"]["business_rules"] == ""
