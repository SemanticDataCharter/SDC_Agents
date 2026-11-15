"""Follow-ups from the 4.5.1 assessment's evidence bundle (pip-audit, bandit).

- opentelemetry-api below 1.45.1 has CVE-2026-114603; the floor is enforced.
- Four ``except Exception: pass`` blocks (bandit B110) hid failures. Each
  now reports what it couldn't read, and the SQL/MongoDB ones catch only
  the errors they expect.
"""

from __future__ import annotations

import importlib.metadata as md
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import sqlalchemy
from packaging.version import Version
from pymongo.errors import OperationFailure
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.ext.asyncio import create_async_engine

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.distribution import DistributionToolset
from sdc_agents.toolsets.introspect import IntrospectToolset

# --- dependency floor ---------------------------------------------------------


def test_opentelemetry_api_is_at_or_above_the_fixed_version():
    assert Version(md.version("opentelemetry-api")) >= Version("1.45.1")


def test_pyproject_declares_the_floor():
    import tomllib

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    deps = tomllib.loads(pyproject.read_text())["project"]["dependencies"]
    assert "opentelemetry-api>=1.45.1" in deps
    assert "google-adk>=2.14.0" in deps


# Floors for runtime dependencies with advisories (pip-audit, 2026-11-15).
RUNTIME_FLOORS = {
    "pymongo": "4.18.3",
    "urllib3": "2.8.0",
    "certifi": "2026.10.18",
    "dnspython": "2.9.2",
    "joserfc": "1.7.6",
    "pyasn1": "0.6.5",
}


@pytest.mark.parametrize("package,floor", sorted(RUNTIME_FLOORS.items()))
def test_runtime_dependency_floor(package, floor):
    import tomllib

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    deps = tomllib.loads(pyproject.read_text())["project"]["dependencies"]
    assert f"{package}>={floor}" in deps
    assert Version(md.version(package)) >= Version(floor)


# --- introspect_sql_schema ----------------------------------------------------


@pytest.fixture
async def sql_toolset(tmp_path: Path) -> IntrospectToolset:
    db = tmp_path / "s.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    async with engine.begin() as conn:
        await conn.execute(sqlalchemy.text("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)"))
    await engine.dispose()
    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        datasources={"s": {"type": "sql", "connection_string": f"sqlite+aiosqlite:///{db}"}},
    )
    return IntrospectToolset(config=config)


async def test_schema_reports_no_warnings_when_everything_reads(sql_toolset):
    result = await sql_toolset.introspect_sql_schema("s", "t")
    assert result["warnings"] == []


async def test_unsupported_catalog_features_are_reported_not_hidden(sql_toolset, monkeypatch):
    def not_implemented(self, *a, **k):
        raise NotImplementedError

    monkeypatch.setattr(Inspector, "get_foreign_keys", not_implemented)
    monkeypatch.setattr(Inspector, "get_check_constraints", not_implemented)
    monkeypatch.setattr(Inspector, "get_pk_constraint", not_implemented)

    result = await sql_toolset.introspect_sql_schema("s", "t")
    assert [c["name"] for c in result["columns"]] == ["id", "v"]  # still introspected
    assert result["warnings"] == [
        "t: primary key unavailable (NotImplementedError)",
        "t: foreign keys unavailable (NotImplementedError)",
        "t: check constraints unavailable (NotImplementedError)",
    ]


async def test_unexpected_errors_are_not_swallowed(sql_toolset, monkeypatch):
    """Only 'feature unavailable' errors are tolerated; a bug still surfaces."""

    def broken(self, *a, **k):
        raise KeyError("bug")

    monkeypatch.setattr(Inspector, "get_foreign_keys", broken)
    with pytest.raises(KeyError):
        await sql_toolset.introspect_sql_schema("s", "t")


# --- introspect_mongodb -------------------------------------------------------


def _mongo_client(command_side_effect):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[{"_id": "a", "name": "x"}])
    find = MagicMock()
    find.limit = MagicMock(return_value=cursor)
    coll = MagicMock()
    coll.find = MagicMock(return_value=find)
    coll.count_documents = AsyncMock(return_value=1)
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=coll)
    db.command = AsyncMock(side_effect=command_side_effect)
    client = MagicMock()
    client.__getitem__ = MagicMock(return_value=db)
    return client


@pytest.fixture
def mongo_toolset(tmp_path: Path) -> IntrospectToolset:
    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        datasources={
            "m": {
                "type": "mongodb",
                "connection_string": "mongodb://localhost:27017",
                "database": "d",
                "collection": "c",
            }
        },
    )
    return IntrospectToolset(config=config)


async def test_mongo_missing_privilege_is_reported(mongo_toolset):
    client = _mongo_client(OperationFailure("not authorized on d to execute command"))
    with patch("motor.motor_asyncio.AsyncIOMotorClient", return_value=client):
        result = await mongo_toolset.introspect_mongodb("m")
    assert {c["name"] for c in result["columns"]} == {"_id", "name"}
    assert result["warnings"] == ["collection validator not read (OperationFailure)"]


async def test_mongo_unexpected_error_surfaces(mongo_toolset):
    client = _mongo_client(KeyError("bug"))
    with patch("motor.motor_asyncio.AsyncIOMotorClient", return_value=client):
        with pytest.raises(KeyError):
            await mongo_toolset.introspect_mongodb("m")


# --- list_destinations --------------------------------------------------------


async def test_unreachable_destination_says_why_without_echoing_secrets(tmp_path: Path):
    secret = "Bearer s3cr3t-token"

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url} with {secret}")

    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        output={"directory": str(tmp_path / "out")},
        destinations={
            "ts": {
                "type": "fuseki",
                "endpoint": "http://user:pw@fuseki.local/ds",
                "auth": secret,
            }
        },
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    result = await DistributionToolset(config=config, http_client=client).list_destinations()
    (entry,) = result
    assert entry["status"] == "unreachable"
    assert entry["error"] == "ConnectError"
    assert secret not in str(result)
