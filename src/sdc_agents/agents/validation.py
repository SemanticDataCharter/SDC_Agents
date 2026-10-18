"""Validation Agent factory: local SDC4 validation and settlement on the VSL."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.validation import ValidationToolset


def create_validation_agent(
    config: SDCAgentsConfig,
    model: str = "gemini-2.0-flash",
) -> LlmAgent:
    """Create a Validation Agent for SDC4 XML instance validation.

    The agent validates instances locally with sdcvalidator against the
    model's published schema (free, offline once the schema is cached) and
    settles an exchange on the Verifiable Settlement Layer when a signed
    receipt is needed.

    Args:
        config: SDC Agents configuration.
        model: LLM model identifier.

    Returns:
        Configured LlmAgent with ValidationToolset.
    """
    return LlmAgent(
        name="validation_agent",
        model=model,
        description=(
            "Validates SDC4 XML instances locally against their published "
            "schemas, reports structural and semantic errors, recovers "
            "semantic errors with ExceptionalValues, and settles an exchange "
            "on the Verifiable Settlement Layer for a signed receipt."
        ),
        instruction=(
            "You are the Validation Agent. Your job is to validate SDC4 XML "
            "instances and, when asked, settle an exchange.\n\n"
            "You can:\n"
            "- Validate XML instances locally against their published schemas "
            "(the instance's own dm-<ct_id> names the schema)\n"
            "- Batch validate all XML files in the output directory\n"
            "- Use 'recover' mode to keep an invalid value and flag it with an "
            "ExceptionalValue instead of discarding it\n"
            "- Settle one exchange on the Verifiable Settlement Layer, which "
            "costs 1,000 credits and returns a signed Settlement Receipt\n\n"
            "You CANNOT:\n"
            "- Access datasources (SQL, CSV, etc.)\n"
            "- Generate or modify XML instances\n"
            "- Access files outside the configured output directory\n"
            "- Modify schemas or mappings\n"
            "- Fund the wallet: report a 402 to the person and stop\n\n"
            "Validation is free; settle only when the user asks for a receipt. "
            "Always check the error list even when validation succeeds."
        ),
        tools=[ValidationToolset(config=config)],
    )
