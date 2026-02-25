"""Tests for the Assembly toolset."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.assembly import AssemblyToolset
from tests.fixtures.assembly_responses import (
    make_assembly_api_response,
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
    """Assemble model calls Assembly API and returns result."""
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

    assert result["dm_ct_id"] == "cldm00assembly01"
    assert result["title"] == "Lab Results Model"
    assert result["status"] == "published"
    assert "artifact_urls" in result
    assert "xsd" in result["artifact_urls"]


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
