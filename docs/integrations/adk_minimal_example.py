"""Minimal ADK integration example — SDC Agents + BigQuery.

Demonstrates composing ADK data access tools with SDC governance
toolsets in a single agent. The agent can introspect a BigQuery table,
find matching SDC4 schemas, and map columns to published components.

Prerequisites:
    pip install sdc-agents google-adk
    export SDC_API_KEY="your-sdcstudio-api-key"
    export GCP_PROJECT_ID="your-gcp-project"

Usage:
    python adk-minimal-example.py
"""

import asyncio

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.catalog import CatalogToolset
from sdc_agents.toolsets.introspect import IntrospectToolset
from sdc_agents.toolsets.mapping import MappingToolset


def build_agent() -> LlmAgent:
    """Build an agent that combines data introspection with schema governance."""
    config = SDCAgentsConfig(
        sdcstudio={
            "base_url": "https://sdcstudio.com",
            "api_key": "${SDC_API_KEY}",
        },
        datasources={
            "warehouse": {
                "type": "csv",
                "path": "../data/lab_results.csv",
            },
        },
        cache={"root": ".sdc-cache"},
        audit={"path": ".sdc-cache/audit.jsonl"},
    )

    return LlmAgent(
        name="data_governance_agent",
        model="gemini-2.0-flash",
        description="Introspects data sources and maps them to SDC4 schemas.",
        instruction=(
            "You help data engineers govern their data. When asked about a "
            "datasource, introspect it to discover columns and types, then "
            "search the SDC4 catalog for matching schemas. Map columns to "
            "schema components and report the mapping with confidence scores."
        ),
        tools=[
            IntrospectToolset(config=config),
            CatalogToolset(config=config),
            MappingToolset(config=config),
        ],
    )


async def main():
    agent = build_agent()
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name="sdc-demo", session_service=session_service)

    session = await session_service.create_session(app_name="sdc-demo", user_id="demo-user")

    print("SDC Data Governance Agent ready.")
    print("Try: 'Introspect the warehouse datasource and find matching schemas.'\n")

    while True:
        user_input = input("You: ").strip()
        if not user_input or user_input.lower() in ("exit", "quit"):
            break

        content = runner.gen_content_async(
            user_id="demo-user",
            session_id=session.id,
            new_message=user_input,
        )
        async for event in content:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(f"Agent: {part.text}")


if __name__ == "__main__":
    asyncio.run(main())
