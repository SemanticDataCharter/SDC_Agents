"""CLI entry point for sdc-agents.

Provides subcommands for serving agents as MCP servers, inspecting
audit logs, displaying configuration info, and validating config files.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from importlib import import_module
from pathlib import Path

import click

AGENT_REGISTRY: dict[str, tuple[str, str]] = {
    "assembly": ("sdc_agents.toolsets.assembly", "AssemblyToolset"),
    "catalog": ("sdc_agents.toolsets.catalog", "CatalogToolset"),
    "distribution": ("sdc_agents.toolsets.distribution", "DistributionToolset"),
    "generator": ("sdc_agents.toolsets.generator", "GeneratorToolset"),
    "introspect": ("sdc_agents.toolsets.introspect", "IntrospectToolset"),
    "knowledge": ("sdc_agents.toolsets.knowledge", "KnowledgeToolset"),
    "mapping": ("sdc_agents.toolsets.mapping", "MappingToolset"),
    "validation": ("sdc_agents.toolsets.validation", "ValidationToolset"),
}

_VALID_AGENTS = ", ".join(sorted(AGENT_REGISTRY))


def _load_toolset(agent_name: str, config):
    """Dynamically import and instantiate a toolset for the given agent."""
    module_path, class_name = AGENT_REGISTRY[agent_name]
    mod = import_module(module_path)
    cls = getattr(mod, class_name)
    return cls(config=config)


def _parse_duration(duration: str) -> timedelta:
    """Parse a duration string like '24h', '7d', '30m' into a timedelta."""
    match = re.fullmatch(r"(\d+)([hdm])", duration.strip().lower())
    if not match:
        raise click.BadParameter(
            f"Invalid duration '{duration}'. Use format like '24h', '7d', or '30m'."
        )
    value, unit = int(match.group(1)), match.group(2)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "d":
        return timedelta(days=value)
    return timedelta(minutes=value)


@click.group()
@click.option(
    "--config",
    default=None,
    envvar="SDC_AGENTS_CONFIG",
    type=click.Path(),
    help="Path to sdc-agents.yaml config file.  [default: sdc-agents.yaml]",
)
@click.pass_context
def main(ctx: click.Context, config: str | None) -> None:
    """SDC Agents — purpose-scoped ADK agents for SDC4 data operations."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config or "sdc-agents.yaml"


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--mcp",
    required=True,
    metavar="AGENT",
    help=f"Agent to serve as MCP server.  Valid: {_VALID_AGENTS}",
)
@click.pass_context
def serve(ctx: click.Context, mcp: str) -> None:
    """Start an agent toolset as an MCP stdio server."""
    if mcp not in AGENT_REGISTRY:
        raise click.ClickException(f"Unknown agent '{mcp}'. Valid agents: {_VALID_AGENTS}")

    from sdc_agents.common.config import load_config

    try:
        config = load_config(ctx.obj["config_path"])
    except (FileNotFoundError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc

    asyncio.run(_run_mcp_server(mcp, config))


async def _run_mcp_server(agent_name: str, config) -> None:
    """Set up and run an MCP stdio server for the given agent toolset."""
    from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent

    toolset = _load_toolset(agent_name, config)
    adk_tools = await toolset.get_tools()

    # Build lookup: MCP tool name → ADK FunctionTool
    adk_by_name = {t.name: t for t in adk_tools}
    mcp_tools = [adk_to_mcp_tool_type(t) for t in adk_tools]

    server = Server(f"sdc-agents-{agent_name}")

    @server.list_tools()
    async def list_tools():
        return mcp_tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        if name not in adk_by_name:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        func = adk_by_name[name]
        result = await func.run_async(args=arguments, tool_context=None)
        text = json.dumps(result, default=str) if not isinstance(result, str) else result
        return [TextContent(type="text", text=text)]

    click.echo(f"Serving {agent_name} agent via MCP stdio ({len(adk_tools)} tools)...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------


@main.group()
def audit() -> None:
    """Inspect the structured audit log."""


@audit.command("show")
@click.option("--agent", default=None, help="Filter by agent name.")
@click.option("--tool", default=None, help="Filter by tool name.")
@click.option(
    "--last", default=None, metavar="DURATION", help="Show records within duration (e.g. 24h, 7d)."
)
@click.option("--limit", default=50, show_default=True, help="Maximum records to display.")
@click.option(
    "--audit-path", default=None, type=click.Path(), help="Audit log path (overrides config)."
)
@click.pass_context
def audit_show(
    ctx: click.Context,
    agent: str | None,
    tool: str | None,
    last: str | None,
    limit: int,
    audit_path: str | None,
) -> None:
    """Display audit log records with optional filters."""
    # Resolve audit path
    log_path: str | None = audit_path
    if log_path is None:
        from sdc_agents.common.config import load_config

        try:
            config = load_config(ctx.obj["config_path"])
            log_path = config.audit.path
        except (FileNotFoundError, KeyError):
            log_path = ".sdc-cache/audit.jsonl"

    path = Path(log_path)
    if not path.exists():
        click.echo(f"No audit log found at {path}")
        return

    # Parse time filter
    cutoff: datetime | None = None
    if last is not None:
        try:
            delta = _parse_duration(last)
        except click.BadParameter as exc:
            raise click.ClickException(str(exc)) from exc
        cutoff = datetime.now(timezone.utc) - delta

    # Read and filter records
    records: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        if agent and record.get("agent") != agent:
            continue
        if tool and record.get("tool") != tool:
            continue
        if cutoff:
            ts_str = record.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts < cutoff:
                    continue
            except (ValueError, TypeError):
                continue

        records.append(record)

    if not records:
        click.echo("No matching audit records.")
        return

    # Display last N records
    for rec in records[-limit:]:
        click.echo("---")
        click.echo(f"  timestamp : {rec.get('timestamp', '?')}")
        click.echo(f"  agent     : {rec.get('agent', '?')}")
        click.echo(f"  tool      : {rec.get('tool', '?')}")
        click.echo(f"  duration  : {rec.get('duration_ms', '?')} ms")
        inputs = rec.get("inputs", {})
        if isinstance(inputs, dict):
            click.echo(f"  inputs    : {', '.join(inputs.keys()) or '(none)'}")
        else:
            click.echo(f"  inputs    : {inputs}")


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def info(ctx: click.Context) -> None:
    """Display configuration summary and agent inventory."""
    from sdc_agents.common.config import load_config

    config_path = ctx.obj["config_path"]
    try:
        config = load_config(config_path)
    except (FileNotFoundError, KeyError) as exc:
        raise click.ClickException(f"Cannot load config: {exc}") from exc

    click.echo(f"Config      : {config_path}")
    click.echo(f"Cache root  : {config.cache.root}")
    click.echo(f"Output dir  : {config.output.directory}")
    click.echo(f"Audit path  : {config.audit.path}")
    click.echo()

    # Agent inventory with tool counts
    click.echo("Agents (8):")
    tool_counts = {
        "assembly": 4,
        "catalog": 5,
        "distribution": 5,
        "generator": 3,
        "introspect": 5,
        "knowledge": 3,
        "mapping": 3,
        "validation": 3,
    }
    for name in sorted(AGENT_REGISTRY):
        count = tool_counts.get(name, "?")
        click.echo(f"  {name:16s} {count} tools")
    click.echo()

    # Datasources
    if config.datasources:
        click.echo(f"Datasources ({len(config.datasources)}):")
        for name, ds in config.datasources.items():
            click.echo(f"  {name:20s} type={ds.type}")
    else:
        click.echo("Datasources: (none)")
    click.echo()

    # Destinations
    if config.destinations:
        click.echo(f"Destinations ({len(config.destinations)}):")
        for name, dest in config.destinations.items():
            endpoint = dest.endpoint or dest.path or ""
            click.echo(f"  {name:20s} type={dest.type}  endpoint={endpoint}")
    else:
        click.echo("Destinations: (none)")


# ---------------------------------------------------------------------------
# validate-config
# ---------------------------------------------------------------------------


@main.command("validate-config")
@click.pass_context
def validate_config(ctx: click.Context) -> None:
    """Validate the configuration file and report errors."""
    from pydantic import ValidationError

    from sdc_agents.common.config import load_config

    config_path = ctx.obj["config_path"]
    try:
        load_config(config_path)
    except FileNotFoundError:
        click.echo(f"Error: config file not found: {config_path}", err=True)
        sys.exit(1)
    except KeyError as exc:
        click.echo(f"Error: missing environment variable: {exc}", err=True)
        sys.exit(1)
    except ValidationError as exc:
        click.echo(f"Error: config validation failed:\n{exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Config OK: {config_path}")
