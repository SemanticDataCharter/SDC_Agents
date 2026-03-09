"""Catalog Agent factory — schema discovery and artifact retrieval."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.catalog import CatalogToolset


def create_catalog_agent(
    config: SDCAgentsConfig,
    model: str = "gemini-2.0-flash",
) -> LlmAgent:
    """Create a Catalog Agent for SDC4 schema discovery.

    The agent can list schemas, get schema details, and download
    artifacts (RDF, skeleton, ontologies) from the SDCStudio Catalog API.
    It has no datasource access and no write capabilities.

    Args:
        config: SDC Agents configuration.
        model: LLM model identifier.

    Returns:
        Configured LlmAgent with CatalogToolset.
    """
    return LlmAgent(
        name="catalog_agent",
        model=model,
        description=(
            "Discovers and retrieves SDC4 schemas from the SDCStudio Catalog API. "
            "Read-only access to published schemas and their artifacts."
        ),
        instruction=(
            "You are the Catalog Agent. Your job is to help users discover and "
            "retrieve SDC4 schemas from the SDCStudio catalog.\n\n"
            "You can:\n"
            "- List available schemas, optionally filtering by search query\n"
            "- Get full schema details including component trees\n"
            "- Download schema artifacts: RDF, XML skeletons, ontologies\n"
            "- Check wallet balance before expensive operations\n\n"
            "You CANNOT:\n"
            "- Access datasources (SQL, CSV, etc.)\n"
            "- Modify or create schemas\n"
            "- Write to the file system\n\n"
            "Always use the schema's ct_id (CUID2) when referencing specific schemas. "
            "Schemas are immutable — once published, they never change. "
            "Before assembly or minting operations, check the wallet balance to "
            "ensure sufficient funds are available."
        ),
        tools=[CatalogToolset(config=config)],
    )
