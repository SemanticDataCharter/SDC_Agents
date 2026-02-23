"""Tests for Distribution Toolset — package inspection, delivery, and bootstrap."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.config import SDCAgentsConfig
from tests.fixtures.distribution_fixtures import (
    make_destination_configs,
    make_manifest,
    make_package_zip,
)


@pytest.fixture
def dist_config(tmp_path: Path) -> SDCAgentsConfig:
    """Config with destinations and tmpdir-based output."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    destinations = make_destination_configs()
    # Override archive path to use tmp dir
    destinations["archive"]["path"] = str(tmp_path / "archive" / "{ct_id}" / "{instance_id}")
    return SDCAgentsConfig(
        sdcstudio={"base_url": "https://test.local"},
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl"), "log_level": "verbose"},
        output={"directory": str(output_dir)},
        destinations=destinations,
    )


@pytest.fixture
def sample_package(dist_config: SDCAgentsConfig) -> Path:
    """Write a sample .pkg.zip to the output directory."""
    output_dir = Path(dist_config.output.directory)
    pkg_path = output_dir / "clxyz123abc_inst001.pkg.zip"
    pkg_path.write_bytes(make_package_zip())
    return pkg_path


def _mock_transport() -> httpx.MockTransport:
    """Transport that returns 200 OK for all requests."""

    def handler(request: httpx.Request) -> httpx.Response:
        # SPARQL ASK query response — graph does not exist
        if b"ASK WHERE" in (request.content or b""):
            return httpx.Response(200, json={"boolean": False})
        # Neo4j transactional endpoint
        if "/tx/commit" in str(request.url):
            return httpx.Response(200, json={"results": [], "errors": []})
        # Default: 200 OK
        return httpx.Response(200, json={"status": "ok"})

    return httpx.MockTransport(handler)


def _unreachable_transport() -> httpx.MockTransport:
    """Transport that simulates unreachable destinations."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    return httpx.MockTransport(handler)


# --- inspect_package ---


async def test_inspect_package_parses_manifest(dist_config, sample_package):
    """inspect_package reads manifest and reports artifacts with sizes."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    result = await toolset.inspect_package(str(sample_package))
    assert result["ct_id"] == "clxyz123abc"
    assert result["instance_id"] == "inst001"
    assert len(result["artifacts"]) == 5
    # All artifacts have non-zero size
    for art in result["artifacts"]:
        assert art["size_bytes"] > 0
        assert "type" in art
        assert "filename" in art


async def test_inspect_package_returns_manifest(dist_config, sample_package):
    """inspect_package returns the full manifest dict."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    result = await toolset.inspect_package(str(sample_package))
    assert "manifest" in result
    assert result["manifest"]["ct_id"] == "clxyz123abc"
    assert len(result["manifest"]["artifacts"]) == 5


# --- list_destinations ---


async def test_list_destinations_reachable(dist_config):
    """list_destinations reports reachable status for mock endpoints."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    result = await toolset.list_destinations()
    assert len(result) == 5
    names = {d["name"] for d in result}
    assert names == {"triplestore", "graph_database", "document_store", "archive", "linked_data"}

    # HTTP destinations are reachable
    for d in result:
        if d["type"] != "filesystem":
            assert d["status"] == "reachable", f"{d['name']} should be reachable"


async def test_list_destinations_unreachable(dist_config):
    """list_destinations reports unreachable status for failing endpoints."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    client = httpx.AsyncClient(transport=_unreachable_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    result = await toolset.list_destinations()
    for d in result:
        if d["type"] != "filesystem":
            assert d["status"] == "unreachable", f"{d['name']} should be unreachable"


# --- distribute_package ---


async def test_distribute_package_delivers_all(dist_config, sample_package):
    """distribute_package delivers artifacts to all configured destinations."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    result = await toolset.distribute_package(str(sample_package))
    assert result["ct_id"] == "clxyz123abc"
    assert result["artifacts_distributed"] == 5
    assert len(result["results"]) == 5
    for r in result["results"]:
        assert r["status"] == "delivered"


