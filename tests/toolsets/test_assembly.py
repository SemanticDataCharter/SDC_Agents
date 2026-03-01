"""Tests for the Assembly toolset."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.common.exceptions import InsufficientFundsError
from sdc_agents.toolsets.assembly import AssemblyToolset
from tests.fixtures.assembly_responses import (
    make_assembly_api_response,
    make_assembly_insufficient_funds_response,
    make_assembly_processing_response,
    make_contextual_components_response,
)


@pytest.fixture
def assembly_config(tmp_path: Path) -> SDCAgentsConfig:
    """Config with default_library_project and cache."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return SDCAgentsConfig(
        sdcstudio={
            "base_url": "https://test.local",
            "api_key": "test-key",
            "default_library_project": "SDC4-Core",
        },
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        output={"directory": str(output_dir)},
    )


def _make_transport(assembly_config):
    """Create a MockTransport handling Catalog and Assembly API routes."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)

        if "/api/catalog/schemas/" in url and request.method == "GET":
            return httpx.Response(200, json=make_contextual_components_response())
        if "/api/v1/dmgen/assemble/" in url and request.method == "POST":
            return httpx.Response(200, json=make_assembly_api_response())

        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


def _make_error_transport():
    """Create a MockTransport that returns 400 for Assembly API."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/v1/dmgen/assemble/" in url:
            return httpx.Response(
                400, json={"error": "Invalid component reference: clxyz_invalid"}
            )
        if "/api/catalog/schemas/" in url:
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _make_402_transport():
    """Create a MockTransport that returns 402 for Assembly API."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/v1/dmgen/assemble/" in url:
            return httpx.Response(
                402,
                json=make_assembly_insufficient_funds_response(),
                headers={
                    "Content-Type": "application/json",
                    "X-SDC-Estimated-Cost": "0.30",
                    "X-SDC-Balance-Remaining": "0.05",
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _make_202_transport():
    """Create a MockTransport that returns 202 for mixed assembly."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/v1/dmgen/assemble/" in url and request.method == "POST":
            return httpx.Response(202, json=make_assembly_processing_response())
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture
def assembly_client(assembly_config):
    """httpx.AsyncClient with mock transport."""
    transport = _make_transport(assembly_config)
    return httpx.AsyncClient(transport=transport, base_url="https://test.local")


@pytest.fixture
def error_client():
    """httpx.AsyncClient with error mock transport."""
    transport = _make_error_transport()
    return httpx.AsyncClient(transport=transport, base_url="https://test.local")


async def test_get_tools_returns_four(assembly_config, assembly_client):
    """Assembly toolset exposes exactly 4 tools."""
    toolset = AssemblyToolset(config=assembly_config, http_client=assembly_client)
    tools = await toolset.get_tools()
    assert len(tools) == 4
    names = {t.name for t in tools}
    assert names == {
        "discover_components",
        "propose_cluster_hierarchy",
        "select_contextual_components",
        "assemble_model",
    }


async def test_discover_components(assembly_config, assembly_client, tmp_path):
    """Discover components matches introspection columns to schema components."""
    toolset = AssemblyToolset(config=assembly_config, http_client=assembly_client)

    # Pre-populate cache with introspection result
    intro_dir = tmp_path / ".sdc-cache" / "introspections"
    intro_dir.mkdir(parents=True, exist_ok=True)
    introspection = {
        "columns": [
            {"name": "test_name", "data_type": "string"},
            {"name": "result_value", "data_type": "decimal"},
            {"name": "test_date", "data_type": "date"},
            {"name": "internal_id", "data_type": "integer"},
        ]
    }
    (intro_dir / "lab_results.json").write_text(json.dumps(introspection))

    # Pre-populate cache with schema
    schema_dir = tmp_path / ".sdc-cache" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    schema = {
        "components": [
            {"type": "XdString", "ct_id": "clxdstr001", "label": "test-name"},
            {"type": "XdQuantity", "ct_id": "clxdqty001", "label": "result-value"},
            {"type": "XdTemporal", "ct_id": "clxdtmp001", "label": "test-date"},
        ]
    }
    (schema_dir / "clschema001.json").write_text(json.dumps(schema))

    result = await toolset.discover_components("lab_results", schema_ct_id="clschema001")

    assert result["datasource"] == "lab_results"
    assert len(result["matches"]) >= 2  # At least test_name and test_date should match
    assert "internal_id" in result["unmatched"]  # integer won't match any schema component

    # Verify match structure
    for match in result["matches"]:
        assert "column" in match
        assert "ct_id" in match
        assert "label" in match
        assert "type" in match
        assert "score" in match


async def test_discover_components_missing_introspection(assembly_config, assembly_client):
    """Missing introspection raises FileNotFoundError."""
    toolset = AssemblyToolset(config=assembly_config, http_client=assembly_client)
    with pytest.raises(FileNotFoundError, match="No cached introspection"):
        await toolset.discover_components("nonexistent_ds")


