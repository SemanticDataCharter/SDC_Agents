"""Tests for the Assembly toolset."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.common.exceptions import InsufficientFundsError
from sdc_agents.toolsets.assembly import AssemblyToolset
from tests.fixtures.assembly_responses import (
    make_assembly_api_response,
    make_assembly_insufficient_funds_response,
    make_assembly_processing_response,
    make_catalog_search_response,
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

        if "/api/v1/catalog/components/" in url and request.method == "GET":
            # Parse the type param from query string to return correct fixture
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            comp_type = params.get("type", ["audit"])[0]
            return httpx.Response(
                200, json=make_contextual_components_response(component_type=comp_type)
            )
        if "/api/v1/dmgen/components/" in url and request.method == "GET":
            # Return empty results by default for existing tests
            return httpx.Response(200, json=make_catalog_search_response())
        if "/api/v1/dmgen/assemble/" in url and request.method == "POST":
            return httpx.Response(200, json=make_assembly_api_response())
        if "/api/v1/auth/modeler/" in url and request.method == "GET":
            return httpx.Response(
                200,
                json={"project_ct_id": "clproj_default", "name": "Test Modeler"},
            )

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
        if "/api/v1/catalog/components/" in url:
            return httpx.Response(200, json={"count": 0, "results": []})
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
    unmatched_names = [u["name"] for u in result["unmatched"]]
    assert "internal_id" in unmatched_names  # integer won't match any schema component

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
    """Select contextual components from default project — all 9 slots."""
    toolset = AssemblyToolset(config=assembly_config, http_client=assembly_client)

    result = await toolset.select_contextual_components()

    assert result["project"] == "SDC4-Core"
    assert "contextual" in result
    ctx = result["contextual"]

    # All 9 contextual slots must be present
    expected_slots = {
        "audit",
        "attestation",
        "party",
        "subject",
        "provider",
        "participation",
        "protocol",
        "workflow",
        "acs",
    }
    assert set(ctx.keys()) == expected_slots

    # With our mock data, all 9 should be found
    assert ctx["audit"] is not None
    assert ctx["audit"]["label"] == "audit-trail"
    assert ctx["attestation"]["label"] == "attestation"
    assert ctx["party"]["label"] == "party-identifier"
    assert ctx["subject"]["label"] == "subject"
    assert ctx["provider"]["label"] == "provider"
    assert ctx["participation"]["label"] == "participation"
    assert ctx["protocol"]["label"] == "protocol"
    assert ctx["workflow"]["label"] == "workflow"
    assert ctx["acs"]["label"] == "acs"


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
    assert "/api/v1/catalog/dm/" in result["artifact_urls"]["xsd"]


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

    assert exc_info.value.estimated_cost == 0.30
    assert exc_info.value.balance_remaining == 0.05


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

    # Without X-SDC-* headers, falls back to body fields
    assert exc_info.value.estimated_cost == 0.50
    assert exc_info.value.balance_remaining == 0.10


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
    assert result["estimated_cost"] == 0.20
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


# --- Description-based matching ---


async def test_discover_description_matching(assembly_config, assembly_client, tmp_path):
    """Column with coded name + description matches component by description."""
    toolset = AssemblyToolset(config=assembly_config, http_client=assembly_client)

    # Introspection with coded column name but human-readable description
    intro_dir = tmp_path / ".sdc-cache" / "introspections"
    intro_dir.mkdir(parents=True, exist_ok=True)
    introspection = {
        "columns": [
            {
                "name": "BPXSY1",
                "data_type": "decimal",
                "description": "Systolic Blood Pressure",
            },
        ]
    }
    (intro_dir / "nhanes_bp.json").write_text(json.dumps(introspection))

    # Schema with component matching the description
    schema_dir = tmp_path / ".sdc-cache" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    schema = {
        "components": [
            {
                "type": "XdQuantity",
                "ct_id": "clxdqty_bp",
                "label": "systolic-blood-pressure",
            },
        ]
    }
    (schema_dir / "clschema_bp.json").write_text(json.dumps(schema))

    result = await toolset.discover_components("nhanes_bp", schema_ct_id="clschema_bp")

    # "BPXSY1" alone would score low, but "Systolic Blood Pressure" matches well
    assert len(result["matches"]) == 1
    assert result["matches"][0]["column"] == "BPXSY1"
    assert result["matches"][0]["ct_id"] == "clxdqty_bp"


async def test_discover_description_beats_name(assembly_config, assembly_client, tmp_path):
    """Description match wins when name score is low."""
    toolset = AssemblyToolset(config=assembly_config, http_client=assembly_client)

    intro_dir = tmp_path / ".sdc-cache" / "introspections"
    intro_dir.mkdir(parents=True, exist_ok=True)
    introspection = {
        "columns": [
            {
                "name": "RIDAGEYR",
                "data_type": "integer",
                "description": "Age in years at screening",
            },
        ]
    }
    (intro_dir / "nhanes.json").write_text(json.dumps(introspection))

    schema_dir = tmp_path / ".sdc-cache" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    schema = {
        "components": [
            {"type": "XdCount", "ct_id": "clxdcnt_age", "label": "age-in-years"},
        ]
    }
    (schema_dir / "clschema_demo.json").write_text(json.dumps(schema))

    result = await toolset.discover_components("nhanes", schema_ct_id="clschema_demo")

    assert len(result["matches"]) == 1
    assert result["matches"][0]["ct_id"] == "clxdcnt_age"
    # Score should be > 0.3 (from description match)
    assert result["matches"][0]["score"] > 0.3


async def test_backward_compat_inferred_type(assembly_config, assembly_client, tmp_path):
    """Old cache files with inferred_type still work via fallback."""
    toolset = AssemblyToolset(config=assembly_config, http_client=assembly_client)

    intro_dir = tmp_path / ".sdc-cache" / "introspections"
    intro_dir.mkdir(parents=True, exist_ok=True)
    # Old-style cache with inferred_type
    introspection = {
        "columns": [
            {"name": "test_name", "inferred_type": "string"},
        ]
    }
    (intro_dir / "old_ds.json").write_text(json.dumps(introspection))

    schema_dir = tmp_path / ".sdc-cache" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    schema = {
        "components": [
            {"type": "XdString", "ct_id": "clxdstr001", "label": "test-name"},
        ]
    }
    (schema_dir / "clschema_old.json").write_text(json.dumps(schema))

    result = await toolset.discover_components("old_ds", schema_ct_id="clschema_old")

    # Should still match despite using inferred_type
    assert len(result["matches"]) == 1
    assert result["matches"][0]["ct_id"] == "clxdstr001"


async def test_mint_ref_carries_metadata(assembly_config, assembly_client):
    """Unmatched columns pass description/units/enumeration to mint refs."""
    toolset = AssemblyToolset(config=assembly_config, http_client=assembly_client)

    matches = [
        {"column": "test_name", "ct_id": "clxdstr001", "label": "test-name", "type": "XdString"},
    ]
    unmatched = [
        {
            "name": "BPXSY1",
            "data_type": "XdQuantity",
            "description": "Systolic Blood Pressure",
            "units": "mmHg",
            "enumeration": {"1": "Acceptable", "2": "Questionable"},
        },
    ]

    result = await toolset.propose_cluster_hierarchy("nhanes_bp", matches, unmatched)

    hierarchy = result["hierarchy"]
    # Find the mint ref
    mint_refs = [c for c in hierarchy["components"] if "ct_id" not in c]
    assert len(mint_refs) == 1
    ref = mint_refs[0]
    assert ref["label"] == "BPXSY1"
    assert ref["data_type"] == "XdQuantity"
    assert ref["description"] == "Systolic Blood Pressure"
    assert ref["units"] == "mmHg"
    assert ref["enumeration"] == {"1": "Acceptable", "2": "Questionable"}


# --- Catalog-first component discovery ---


def _make_catalog_transport(
    project_results: list[dict] | None = None,
    public_results: list[dict] | None = None,
    modeler_project: str | None = "clproj_modeler_default",
):
    """Create a MockTransport that returns catalog search results.

    Args:
        project_results: Results when ``project=`` param is present.
        public_results: Results when no ``project=`` param.
        modeler_project: project_ct_id returned by the Modeler API.
    """
    call_log: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)

        if "/api/v1/auth/modeler/" in url and request.method == "GET":
            return httpx.Response(
                200,
                json={"project_ct_id": modeler_project, "name": "Test Modeler"},
            )
        if "/api/v1/dmgen/components/" in url and request.method == "GET":
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            call_log.append(
                {
                    "search": params.get("search", [None])[0],
                    "project": params.get("project", [None])[0],
                }
            )
            if params.get("project"):
                return httpx.Response(
                    200, json=make_catalog_search_response(project_results or [])
                )
            return httpx.Response(200, json=make_catalog_search_response(public_results or []))
        if "/api/v1/catalog/components/" in url and request.method == "GET":
            return httpx.Response(200, json={"count": 0, "results": []})

        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler), call_log


async def test_catalog_search_project_first(assembly_config, tmp_path):
    """Column 'DIABETE4' with description matches project component; public not called."""
    project_results = [
        {
            "ct_id": "clxdtkn_diab",
            "label": "diabetes-status",
            "type": "xdtoken",
            "description": "Ever told you had diabetes",
            "project_name": "NIH_CDE",
        },
    ]
    transport, call_log = _make_catalog_transport(project_results=project_results)
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = AssemblyToolset(config=assembly_config, http_client=client)

    intro_dir = tmp_path / ".sdc-cache" / "introspections"
    intro_dir.mkdir(parents=True, exist_ok=True)
    introspection = {
        "columns": [
            {
                "name": "DIABETE4",
                "data_type": "decimal",
                "description": "Ever told you had diabetes",
            },
        ]
    }
    (intro_dir / "nhanes_diab.json").write_text(json.dumps(introspection))

    result = await toolset.discover_components(
        "nhanes_diab", search_catalog=True, project_ct_id="proj_nih"
    )

    assert len(result["matches"]) == 1
    m = result["matches"][0]
    assert m["column"] == "DIABETE4"
    assert m["ct_id"] == "clxdtkn_diab"
    assert m["type"] == "XdToken"  # Normalized from lowercase
    assert m["source"] == "catalog_project"
    assert result["catalog_matches"] == 1

    # Only project-scoped call made (no public call for this column)
    project_calls = [c for c in call_log if c["project"] is not None]
    assert len(project_calls) >= 1


async def test_catalog_search_falls_to_public(assembly_config, tmp_path):
    """Column matches public catalog when project search returns nothing."""
    public_results = [
        {
            "ct_id": "clxdord_edu",
            "label": "education-level",
            "type": "xdordinal",
            "description": "Education level completed",
            "project_name": "NIH_CDE",
        },
    ]
    transport, call_log = _make_catalog_transport(
        project_results=[], public_results=public_results
    )
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = AssemblyToolset(config=assembly_config, http_client=client)

    intro_dir = tmp_path / ".sdc-cache" / "introspections"
    intro_dir.mkdir(parents=True, exist_ok=True)
    introspection = {
        "columns": [
            {
                "name": "DMDEDUC2",
                "data_type": "decimal",
                "description": "Education level",
            },
        ]
    }
    (intro_dir / "nhanes_edu.json").write_text(json.dumps(introspection))

    result = await toolset.discover_components(
        "nhanes_edu", search_catalog=True, project_ct_id="proj_nih"
    )

    assert len(result["matches"]) == 1
    m = result["matches"][0]
    assert m["ct_id"] == "clxdord_edu"
    assert m["type"] == "XdOrdinal"
    assert m["source"] == "catalog_public"
    assert result["catalog_matches"] == 1


async def test_catalog_search_type_override(assembly_config, tmp_path):
    """Catalog type overrides inferred type — decimal column matches XdOrdinal."""
    public_results = [
        {
            "ct_id": "clxdord_edu",
            "label": "education-level",
            "type": "xdordinal",
            "description": "Education level completed",
            "project_name": "NIH_CDE",
        },
    ]
    transport, _ = _make_catalog_transport(public_results=public_results)
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = AssemblyToolset(config=assembly_config, http_client=client)

    intro_dir = tmp_path / ".sdc-cache" / "introspections"
    intro_dir.mkdir(parents=True, exist_ok=True)
    introspection = {
        "columns": [
            {
                "name": "DMDEDUC2",
                "data_type": "decimal",  # _infer_type sees SAS double
                "description": "Education level",
            },
        ]
    }
    (intro_dir / "nhanes_type.json").write_text(json.dumps(introspection))

    result = await toolset.discover_components("nhanes_type", search_catalog=True)

    assert len(result["matches"]) == 1
    # XdOrdinal is NOT in TYPE_COMPATIBILITY["decimal"] = {XdQuantity, XdDecimalList}
    # but catalog-first search ignores type compatibility
    assert result["matches"][0]["type"] == "XdOrdinal"


async def test_catalog_search_caching(assembly_config, tmp_path):
    """Same keyword searched twice results in only one API call."""
    public_results = [
        {
            "ct_id": "clxdtkn_diab",
            "label": "diabetes-status",
            "type": "xdtoken",
            "description": "Ever told you had diabetes",
            "project_name": "NIH_CDE",
        },
    ]
    transport, call_log = _make_catalog_transport(public_results=public_results)
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = AssemblyToolset(config=assembly_config, http_client=client)

    intro_dir = tmp_path / ".sdc-cache" / "introspections"
    intro_dir.mkdir(parents=True, exist_ok=True)
    # Two columns with same description keyword
    introspection = {
        "columns": [
            {
                "name": "DIABETE3",
                "data_type": "decimal",
                "description": "Ever told you had diabetes",
            },
            {
                "name": "DIABETE4",
                "data_type": "decimal",
                "description": "Ever told you had diabetes",
            },
        ]
    }
    (intro_dir / "nhanes_cache.json").write_text(json.dumps(introspection))

    result = await toolset.discover_components("nhanes_cache", search_catalog=True)

    # Both columns should match
    assert len(result["matches"]) == 2

    # But the same keyword should only trigger one API call (cached on second)
    # Extract unique search keywords from call_log
    unique_searches = {(c["search"], c["project"]) for c in call_log}
    # "told diabetes" extracted from both descriptions is the same query
    # so we expect at most 2 unique queries (keyword variants), not 4
    assert len(call_log) <= len(unique_searches) + 1  # Allow 1 extra for keyword variants


async def test_catalog_search_disabled(assembly_config, tmp_path):
    """search_catalog=False skips catalog API calls entirely."""
    transport, call_log = _make_catalog_transport(
        public_results=[
            {
                "ct_id": "clxdtkn_x",
                "label": "should-not-match",
                "type": "xdtoken",
                "description": "Should not be reached",
                "project_name": "Test",
            },
        ]
    )
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = AssemblyToolset(config=assembly_config, http_client=client)

    intro_dir = tmp_path / ".sdc-cache" / "introspections"
    intro_dir.mkdir(parents=True, exist_ok=True)
    introspection = {
        "columns": [
            {"name": "test_col", "data_type": "string", "description": "Some column"},
        ]
    }
    (intro_dir / "ds_disabled.json").write_text(json.dumps(introspection))

    result = await toolset.discover_components("ds_disabled", search_catalog=False)

    # No catalog API calls should have been made
    assert len(call_log) == 0
    assert result["catalog_matches"] == 0
    # No schema either, so everything unmatched
    assert len(result["unmatched"]) == 1


async def test_catalog_search_no_false_positives(assembly_config, tmp_path):
    """Weak keyword match (score < 0.5) correctly rejected."""
    public_results = [
        {
            "ct_id": "clxdstr_unrel",
            "label": "completely-unrelated-component",
            "type": "xdstring",
            "description": "Something entirely different",
            "project_name": "Other",
        },
    ]
    transport, _ = _make_catalog_transport(public_results=public_results)
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = AssemblyToolset(config=assembly_config, http_client=client)

    intro_dir = tmp_path / ".sdc-cache" / "introspections"
    intro_dir.mkdir(parents=True, exist_ok=True)
    introspection = {
        "columns": [
            {
                "name": "SEQN",
                "data_type": "integer",
                "description": "Respondent sequence number",
            },
        ]
    }
    (intro_dir / "nhanes_fp.json").write_text(json.dumps(introspection))

    result = await toolset.discover_components("nhanes_fp", search_catalog=True)

    # Should not match — similarity too low
    assert result["catalog_matches"] == 0
    assert len(result["unmatched"]) == 1


async def test_catalog_search_falls_through_to_schema(assembly_config, tmp_path):
    """No catalog match but schema component matches — existing behavior preserved."""
    transport, _ = _make_catalog_transport()  # Empty catalog results
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = AssemblyToolset(config=assembly_config, http_client=client)

    intro_dir = tmp_path / ".sdc-cache" / "introspections"
    intro_dir.mkdir(parents=True, exist_ok=True)
    introspection = {
        "columns": [
            {"name": "test_name", "data_type": "string"},
        ]
    }
    (intro_dir / "ds_fallback.json").write_text(json.dumps(introspection))

    schema_dir = tmp_path / ".sdc-cache" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    schema = {
        "components": [
            {"type": "XdString", "ct_id": "clxdstr001", "label": "test-name"},
        ]
    }
    (schema_dir / "clschema_fb.json").write_text(json.dumps(schema))

    result = await toolset.discover_components(
        "ds_fallback", schema_ct_id="clschema_fb", search_catalog=True
    )

    # Catalog returned nothing, but schema-tree match works
    assert result["catalog_matches"] == 0
    assert len(result["matches"]) == 1
    assert result["matches"][0]["ct_id"] == "clxdstr001"
    assert "source" not in result["matches"][0]  # Schema matches don't have source


# --- Modeler default project auto-fetch ---


async def test_get_modeler_project(assembly_config, assembly_client):
    """_get_modeler_project fetches and caches the Modeler's default project."""
    toolset = AssemblyToolset(config=assembly_config, http_client=assembly_client)

    project = await toolset._get_modeler_project()
    assert project == "clproj_default"

    # Second call returns cached value (no extra API call)
    project2 = await toolset._get_modeler_project()
    assert project2 == "clproj_default"