async def test_distribute_package_skips_unconfigured_destination(dist_config, sample_package):
    """distribute_package skips artifacts with unconfigured destinations."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    # Remove triplestore from config
    del dist_config.destinations["triplestore"]

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    result = await toolset.distribute_package(str(sample_package))
    # 4 delivered, 1 skipped
    assert result["artifacts_distributed"] == 4
    skipped = [r for r in result["results"] if r["status"] == "skipped"]
    assert len(skipped) == 1
    assert skipped[0]["destination"] == "triplestore"


async def test_distribute_package_filesystem(dist_config, sample_package):
    """distribute_package writes artifacts to filesystem destinations."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    await toolset.distribute_package(str(sample_package))

    # Check filesystem archive destination wrote the file
    archive_base = Path(dist_config.destinations["archive"].path
                        .replace("{ct_id}", "clxyz123abc")
                        .replace("{instance_id}", "inst001"))
    assert (archive_base / "instance.xml").exists()


async def test_distribute_package_per_artifact_failure_isolation(dist_config, sample_package):
    """If one destination fails, other artifacts still get delivered."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    call_count = {"n": 0}

    def failing_handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        # Fail on Neo4j endpoint
        if "/tx/commit" in str(request.url):
            return httpx.Response(500, text="Internal Server Error")
        return httpx.Response(200, json={"status": "ok"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(failing_handler))
    toolset = DistributionToolset(config=dist_config, http_client=client)

    result = await toolset.distribute_package(str(sample_package))
    # GQL artifact to neo4j should fail, others succeed
    failed = [r for r in result["results"] if r["status"] == "failed"]
    delivered = [r for r in result["results"] if r["status"] == "delivered"]
    assert len(failed) == 1
    assert failed[0]["destination"] == "graph_database"
    assert len(delivered) == 4


# --- distribute_batch ---


async def test_distribute_batch_processes_all_packages(dist_config):
    """distribute_batch processes all .pkg.zip files in directory."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    output_dir = Path(dist_config.output.directory)
    # Write two packages
    (output_dir / "pkg1.pkg.zip").write_bytes(make_package_zip("ct1", "i1"))
    (output_dir / "pkg2.pkg.zip").write_bytes(make_package_zip("ct2", "i2"))

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    result = await toolset.distribute_batch()
    assert result["count"] == 2
    assert result["failed"] == 0
    assert len(result["results"]) == 2


async def test_distribute_batch_defaults_to_output_dir(dist_config, sample_package):
    """distribute_batch uses output directory when no dir specified."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    result = await toolset.distribute_batch()
    assert result["count"] == 1


# --- bootstrap_triplestore ---


async def test_bootstrap_loads_ontologies(dist_config):
    """bootstrap_triplestore loads ontology files into named graphs."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    # Create ontology files in cache
    cache_root = Path(dist_config.cache.root)
    ont_dir = cache_root / "ontologies"
    ont_dir.mkdir(parents=True, exist_ok=True)
    (ont_dir / "sdc4-core.rdf").write_text("<rdf>core ontology</rdf>")
    (ont_dir / "sdc4-types.ttl").write_text("@prefix sdc4: <urn:sdc4:> .")

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    result = await toolset.bootstrap_triplestore()
    assert len(result["graphs_loaded"]) == 2
    names = {g["name"] for g in result["graphs_loaded"]}
    assert names == {"sdc4-core.rdf", "sdc4-types.ttl"}
    for g in result["graphs_loaded"]:
        assert g["status"] == "loaded"


