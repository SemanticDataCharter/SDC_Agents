"""F-C: source values never reach the cache or audit log shared with network agents.

The introspection cache and the default audit log sit under the same cache
root that AssemblyToolset (which makes network calls) reads. Only structure
may be written there.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.assembly import AssemblyToolset
from sdc_agents.toolsets.introspect import IntrospectToolset

SSN = "111-22-3333"
NAME = "Zebulon Quartermaine"


def _all_cache_text(root: Path) -> str:
    return "\n".join(p.read_text(errors="replace") for p in root.rglob("*") if p.is_file())


@pytest.fixture
def config(tmp_path: Path) -> SDCAgentsConfig:
    csv_path = tmp_path / "customers.csv"
    csv_path.write_text(f"id,name,ssn\n1,{NAME},{SSN}\n2,Ann Other,222-33-4444\n")
    json_path = tmp_path / "customers.json"
    json_path.write_text(json.dumps([{"id": 1, "name": NAME, "ssn": SSN}]))
    root = tmp_path / ".sdc-cache"
    return SDCAgentsConfig(
        sdcstudio={"base_url": "https://test.local", "api_key": "k"},
        cache={"root": str(root)},
        # Default layout: the audit log inside the cache root, at the most
        # revealing level.
        audit={"path": str(root / "audit.jsonl"), "log_level": "verbose"},
        datasources={
            "cust_csv": {"type": "csv", "path": str(csv_path)},
            "cust_json": {"type": "json", "path": str(json_path)},
            "cust_sql": {
                "type": "sql",
                "connection_string": f"sqlite+aiosqlite:///{tmp_path / 'c.db'}",
            },
        },
    )


async def test_csv_values_stay_out_of_the_shared_cache(config: SDCAgentsConfig):
    toolset = IntrospectToolset(config=config)
    result = await toolset.introspect_csv("cust_csv")

    # The agent that asked still gets samples to reason with.
    ssn_col = next(c for c in result["columns"] if c["name"] == "ssn")
    assert SSN in ssn_col["sample_values"]

    root = Path(config.cache.root)
    assert SSN not in _all_cache_text(root)
    assert NAME not in _all_cache_text(root)

    # Structure is still there for the downstream toolsets.
    cached = json.loads((root / "introspections" / "cust_csv.json").read_text())
    assert [c["name"] for c in cached["columns"]] == ["id", "name", "ssn"]
    assert cached["row_count"] == 2
    assert all(c["sample_values"] == [] for c in cached["columns"])


async def test_json_values_stay_out_of_the_shared_cache(config: SDCAgentsConfig):
    toolset = IntrospectToolset(config=config)
    result = await toolset.introspect_json("cust_json")
    assert any(SSN in c["sample_values"] for c in result["columns"])
    assert SSN not in _all_cache_text(Path(config.cache.root))


async def test_sql_rows_stay_out_of_the_audit_log(config: SDCAgentsConfig):
    engine = create_async_engine(config.datasources["cust_sql"].connection_string)
    async with engine.begin() as conn:
        await conn.execute(sqlalchemy.text("CREATE TABLE c (name TEXT, ssn TEXT)"))
        await conn.execute(sqlalchemy.text(f"INSERT INTO c VALUES ('{NAME}', '{SSN}')"))
    await engine.dispose()

    toolset = IntrospectToolset(config=config)
    rows = await toolset.introspect_sql("cust_sql", "SELECT name, ssn FROM c")
    assert rows == [{"name": NAME, "ssn": SSN}]

    audit = Path(config.audit.path).read_text()
    assert SSN not in audit and NAME not in audit
    record = json.loads(audit.strip().splitlines()[-1])
    assert record["outputs"] == {"row_count": 1, "columns": ["name", "ssn"]}


async def test_network_agent_sees_only_structure(config: SDCAgentsConfig):
    """The assessment's channel: assembly reads the same cache root."""
    await IntrospectToolset(config=config).introspect_csv("cust_csv")
    assembly = AssemblyToolset(config=config)
    assert str(assembly._cache.root) == config.cache.root
    seen = assembly._cache.introspection_path("cust_csv").read_text()
    assert SSN not in seen and NAME not in seen