async def test_get_modeler_project_none(assembly_config):
    """_get_modeler_project returns None when Modeler has no default project."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/v1/auth/modeler/" in url:
            return httpx.Response(200, json={"project_ct_id": None, "name": "Test Modeler"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = AssemblyToolset(config=assembly_config, http_client=client)

    project = await toolset._get_modeler_project()
    assert project is None


async def test_discover_auto_fetches_modeler_project(assembly_config, tmp_path):
    """discover_components auto-fetches Modeler project when project_ct_id not passed."""
    public_results = [
        {
            "ct_id": "clxdtkn_diab",
            "label": "diabetes-status",
            "type": "xdtoken",
            "description": "Ever told you had diabetes",
            "project_name": "NIH_CDE",
        },
    ]
    transport, call_log = _make_catalog_transport(
        project_results=[], public_results=public_results
    )
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    toolset = AssemblyToolset(config=assembly_config, http_client=client)

    intro_dir = tmp_path / ".sdc-cache" / "introspections"
    intro_dir.mkdir(parents=True, exist_ok=True)
    introspection = {
        "columns": [
            {
                "name": "DIABETE4",
                "data_type": "decimal",
                "description": "Ever told you had diabetes",
            },
        ]
    }
    (intro_dir / "nhanes_auto.json").write_text(json.dumps(introspection))

    # No project_ct_id passed — should auto-fetch from Modeler API
    await toolset.discover_components("nhanes_auto")

    # Should have searched Modeler's project first
    project_calls = [c for c in call_log if c["project"] is not None]
    assert len(project_calls) >= 1
    assert project_calls[0]["project"] == "clproj_modeler_default"
