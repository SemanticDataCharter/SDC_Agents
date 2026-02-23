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
from sdc_agents.toolsets.distribution import DistributionToolset
from sdc_agents.toolsets.generator import GeneratorToolset
from sdc_agents.toolsets.introspect import IntrospectToolset
from sdc_agents.toolsets.mapping import MappingToolset
from sdc_agents.toolsets.validation import ValidationToolset


@pytest.fixture
def security_config(tmp_path: Path) -> SDCAgentsConfig:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return SDCAgentsConfig(
        sdcstudio={
            "base_url": "https://test.local",
            "api_key": "test-secret-key",
        },
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl"), "log_level": "verbose"},
        output={"directory": str(output_dir)},
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
    """Introspect toolset has exactly 4 introspect-scoped tools."""
    toolset = IntrospectToolset(config=security_config)
    tools = await toolset.get_tools()
    names = {t.name for t in tools}
    assert names == {
        "introspect_sql",
        "introspect_csv",
        "introspect_json",
        "introspect_mongodb",
    }
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


async def test_generator_only_exposes_generator_tools(security_config):
    """Generator toolset has exactly 3 generator-scoped tools."""
    toolset = GeneratorToolset(config=security_config)
    tools = await toolset.get_tools()
    names = {t.name for t in tools}
    assert names == {"generate_instance", "generate_batch", "generate_preview"}
    # No other toolset tools
    assert not names & {"catalog_list_schemas", "introspect_sql", "mapping_suggest"}


async def test_validation_only_exposes_validation_tools(security_config):
    """Validation toolset has exactly 3 validation-scoped tools."""
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = ValidationToolset(config=security_config, http_client=client)
    tools = await toolset.get_tools()
    names = {t.name for t in tools}
    assert names == {"validate_instance", "sign_instance", "validate_batch"}
    # No other toolset tools
    assert not names & {"catalog_list_schemas", "introspect_sql", "generate_instance"}


async def test_distribution_only_exposes_distribution_tools(security_config):
    """Distribution toolset has exactly 5 distribution-scoped tools."""
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = DistributionToolset(config=security_config, http_client=client)
    tools = await toolset.get_tools()
    names = {t.name for t in tools}
    assert names == {
        "inspect_package",
        "list_destinations",
        "distribute_package",
        "distribute_batch",
        "bootstrap_triplestore",
    }
    # No other toolset tools
    assert not names & {
        "catalog_list_schemas",
        "introspect_sql",
        "generate_instance",
        "validate_instance",
    }


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
    """Tool names across all 6 toolsets are disjoint."""
    config = SDCAgentsConfig(
        sdcstudio={"base_url": "https://test.local"},
    )
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=[]))
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")

    catalog = CatalogToolset(config=config, http_client=client)
    introspect = IntrospectToolset(config=config)
    mapping = MappingToolset(config=config)
    generator = GeneratorToolset(config=config)
    validation = ValidationToolset(config=config, http_client=client)
    distribution = DistributionToolset(config=config, http_client=client)

    all_toolsets = {
        "catalog": {t.name for t in await catalog.get_tools()},
        "introspect": {t.name for t in await introspect.get_tools()},
        "mapping": {t.name for t in await mapping.get_tools()},
        "generator": {t.name for t in await generator.get_tools()},
        "validation": {t.name for t in await validation.get_tools()},
        "distribution": {t.name for t in await distribution.get_tools()},
    }

    # Verify expected counts (5+4+3+3+3+5 = 23 total)
    assert len(all_toolsets["catalog"]) == 5
    assert len(all_toolsets["introspect"]) == 4
    assert len(all_toolsets["mapping"]) == 3
    assert len(all_toolsets["generator"]) == 3
    assert len(all_toolsets["validation"]) == 3
    assert len(all_toolsets["distribution"]) == 5

    # All pairwise intersections are empty
    names = list(all_toolsets.keys())
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            overlap = all_toolsets[a] & all_toolsets[b]
            assert not overlap, f"{a} and {b} tools overlap: {overlap}"


# --- Validation path confinement ---


async def test_validation_rejects_etc_passwd(security_config):
    """Validation rejects /etc/passwd."""
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = ValidationToolset(config=security_config, http_client=client)

    with pytest.raises(PermissionError, match="outside the output directory"):
        await toolset.validate_instance(xml_path="/etc/passwd")


async def test_validation_rejects_tmp_evil(security_config):
    """Validation rejects /tmp/evil.xml."""
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = ValidationToolset(config=security_config, http_client=client)

    with pytest.raises(PermissionError, match="outside the output directory"):
        await toolset.validate_instance(xml_path="/tmp/evil.xml")


async def test_validation_rejects_relative_traversal(security_config):
    """Validation rejects relative path traversal."""
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = ValidationToolset(config=security_config, http_client=client)

    output_dir = security_config.output.directory
    traversal = f"{output_dir}/../../../etc/passwd"
    with pytest.raises(PermissionError, match="outside the output directory"):
        await toolset.validate_instance(xml_path=traversal)


# --- Distribution path confinement ---


async def test_distribution_rejects_outside_path(security_config):
    """Distribution rejects package paths outside output directory."""
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = DistributionToolset(config=security_config, http_client=client)

    with pytest.raises(PermissionError, match="outside the output directory"):
        await toolset.inspect_package("/etc/passwd")


async def test_distribution_rejects_traversal(security_config):
    """Distribution rejects path traversal attacks."""
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = DistributionToolset(config=security_config, http_client=client)

    output_dir = security_config.output.directory
    traversal = f"{output_dir}/../../../etc/passwd"
    with pytest.raises(PermissionError, match="outside the output directory"):
        await toolset.distribute_package(traversal)


# --- Generator output directory confinement ---


async def test_generator_writes_to_output_dir(security_config):
    """Generator writes files only to the configured output directory."""
    toolset = GeneratorToolset(config=security_config)
    output_dir = Path(security_config.output.directory).resolve()
    assert toolset._output_dir.resolve() == output_dir


# --- VaaS token redaction in audit ---


async def test_destination_credentials_redacted_in_audit(security_config):
    """Destination auth credentials are redacted in audit logs."""
    from sdc_agents.common.audit import AuditLogger

    audit = AuditLogger(security_config.audit.path, security_config.audit.log_level)

    import time

    audit.log(
        agent="distribution",
        tool="distribute_package",
        inputs={"package_path": "/test.pkg.zip", "auth_token": "secret-cred"},
        outputs={"status": "ok"},
        start_time=time.monotonic(),
    )

    log_content = Path(security_config.audit.path).read_text()
    record = json.loads(log_content.strip().split("\n")[-1])
    assert record["inputs"]["auth_token"] == "***REDACTED***"
    assert "secret-cred" not in log_content


async def test_vaas_token_redacted_in_audit(security_config):
    """VaaS API token is redacted in audit log entries."""
    from sdc_agents.common.audit import AuditLogger

    audit = AuditLogger(security_config.audit.path, security_config.audit.log_level)

    # Simulate audit log with api_key in inputs
    import time

    audit.log(
        agent="validation",
        tool="validate_instance",
        inputs={"xml_path": "/test.xml", "api_key": "test-secret-key"},
        outputs={"valid": True},
        start_time=time.monotonic(),
    )

    log_content = Path(security_config.audit.path).read_text()
    record = json.loads(log_content.strip())
    assert record["inputs"]["api_key"] == "***REDACTED***"
    assert "test-secret-key" not in log_content
