"""Mapping Agent factory — column-to-component mapping."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.mapping import MappingToolset


def create_mapping_agent(
    config: SDCAgentsConfig,
    model: str = "gemini-2.0-flash",
) -> LlmAgent:
    """Create a Mapping Agent for column-to-SDC4-component mapping.

    The agent suggests mappings based on type compatibility and name
    similarity, and can persist confirmed mappings to cache.
    No direct datasource or API access.

    Args:
        config: SDC Agents configuration.
        model: LLM model identifier.

    Returns:
        Configured LlmAgent with MappingToolset.
    """
    return LlmAgent(
        name="mapping_agent",
        model=model,
        description=(
            "Maps datasource columns to SDC4 schema components using type "
            "compatibility and name similarity. Works with cached data only."
        ),
        instruction=(
            "You are the Mapping Agent. Your job is to help users map their "
            "datasource columns to SDC4 schema components.\n\n"
            "You can:\n"
            "- Suggest component mappings based on type and name similarity\n"
            "- Confirm and persist mapping configurations\n"
            "- List saved mapping configurations\n\n"
            "You CANNOT:\n"
            "- Access datasources directly\n"
            "- Access the SDCStudio API\n"
            "- Modify schemas\n\n"
            "Schemas must be cached first (via the Catalog Agent) before you "
            "can suggest mappings. Always explain your mapping rationale, "
            "including type compatibility and name similarity scores."
        ),
        tools=[MappingToolset(config=config)],
    )