async def test_bootstrap_skips_existing_graphs(dist_config):
    """bootstrap_triplestore skips graphs that already exist."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    cache_root = Path(dist_config.cache.root)
    ont_dir = cache_root / "ontologies"
    ont_dir.mkdir(parents=True, exist_ok=True)
    (ont_dir / "sdc4-core.rdf").write_text("<rdf>core</rdf>")

    def existing_graph_handler(request: httpx.Request) -> httpx.Response:
        if b"ASK WHERE" in (request.content or b""):
            return httpx.Response(200, json={"boolean": True})  # Exists
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(existing_graph_handler))
    toolset = DistributionToolset(config=dist_config, http_client=client)

    result = await toolset.bootstrap_triplestore()
    assert result["graphs_loaded"][0]["status"] == "already_exists"


async def test_bootstrap_loads_schema_rdf(dist_config):
    """bootstrap_triplestore loads schema RDF when ct_id provided."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    cache_root = Path(dist_config.cache.root)
    schemas_dir = cache_root / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)
    (schemas_dir / "dm-clxyz123abc.ttl").write_text("@prefix sdc4: <urn:sdc4:> .")

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    result = await toolset.bootstrap_triplestore(ct_id="clxyz123abc")
    schema_graphs = [g for g in result["graphs_loaded"] if "schema" in g["graph_uri"]]
    assert len(schema_graphs) == 1
    assert schema_graphs[0]["graph_uri"] == "urn:sdc4:schema:clxyz123abc"
    assert schema_graphs[0]["status"] == "loaded"


async def test_bootstrap_requires_triplestore_config(dist_config):
    """bootstrap_triplestore raises ValueError when no triplestore configured."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    # Remove triplestore destinations
    dist_config.destinations = {
        k: v for k, v in dist_config.destinations.items()
        if v.type not in ("fuseki", "graphdb")
    }

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    with pytest.raises(ValueError, match="No triplestore destination configured"):
        await toolset.bootstrap_triplestore()


# --- Path confinement ---


async def test_path_confinement_rejects_outside_output(dist_config):
    """Distribution tools reject paths outside output directory."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    with pytest.raises(PermissionError, match="outside the output directory"):
        await toolset.inspect_package("/etc/passwd")

    with pytest.raises(PermissionError, match="outside the output directory"):
        await toolset.distribute_package("/tmp/evil.pkg.zip")


async def test_path_confinement_rejects_traversal(dist_config):
    """Distribution tools reject relative path traversal."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    traversal = f"{dist_config.output.directory}/../../../etc/passwd"
    with pytest.raises(PermissionError, match="outside the output directory"):
        await toolset.inspect_package(traversal)


# --- Audit logging ---


async def test_audit_logging_records_tool_calls(dist_config, sample_package):
    """All tool calls write audit log entries."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    await toolset.inspect_package(str(sample_package))
    await toolset.list_destinations()

    audit_path = Path(dist_config.audit.path)
    records = [json.loads(line) for line in audit_path.read_text().strip().split("\n")]
    tools = {r["tool"] for r in records}
    assert "inspect_package" in tools
    assert "list_destinations" in tools
    assert all(r["agent"] == "distribution" for r in records)


async def test_destination_credentials_redacted_in_audit(dist_config, sample_package):
    """Destination auth credentials are redacted in audit log."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    await toolset.distribute_package(str(sample_package))

    audit_content = Path(dist_config.audit.path).read_text()
    # Auth tokens should not appear in the log
    assert "Basic dXNlcjpwYXNz" not in audit_content
    assert "Basic bmVvNGo6dGVzdA==" not in audit_content
    assert "Bearer test-token" not in audit_content


# --- Tool count ---


async def test_distribution_exposes_exactly_5_tools(dist_config):
    """Distribution toolset exposes exactly 5 tools."""
    from sdc_agents.toolsets.distribution import DistributionToolset

    client = httpx.AsyncClient(transport=_mock_transport())
    toolset = DistributionToolset(config=dist_config, http_client=client)

    tools = await toolset.get_tools()
    assert len(tools) == 5
    names = {t.name for t in tools}
    assert names == {
        "inspect_package",
        "list_destinations",
        "distribute_package",
        "distribute_batch",
        "bootstrap_triplestore",
    }
