"""Distribution Agent factory — route artifact packages to customer destinations."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.distribution import DistributionToolset


def create_distribution_agent(
    config: SDCAgentsConfig,
    model: str = "gemini-2.0-flash",
) -> LlmAgent:
    """Create a Distribution Agent for SDC4 artifact package delivery.

    The agent routes validated artifact packages to configured destinations
    including triplestores, graph databases, REST APIs, and filesystem paths.

    Args:
        config: SDC Agents configuration.
        model: LLM model identifier.

    Returns:
        Configured LlmAgent with DistributionToolset.
    """
    return LlmAgent(
        name="distribution_agent",
        model=model,
        description=(
            "Distributes SDC4 artifact packages to customer destinations. "
            "Routes XML, JSON, RDF, GQL, and JSON-LD artifacts to "
            "triplestores, graph databases, REST APIs, and filesystem paths."
        ),
        instruction=(
            "You are the Distribution Agent. Your job is to deliver SDC4 "
            "artifact packages (.pkg.zip) to configured destinations.\n\n"
            "You can:\n"
            "- Inspect artifact packages to see their contents and manifest\n"
            "- List configured destinations and check their connectivity\n"
            "- Distribute individual packages to all configured destinations\n"
            "- Batch distribute all packages in the output directory\n"
            "- Bootstrap triplestores with SDC4 ontologies and schema RDF\n\n"
            "You CANNOT:\n"
            "- Access datasources (SQL, CSV, etc.)\n"
            "- Generate or validate XML instances\n"
            "- Access files outside the configured output directory\n"
            "- Modify schemas, mappings, or catalog entries\n"
            "- Create or modify destination configurations\n\n"
            "Packages contain a manifest.json that maps each artifact to a "
            "named destination. If a destination is not configured, the "
            "artifact is skipped (not an error). Always inspect a package "
            "before distributing if you're unsure of its contents."
        ),
        tools=[DistributionToolset(config=config)],
    )
