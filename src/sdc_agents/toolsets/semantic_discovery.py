"""Semantic Discovery toolset — Vertex AI Search for SDC4 component discovery.

Wraps ADK's VertexAiSearchTool to search a configured Vertex AI Search
data store for semantically relevant SDC4 resources.

ADK-native only — VertexAiSearchTool requires a non-None ToolContext for
run_async(), making it incompatible with the MCP stdio adapter.
"""

from __future__ import annotations

from google.adk.tools import VertexAiSearchTool
from google.adk.tools.base_toolset import BaseToolset

from sdc_agents.common.config import SDCAgentsConfig


class SemanticDiscoveryToolset(BaseToolset):
    """Toolset wrapping VertexAiSearchTool for semantic component discovery."""

    def __init__(
        self,
        config: SDCAgentsConfig,
        **kwargs,
    ):
        super().__init__(**kwargs)
        vas_config = config.vertex_ai_search
        if not vas_config.enabled:
            raise RuntimeError(
                "Semantic Discovery Agent requires vertex_ai_search.enabled: true "
                "in configuration."
            )
        self._search_tool = VertexAiSearchTool(
            data_store_id=vas_config.data_store_id,
            search_engine_id=vas_config.search_engine_id,
        )

    async def get_tools(self) -> list:
        return [self._search_tool]
