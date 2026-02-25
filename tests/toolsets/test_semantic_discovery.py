"""Tests for the Semantic Discovery toolset."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from sdc_agents.common.config import SDCAgentsConfig, VertexAiSearchConfig


def _enabled_config() -> SDCAgentsConfig:
    """Config with vertex_ai_search enabled and a data_store_id."""
    return SDCAgentsConfig(
        vertex_ai_search={
            "enabled": True,
            "data_store_id": ("projects/test/locations/global/dataStores/test-store"),
            "max_results": 5,
        },
    )


def test_get_tools_returns_one():
    """SemanticDiscoveryToolset exposes exactly 1 tool."""
    with patch("sdc_agents.toolsets.semantic_discovery.VertexAiSearchTool") as MockVAS:
        mock_tool = MagicMock()
        mock_tool.name = "vertex_ai_search"
        MockVAS.return_value = mock_tool

        from sdc_agents.toolsets.semantic_discovery import SemanticDiscoveryToolset

        config = _enabled_config()
        toolset = SemanticDiscoveryToolset(config=config)

        import asyncio

        tools = asyncio.get_event_loop().run_until_complete(toolset.get_tools())
        assert len(tools) == 1


def test_disabled_raises_runtime_error():
    """SemanticDiscoveryToolset raises RuntimeError when disabled."""
    from sdc_agents.toolsets.semantic_discovery import SemanticDiscoveryToolset

    config = SDCAgentsConfig(
        vertex_ai_search={"enabled": False},
    )
    with pytest.raises(RuntimeError, match="vertex_ai_search.enabled: true"):
        SemanticDiscoveryToolset(config=config)


def test_missing_store_and_engine_raises():
    """Enabled config without data_store_id or search_engine_id raises ValidationError."""
    with pytest.raises(ValidationError, match="data_store_id or search_engine_id"):
        VertexAiSearchConfig(enabled=True)
