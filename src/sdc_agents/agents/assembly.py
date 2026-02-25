"""Assembly Agent factory — discovers components and assembles data models."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.assembly import AssemblyToolset


def create_assembly_agent(
    config: SDCAgentsConfig,
    model: str = "gemini-2.0-flash",
) -> LlmAgent:
    """Create an Assembly Agent for component discovery and model assembly.

    The Assembly Agent discovers catalog components matching datasource
    structure, proposes Cluster hierarchies, selects contextual components,
    and calls the SDCStudio Assembly API to produce published data models.

    Args:
        config: Validated SDC Agents configuration.
        model: LLM model name for the agent.

    Returns:
        Configured LlmAgent instance.
    """
    return LlmAgent(
        name="assembly_agent",
        model=model,
        description=(
            "Discovers catalog components matching datasource structure, proposes "
            "Cluster hierarchies, and assembles published data models via the "
            "SDCStudio Assembly API."
        ),
        instruction=(
            "You are the Assembly Agent for SDC Agents. Your purpose is to discover "
            "matching components, propose hierarchical structures, and assemble "
            "complete data models.\n\n"
            "CAN:\n"
            "- Discover catalog components matching introspected datasource columns\n"
            "- Propose Cluster hierarchies from datasource structure\n"
            "- Select contextual components (audit, attestation, party) from the "
            "default library project\n"
            "- Assemble complete data models via the Assembly API\n\n"
            "CANNOT:\n"
            "- Access datasources directly (use cached introspection results)\n"
            "- Modify existing schemas or components\n"
            "- Bypass type compatibility rules\n"
            "- Create partial or incomplete models\n\n"
            "Always verify component matches before proposing a hierarchy. "
            "Assembly requests are fail-closed: the entire request is rejected "
            "if any referenced component is invalid."
        ),
        tools=[AssemblyToolset(config=config)],
    )
