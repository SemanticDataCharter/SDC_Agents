"""Semantic Discovery Agent factory — Vertex AI Search for SDC4 resources.

ADK-native only. VertexAiSearchTool requires a non-None ToolContext for
run_async(), making this agent incompatible with the MCP stdio adapter.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.semantic_discovery import SemanticDiscoveryToolset


def create_semantic_discovery_agent(
    config: SDCAgentsConfig,
    model: str = "gemini-2.0-flash",
) -> LlmAgent:
    """Create a Semantic Discovery Agent for searching Vertex AI Search.

    The Semantic Discovery Agent searches a configured Vertex AI Search
    data store for semantically relevant SDC4 resources, enabling
    intelligent catalog matching beyond syntactic name similarity.

    Args:
        config: Validated SDC Agents configuration.
        model: LLM model name for the agent.

    Returns:
        Configured LlmAgent instance.
    """
    return LlmAgent(
        name="semantic_discovery_agent",
        model=model,
        description=(
            "Searches Vertex AI Search for semantically relevant SDC4 resources "
            "and catalog components."
        ),
        instruction=(
            "You are the Semantic Discovery Agent for SDC Agents. Your purpose is "
            "to search a configured Vertex AI Search data store for SDC4 resources.\n\n"
            "CAN:\n"
            "- Search the configured Vertex AI Search data store for relevant SDC4 "
            "resources\n\n"
            "CANNOT:\n"
            "- Access datasources (SQL, CSV, JSON, MongoDB, BigQuery)\n"
            "- Access the file system\n"
            "- Modify data or schemas\n"
            "- Access any GCP service other than Vertex AI Search\n\n"
            "Return search results with relevance scores and document metadata."
        ),
        tools=[SemanticDiscoveryToolset(config=config)],
    )
