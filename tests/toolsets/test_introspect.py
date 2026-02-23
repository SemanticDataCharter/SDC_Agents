"""Tests for the Introspect Toolset."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.introspect import IntrospectToolset, _infer_type


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
        await conn.execute(sqlalchemy.text(
            "CREATE TABLE test_table (id INTEGER, name TEXT)"
        ))
        await conn.execute(sqlalchemy.text(
            "INSERT INTO test_table VALUES (1, 'Alice'), (2, 'Bob')"
        ))
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
        await conn.execute(sqlalchemy.text(
            "CREATE TABLE lab_results (id INTEGER, test_name TEXT, value REAL)"
        ))
        await conn.execute(sqlalchemy.text(
            "INSERT INTO lab_results VALUES (1, 'CBC', 98.6), (2, 'BMP', 120.5)"
        ))
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
        await introspect_toolset.introspect_sql(
            "test_db", "INSERT INTO t VALUES (1)"
        )

    with pytest.raises(PermissionError):
        await introspect_toolset.introspect_sql(
            "test_db", "UPDATE t SET x = 1"
        )

    with pytest.raises(PermissionError):
        await introspect_toolset.introspect_sql(
            "test_db", "DELETE FROM t WHERE id = 1"
        )


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
    assert col_map["test_id"]["inferred_type"] == "integer"
    assert col_map["patient_email"]["inferred_type"] == "email"
    assert col_map["is_critical"]["inferred_type"] == "boolean"
    assert col_map["collected_date"]["inferred_type"] == "date"
    assert col_map["collected_time"]["inferred_type"] == "time"
    assert col_map["request_uuid"]["inferred_type"] == "UUID"
    assert col_map["result"]["inferred_type"] == "decimal"


async def test_csv_wrong_datasource_type(introspect_toolset: IntrospectToolset):
    """Using a SQL datasource for CSV raises ValueError."""
    with pytest.raises(ValueError, match="not 'csv'"):
        await introspect_toolset.introspect_csv("test_db")


async def test_get_tools_returns_four(introspect_toolset: IntrospectToolset):
    """get_tools returns exactly 4 tools."""
    tools = await introspect_toolset.get_tools()
    assert len(tools) == 4
    names = {t.name for t in tools}
    assert names == {"introspect_sql", "introspect_csv", "introspect_json", "introspect_mongodb"}


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
    assert col_map["test_id"]["inferred_type"] == "integer"
    assert col_map["patient_email"]["inferred_type"] == "email"
    assert col_map["collected_date"]["inferred_type"] == "date"
    assert col_map["collected_time"]["inferred_type"] == "time"
    assert col_map["request_uuid"]["inferred_type"] == "UUID"


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
    json_file.write_text(json_mod.dumps([
        {"name": "Alice", "address": {"city": "NYC", "zip": "10001"}},
        {"name": "Bob", "address": {"city": "LA", "zip": "90001"}},
    ]))

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
    assert col_map["address"]["inferred_type"] == "object"


async def test_json_arrays(tmp_path: Path):
    """JSON with array values reports 'array' type."""
    import json as json_mod

    json_file = tmp_path / "arrays.json"
    json_file.write_text(json_mod.dumps([
        {"name": "Alice", "scores": [90, 85, 92]},
        {"name": "Bob", "scores": [78, 88]},
    ]))

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
    assert col_map["scores"]["inferred_type"] == "array"


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