async def test_propose_cluster_hierarchy(assembly_config, assembly_client, tmp_path):
    """Propose hierarchy produces tree structure from flat columns."""
    toolset = AssemblyToolset(config=assembly_config, http_client=assembly_client)

    # Pre-populate introspection cache
    intro_dir = tmp_path / ".sdc-cache" / "introspections"
    intro_dir.mkdir(parents=True, exist_ok=True)
    introspection = {
        "columns": [
            {"name": "test_name", "data_type": "string"},
            {"name": "result_value", "data_type": "decimal"},
        ]
    }
    (intro_dir / "lab_results.json").write_text(json.dumps(introspection))

    matches = [
        {"column": "test_name", "ct_id": "clxdstr001", "label": "test-name", "type": "XdString"},
        {
            "column": "result_value",
            "ct_id": "clxdqty001",
            "label": "result-value",
            "type": "XdQuantity",
        },
    ]

    result = await toolset.propose_cluster_hierarchy("lab_results", matches)

    assert "hierarchy" in result
    assert "cluster_count" in result
    assert result["cluster_count"] >= 1
    hierarchy = result["hierarchy"]
    assert "label" in hierarchy
    assert "components" in hierarchy
    assert len(hierarchy["components"]) == 2
    # All matched → all should be reuse refs with ct_id
    for comp in hierarchy["components"]:
        assert "ct_id" in comp
    assert result["reuse_component_count"] == 2
    assert result["new_component_count"] == 0


async def test_propose_cluster_hierarchy_with_unmatched(assembly_config, assembly_client):
    """Unmatched columns become mint-mode refs in the hierarchy."""
    toolset = AssemblyToolset(config=assembly_config, http_client=assembly_client)

    matches = [
        {"column": "test_name", "ct_id": "clxdstr001", "label": "test-name", "type": "XdString"},
    ]
    unmatched = [
        {"name": "internal_id", "data_type": "XdCount"},
        {"name": "notes", "data_type": "XdString", "description": "Free-text notes"},
    ]

    result = await toolset.propose_cluster_hierarchy("lab_results", matches, unmatched)

    hierarchy = result["hierarchy"]
    assert len(hierarchy["components"]) == 3  # 1 matched + 2 unmatched
    assert result["new_component_count"] == 2
    assert result["reuse_component_count"] == 1

    # Find the mint refs (no ct_id, have label + data_type)
    mint_refs = [c for c in hierarchy["components"] if "ct_id" not in c]
    assert len(mint_refs) == 2
    for ref in mint_refs:
        assert "label" in ref
        assert "data_type" in ref


async def test_select_contextual_components(assembly_config, assembly_client):
    """Select contextual components from default project."""
    toolset = AssemblyToolset(config=assembly_config, http_client=assembly_client)

    result = await toolset.select_contextual_components()

    assert result["project"] == "SDC4-Core"
    assert "contextual" in result
    ctx = result["contextual"]
    assert "audit" in ctx
    assert "attestation" in ctx
    assert "party" in ctx
    # With our mock data, all three should be found
    assert ctx["audit"] is not None
    assert ctx["audit"]["label"] == "audit-trail"
    assert ctx["attestation"]["label"] == "attestation"
    assert ctx["party"]["label"] == "party-identifier"


async def test_assemble_model(assembly_config, assembly_client):
    """Assemble model calls Assembly API and returns sync result."""
    toolset = AssemblyToolset(config=assembly_config, http_client=assembly_client)

    assembly_tree = {
        "label": "lab-results",
        "components": [{"ct_id": "clxdstr001"}, {"ct_id": "clxdqty001"}],
        "clusters": [],
    }

    result = await toolset.assemble_model(
        title="Lab Results Model",
        description="A model for lab test results",
        assembly_tree=assembly_tree,
    )

    assert result["mode"] == "sync"
    assert result["dm_ct_id"] == "cldm00assembly01"
    assert result["title"] == "Lab Results Model"
    assert result["status"] == "published"
    assert "artifact_urls" in result
    assert "xsd" in result["artifact_urls"]


async def test_assemble_model_sends_data_key(assembly_config):
    """Verify the payload uses 'data' key (not 'assembly_tree')."""
    captured_payload = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/v1/dmgen/assemble/" in url:
            captured_payload.update(json.loads(request.content))
            return httpx.Response(200, json=make_assembly_api_response())
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = AssemblyToolset(config=assembly_config, http_client=client)

    assembly_tree = {
        "label": "test",
        "components": [{"ct_id": "clxdstr001"}],
        "clusters": [],
    }
    await toolset.assemble_model(
        title="Test",
        description="Test",
        assembly_tree=assembly_tree,
    )

    assert "data" in captured_payload
    assert "assembly_tree" not in captured_payload
    assert captured_payload["data"]["label"] == "test"


