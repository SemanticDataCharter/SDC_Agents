"""Security tests — scope isolation and access control.

Verifies that each toolset exposes only its own tools, SQL rejects
write operations, and datasource access requires configuration.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.catalog import CatalogToolset
from sdc_agents.toolsets.introspect import IntrospectToolset
from sdc_agents.toolsets.mapping import MappingToolset


@pytest.fixture
def security_config(tmp_path: Path) -> SDCAgentsConfig:
    return SDCAgentsConfig(
        sdcstudio={"base_url": "https://test.local"},
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl"), "log_level": "verbose"},
        datasources={
            "allowed_db": {
                "type": "sql",
                "connection_string": "sqlite+aiosqlite://",
            },
        },
    )


# --- Tool scope isolation ---


async def test_catalog_only_exposes_catalog_tools(security_config):
    """Catalog toolset has exactly 5 catalog-scoped tools."""
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=[]))
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = CatalogToolset(config=security_config, http_client=client)
    tools = await toolset.get_tools()
    names = {t.name for t in tools}
    assert names == {
        "catalog_list_schemas",
        "catalog_get_schema",
        "catalog_download_schema_rdf",
        "catalog_download_skeleton",
        "catalog_download_ontologies",
    }
    # No introspect or mapping tools
    assert not names & {"introspect_sql", "introspect_csv", "mapping_suggest"}


async def test_introspect_only_exposes_introspect_tools(security_config):
    """Introspect toolset has exactly 2 introspect-scoped tools."""
    toolset = IntrospectToolset(config=security_config)
    tools = await toolset.get_tools()
    names = {t.name for t in tools}
    assert names == {"introspect_sql", "introspect_csv"}
    # No catalog or mapping tools
    assert not names & {"catalog_list_schemas", "mapping_suggest"}


async def test_mapping_only_exposes_mapping_tools(security_config):
    """Mapping toolset has exactly 3 mapping-scoped tools."""
    toolset = MappingToolset(config=security_config)
    tools = await toolset.get_tools()
    names = {t.name for t in tools}
    assert names == {"mapping_suggest", "mapping_confirm", "mapping_list"}
    # No catalog or introspect tools
    assert not names & {"catalog_list_schemas", "introspect_sql"}


# --- SQL write rejection ---


@pytest.mark.parametrize(
    "query",
    [
        "DROP TABLE users",
        "drop table users",
        "INSERT INTO t VALUES (1)",
        "  insert into t values (1)",
        "UPDATE t SET x = 1",
        "DELETE FROM t WHERE id = 1",
        "ALTER TABLE t ADD COLUMN x INT",
        "CREATE TABLE evil (id INT)",
        "TRUNCATE TABLE t",
    ],
)
async def test_sql_rejects_all_write_operations(security_config, query):
    """All known write SQL operations are rejected."""
    toolset = IntrospectToolset(config=security_config)
    with pytest.raises(PermissionError, match="Write operations are not allowed"):
        await toolset.introspect_sql("allowed_db", query)


async def test_sql_allows_select(security_config, tmp_path):
    """SELECT queries are permitted."""
    import sqlalchemy
    from sqlalchemy.ext.asyncio import create_async_engine

    db_path = tmp_path / "sec_test.db"
    conn_str = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(conn_str)
    async with engine.begin() as conn:
        await conn.execute(sqlalchemy.text("CREATE TABLE t (id INTEGER)"))
        await conn.execute(sqlalchemy.text("INSERT INTO t VALUES (1)"))
    await engine.dispose()

    security_config.datasources["allowed_db"].connection_string = conn_str
    toolset = IntrospectToolset(config=security_config)
    rows = await toolset.introspect_sql("allowed_db", "SELECT * FROM t")
    assert len(rows) == 1


# --- Datasource name enforcement ---


async def test_unknown_datasource_raises_keyerror(security_config):
    """Accessing an unconfigured datasource raises KeyError."""
    toolset = IntrospectToolset(config=security_config)
    with pytest.raises(KeyError, match="Unknown datasource 'hacker_db'"):
        await toolset.introspect_sql("hacker_db", "SELECT 1")


async def test_unknown_csv_datasource_raises_keyerror(security_config):
    """Accessing an unconfigured CSV datasource raises KeyError."""
    toolset = IntrospectToolset(config=security_config)
    with pytest.raises(KeyError, match="Unknown datasource"):
        await toolset.introspect_csv("unknown_csv")


# --- No cross-scope tool leakage ---


async def test_no_tool_name_overlap():
    """Tool names across all toolsets are disjoint."""
    config = SDCAgentsConfig(
        sdcstudio={"base_url": "https://test.local"},
    )
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=[]))
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")

    catalog = CatalogToolset(config=config, http_client=client)
    introspect = IntrospectToolset(config=config)
    mapping = MappingToolset(config=config)

    cat_names = {t.name for t in await catalog.get_tools()}
    int_names = {t.name for t in await introspect.get_tools()}
    map_names = {t.name for t in await mapping.get_tools()}

    # All pairwise intersections are empty
    assert not cat_names & int_names, "Catalog and Introspect tools overlap"
    assert not cat_names & map_names, "Catalog and Mapping tools overlap"
    assert not int_names & map_names, "Introspect and Mapping tools overlap"
