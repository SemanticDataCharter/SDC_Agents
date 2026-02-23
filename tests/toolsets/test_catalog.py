"""Tests for the Catalog Toolset."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.catalog import CatalogToolset
from tests.conftest import read_audit_records
from tests.fixtures.catalog_responses import (
    make_ontologies_response,
    make_rdf_response,
    make_schema_detail_response,
    make_schema_list_response,
    make_skeleton_response,
)


def _make_transport(routes: dict[str, tuple[int, dict | str]]) -> httpx.MockTransport:
    """Create a MockTransport from a route map of path -> (status, body)."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in routes:
            status, body = routes[path]
            if isinstance(body, str):
                return httpx.Response(status, text=body)
            return httpx.Response(status, json=body)
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.fixture
def catalog_config(tmp_path: Path) -> SDCAgentsConfig:
    return SDCAgentsConfig(
        sdcstudio={"base_url": "https://test.local"},
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl"), "log_level": "verbose"},
    )


@pytest.fixture
def catalog_toolset(catalog_config: SDCAgentsConfig) -> CatalogToolset:
    transport = _make_transport(
        {
            "/api/catalog/schemas/": (200, make_schema_list_response()),
            "/api/catalog/schemas/clxyz123abc/": (200, make_schema_detail_response()),
            "/api/catalog/schemas/clxyz123abc/artifacts/rdf/": (200, make_rdf_response()),
            "/api/catalog/schemas/clxyz123abc/artifacts/skeleton/": (
                200,
                make_skeleton_response(),
            ),
            "/api/catalog/schemas/clxyz123abc/artifacts/ontologies/": (
                200,
                make_ontologies_response(),
            ),
        }
    )
    client = httpx.AsyncClient(transport=transport, base_url="https://test.local")
    return CatalogToolset(config=catalog_config, http_client=client)


async def test_list_schemas(catalog_toolset: CatalogToolset):
    """list_schemas returns schema summaries."""
    result = await catalog_toolset.catalog_list_schemas()
    assert len(result) == 2
    assert result[0]["ct_id"] == "clxyz123abc"


async def test_get_schema(catalog_toolset: CatalogToolset):
    """get_schema returns full detail and caches it."""
    result = await catalog_toolset.catalog_get_schema("clxyz123abc")
    assert result["title"] == "Lab Results"
    assert len(result["components"]) == 1

    # Second call should hit cache
    result2 = await catalog_toolset.catalog_get_schema("clxyz123abc")
    assert result2 == result


async def test_get_schema_cache_hit(catalog_toolset: CatalogToolset, catalog_config):
    """Cached schema is returned without HTTP call."""
    from sdc_agents.common.cache import CacheManager

    cache = CacheManager(catalog_config.cache.root)
    cache.ensure_dirs()
    cached_data = {"ct_id": "clxyz123abc", "title": "Cached", "from_cache": True}
    cache.schema_path("clxyz123abc").write_text(json.dumps(cached_data))

    result = await catalog_toolset.catalog_get_schema("clxyz123abc")
    assert result["from_cache"] is True


async def test_download_rdf(catalog_toolset: CatalogToolset):
    """download_schema_rdf returns RDF content."""
    result = await catalog_toolset.catalog_download_schema_rdf("clxyz123abc")
    assert "rdf:RDF" in result
    assert "Lab Results" in result


async def test_download_skeleton(catalog_toolset: CatalogToolset):
    """download_skeleton returns XML skeleton."""
    result = await catalog_toolset.catalog_download_skeleton("clxyz123abc")
    assert "sdc4:dm-clxyz123abc" in result


async def test_download_ontologies(catalog_toolset: CatalogToolset):
    """download_ontologies returns ontology RDF."""
    result = await catalog_toolset.catalog_download_ontologies("clxyz123abc")
    assert "owl:Ontology" in result


async def test_get_tools_returns_five(catalog_toolset: CatalogToolset):
    """get_tools returns exactly 5 tools."""
    tools = await catalog_toolset.get_tools()
    assert len(tools) == 5
    names = {t.name for t in tools}
    assert names == {
        "catalog_list_schemas",
        "catalog_get_schema",
        "catalog_download_schema_rdf",
        "catalog_download_skeleton",
        "catalog_download_ontologies",
    }


async def test_audit_log_written(catalog_toolset: CatalogToolset, catalog_config):
    """Tool calls write audit records."""
    from sdc_agents.common.audit import AuditLogger

    await catalog_toolset.catalog_list_schemas()
    audit = AuditLogger(catalog_config.audit.path)
    records = read_audit_records(audit)
    assert len(records) >= 1
    assert records[0]["tool"] == "catalog_list_schemas"