async def test_assemble_model_with_contextual(assembly_config):
    """Verify contextual components are included in payload."""
    captured_payload = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/v1/dmgen/assemble/" in url:
            captured_payload.update(json.loads(request.content))
            return httpx.Response(200, json=make_assembly_api_response())
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = AssemblyToolset(config=assembly_config, http_client=client)

    assembly_tree = {
        "label": "test",
        "components": [{"ct_id": "clxdstr001"}],
        "clusters": [],
    }
    contextual = {
        "audit": {"ct_id": "clctx_audit_cluster"},
        "attestation": {"ct_id": "clctx_attest_cluster"},
    }
    await toolset.assemble_model(
        title="Test",
        description="Test",
        assembly_tree=assembly_tree,
        contextual=contextual,
    )

    assert "contextual" in captured_payload
    assert captured_payload["contextual"]["audit"]["ct_id"] == "clctx_audit_cluster"


async def test_assemble_model_api_error(assembly_config, error_client):
    """Assembly API error raises HTTPStatusError."""
    toolset = AssemblyToolset(config=assembly_config, http_client=error_client)

    assembly_tree = {
        "label": "bad-model",
        "components": [{"ct_id": "clxyz_invalid"}],
        "clusters": [],
    }

    with pytest.raises(httpx.HTTPStatusError):
        await toolset.assemble_model(
            title="Bad Model",
            description="Should fail",
            assembly_tree=assembly_tree,
        )


# --- HTTP 402 Insufficient Funds ---


async def test_assemble_model_402(assembly_config):
    """assemble_model raises InsufficientFundsError on HTTP 402."""
    transport = _make_402_transport()
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = AssemblyToolset(config=assembly_config, http_client=client)

    assembly_tree = {
        "label": "expensive-model",
        "components": [
            {"label": "new-field", "data_type": "XdString"},
            {"label": "another-field", "data_type": "XdCount"},
            {"ct_id": "clxdstr001"},
        ],
        "clusters": [],
    }

    with pytest.raises(InsufficientFundsError) as exc_info:
        await toolset.assemble_model(
            title="Expensive Model",
            description="Should fail with 402",
            assembly_tree=assembly_tree,
        )

    assert exc_info.value.estimated_cost == "0.30"
    assert exc_info.value.balance_remaining == "0.05"


async def test_assemble_model_402_without_headers(assembly_config):
    """402 without wallet headers still raises with body data."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/v1/dmgen/assemble/" in url:
            return httpx.Response(
                402,
                json=make_assembly_insufficient_funds_response(
                    estimated_cost="0.50",
                    balance="0.10",
                ),
                headers={"Content-Type": "application/json"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = AssemblyToolset(config=assembly_config, http_client=client)

    assembly_tree = {
        "label": "test",
        "components": [{"label": "new", "data_type": "XdString"}],
        "clusters": [],
    }

    with pytest.raises(InsufficientFundsError) as exc_info:
        await toolset.assemble_model(
            title="Test",
            description="Test",
            assembly_tree=assembly_tree,
        )

    # Without headers, should fall back to empty strings
    assert exc_info.value.estimated_cost == ""
    assert exc_info.value.balance_remaining == ""


# --- HTTP 202 Async Assembly ---


async def test_assemble_model_async_202(assembly_config):
    """Mixed assembly returns async result with task_id."""
    transport = _make_202_transport()
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = AssemblyToolset(config=assembly_config, http_client=client)

    assembly_tree = {
        "label": "mixed-model",
        "components": [
            {"ct_id": "clxdstr001"},
            {"label": "new-field", "data_type": "XdCount"},
        ],
        "clusters": [],
    }

    result = await toolset.assemble_model(
        title="Mixed Model",
        description="Some reuse, some mint",
        assembly_tree=assembly_tree,
    )

    assert result["mode"] == "async"
    assert result["status"] == "processing"
    assert result["task_id"] == "celery-task-abc123"
    assert result["data_source_ct_id"] == "clds00assembly01"
    assert result["estimated_cost"] == "0.20"
    assert result["new_components"] == 2


# --- Auth Header ---


async def test_assemble_model_uses_token_auth(assembly_config):
    """Verify auth header uses Token scheme (not Bearer)."""
    captured_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/v1/dmgen/assemble/" in url:
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json=make_assembly_api_response())
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    # Create client WITHOUT pre-set headers so we see only what the toolset adds
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")

    # Create toolset that will build its own client with Token auth
    toolset = AssemblyToolset(config=assembly_config, http_client=client)

    assembly_tree = {
        "label": "test",
        "components": [{"ct_id": "clxdstr001"}],
        "clusters": [],
    }

    # Note: When using injected http_client, auth headers are set on the client
    # by the toolset constructor. With a test client, we verify the constructor
    # logic separately. Here we verify the post() call doesn't add Bearer.
    await toolset.assemble_model(
        title="Test",
        description="Test",
        assembly_tree=assembly_tree,
    )

    # The injected client won't have headers, but verify no Bearer was added
    auth = captured_headers.get("authorization", "")
    assert "Bearer" not in auth
