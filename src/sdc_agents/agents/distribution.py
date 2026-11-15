"""Distribution Agent factory — load reference RDF into a dev triplestore."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.distribution import DistributionToolset


def create_distribution_agent(
    config: SDCAgentsConfig,
    model: str = "gemini-2.0-flash",
) -> LlmAgent:
    """Create a Distribution Agent.

    The agent bootstraps a configured Fuseki or GraphDB triplestore with the
    SDC4 ontologies and a model's schema RDF, and checks that configured
    destinations answer. Its package tools (inspect_package,
    distribute_package, distribute_batch) are deprecated: nothing produces
    .pkg.zip packages since the validation service was retired.

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
            "Bootstraps a development triplestore (Fuseki or GraphDB) with "
            "SDC4 ontologies and model schema RDF, and checks connectivity "
            "of configured destinations."
        ),
        instruction=(
            "You are the Distribution Agent. Your job is to load the SDC4 "
            "reference ontologies and a model's schema RDF into a configured "
            "triplestore, typically a development one used while building "
            "and testing a model.\n\n"
            "You can:\n"
            "- List configured destinations and check their connectivity\n"
            "- Bootstrap a triplestore with SDC4 ontologies and schema RDF\n\n"
            "Deprecated, removal planned for 4.6.0: inspect_package, "
            "distribute_package and distribute_batch. They read .pkg.zip "
            "artifact packages, which nothing produces any more. Do not "
            "suggest them; use them only if the user already has such a "
            "package and asks for it.\n\n"
            "You CANNOT:\n"
            "- Access datasources (SQL, CSV, etc.)\n"
            "- Generate or validate XML instances\n"
            "- Access files outside the configured output directory\n"
            "- Modify schemas, mappings, or catalog entries\n"
            "- Create or modify destination configurations\n\n"
            "SDC Agents are design-time tools. Operational data reaches "
            "Governed Data Records through the application stack or Supabase "
            "kit that SDCStudio generates from a published model, not through "
            "this agent."
        ),
        tools=[DistributionToolset(config=config)],
    )
