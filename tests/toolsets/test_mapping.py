"""Tests for the Mapping Toolset."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.mapping import TYPE_COMPATIBILITY, MappingToolset
from tests.fixtures.catalog_responses import make_schema_detail_response


@pytest.fixture
def mapping_config(tmp_path: Path) -> SDCAgentsConfig:
    return SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl"), "log_level": "verbose"},
    )


@pytest.fixture
def mapping_toolset(mapping_config: SDCAgentsConfig) -> MappingToolset:
    toolset = MappingToolset(config=mapping_config)
    # Pre-populate cache with a schema
    from sdc_agents.common.cache import CacheManager

    cache = CacheManager(mapping_config.cache.root)
    cache.ensure_dirs()
    schema = make_schema_detail_response("clxyz123abc")
    cache.schema_path("clxyz123abc").write_text(json.dumps(schema))
    return toolset


async def test_suggest_type_compatible(mapping_toolset: MappingToolset):
    """Suggestions are filtered by type compatibility."""
    results = await mapping_toolset.mapping_suggest(
        column_name="test_name",
        column_type="string",
        schema_ct_id="clxyz123abc",
    )
    # Should match XdString components only
    assert len(results) > 0
    for r in results:
        assert r["component_type"] in TYPE_COMPATIBILITY["string"]


async def test_suggest_name_similarity(mapping_toolset: MappingToolset):
    """Higher name similarity produces higher scores."""
    results = await mapping_toolset.mapping_suggest(
        column_name="test-name",
        column_type="string",
        schema_ct_id="clxyz123abc",
    )
    # "test-name" should score high against the "test-name" component
    assert results[0]["component_label"] == "test-name"
    assert results[0]["score"] > 0.5


async def test_suggest_uncached_schema(mapping_toolset: MappingToolset):
    """Suggesting against uncached schema raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="not found in cache"):
        await mapping_toolset.mapping_suggest(
            column_name="x", column_type="string", schema_ct_id="nonexistent"
        )


async def test_confirm_and_list_roundtrip(mapping_toolset: MappingToolset):
    """Confirmed mappings can be listed back."""
    mappings = [
        {
            "column_name": "test_name",
            "component_ct_id": "clxdstr001",
            "component_type": "XdString",
        },
        {
            "column_name": "result_value",
            "component_ct_id": "clxdqty001",
            "component_type": "XdQuantity",
        },
    ]
    result = await mapping_toolset.mapping_confirm("lab-mapping", mappings)
    assert result["mapping_name"] == "lab-mapping"
    assert result["count"] == 2

    listed = await mapping_toolset.mapping_list()
    assert len(listed) == 1
    assert listed[0]["name"] == "lab-mapping"
    assert listed[0]["count"] == 2


async def test_confirm_validates_keys(mapping_toolset: MappingToolset):
    """Missing keys in mapping entries raise ValueError."""
    with pytest.raises(ValueError, match="missing keys"):
        await mapping_toolset.mapping_confirm(
            "bad-mapping",
            [{"column_name": "x"}],  # missing component_ct_id, component_type
        )


async def test_list_empty(mapping_toolset: MappingToolset):
    """Listing with no saved mappings returns empty list."""
    results = await mapping_toolset.mapping_list()
    assert results == []


async def test_get_tools_returns_three(mapping_toolset: MappingToolset):
    """get_tools returns exactly 3 tools."""
    tools = await mapping_toolset.get_tools()
    assert len(tools) == 3
    names = {t.name for t in tools}
    assert names == {"mapping_suggest", "mapping_confirm", "mapping_list"}
