"""Introspect Agent factory — datasource structure extraction."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.introspect import IntrospectToolset


def create_introspect_agent(
    config: SDCAgentsConfig,
    model: str = "gemini-2.0-flash",
) -> LlmAgent:
    """Create an Introspect Agent for datasource structure discovery.

    The agent can execute read-only SQL queries and introspect CSV files
    to discover column structure and infer data types.
    No network access, no file writes.

    Args:
        config: SDC Agents configuration.
        model: LLM model identifier.

    Returns:
        Configured LlmAgent with IntrospectToolset.
    """
    return LlmAgent(
        name="introspect_agent",
        model=model,
        description=(
            "Extracts structure from customer datasources (SQL databases, CSV files). "
            "Read-only access, no network calls."
        ),
        instruction=(
            "You are the Introspect Agent. Your job is to help users understand "
            "the structure of their datasources.\n\n"
            "You can:\n"
            "- Execute SELECT queries against configured SQL datasources\n"
            "- Introspect CSV files to discover columns and infer types\n\n"
            "You CANNOT:\n"
            "- Execute write operations (INSERT, UPDATE, DELETE, DROP, etc.)\n"
            "- Access the SDCStudio API\n"
            "- Access datasources not listed in the configuration\n"
            "- Make network calls\n\n"
            "Always use datasource names from the configuration, never raw "
            "connection strings or file paths. When introspecting, suggest "
            "the most specific type that fits the data."
        ),
        tools=[IntrospectToolset(config=config)],
    )
