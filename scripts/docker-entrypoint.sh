#!/bin/sh
set -e

# Docker entrypoint for SDC Agents.
# Dispatches based on SDC_AGENT env var or passes args to the CLI.

if [ $# -gt 0 ]; then
    # Arguments provided — pass them directly to the CLI
    exec sdc-agents --config "$SDC_AGENTS_CONFIG" "$@"
elif [ -n "$SDC_AGENT" ]; then
    # No args but SDC_AGENT is set — serve that agent as MCP
    exec sdc-agents --config "$SDC_AGENTS_CONFIG" serve --mcp "$SDC_AGENT"
else
    echo "Usage: set SDC_AGENT env var or pass CLI arguments."
    echo ""
    echo "  SDC_AGENT mode (serve a single agent as MCP server):"
    echo "    docker run -e SDC_AGENT=catalog -v ./config.yaml:/home/sdc/sdc-agents.yaml:ro IMAGE"
    echo ""
    echo "  CLI mode (pass any sdc-agents subcommand):"
    echo "    docker run -v ./config.yaml:/home/sdc/sdc-agents.yaml:ro IMAGE info"
    echo "    docker run -v ./config.yaml:/home/sdc/sdc-agents.yaml:ro IMAGE validate-config"
    echo ""
    echo "Available agents: catalog, introspect, mapping, generator, validation, distribution"
    exit 1
fi
