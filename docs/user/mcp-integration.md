# MCP Integration

Each SDC Agents toolset can be served as an [MCP](https://modelcontextprotocol.io/) stdio server, allowing non-ADK clients to use the tools. The `sdc-agents serve --mcp <agent>` command converts ADK `FunctionTool` instances to MCP tool types via `adk_to_mcp_tool_type()` and serves them over stdio.

---

## Claude Desktop

### pip install variant

1. Install SDC Agents:

   ```bash
   pip install sdc-agents
   ```

2. Create your config file at `~/sdc-agents.yaml` (see [Configuration Reference](configuration.md)).

3. Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

   ```json
   {
     "mcpServers": {
       "sdc-catalog": {
         "command": "sdc-agents",
         "args": ["--config", "/path/to/sdc-agents.yaml", "serve", "--mcp", "catalog"]
       },
       "sdc-introspect": {
         "command": "sdc-agents",
         "args": ["--config", "/path/to/sdc-agents.yaml", "serve", "--mcp", "introspect"]
       },
       "sdc-mapping": {
         "command": "sdc-agents",
         "args": ["--config", "/path/to/sdc-agents.yaml", "serve", "--mcp", "mapping"]
       },
       "sdc-generator": {
         "command": "sdc-agents",
         "args": ["--config", "/path/to/sdc-agents.yaml", "serve", "--mcp", "generator"]
       },
       "sdc-validation": {
         "command": "sdc-agents",
         "args": ["--config", "/path/to/sdc-agents.yaml", "serve", "--mcp", "validation"]
       },
       "sdc-distribution": {
         "command": "sdc-agents",
         "args": ["--config", "/path/to/sdc-agents.yaml", "serve", "--mcp", "distribution"]
       }
     }
   }
   ```

4. Restart Claude Desktop. The agent's tools appear in the tool list.

### Docker variant

```json
{
  "mcpServers": {
    "sdc-catalog": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-v", "/path/to/sdc-agents.yaml:/home/sdc/sdc-agents.yaml:ro",
        "-e", "SDC_AGENT=catalog",
        "ghcr.io/semanticdatacharter/sdc-agents"
      ]
    }
  }
}
```

For datasource access (CSV/JSON files), mount the data directory:

```json
{
  "mcpServers": {
    "sdc-introspect": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-v", "/path/to/sdc-agents.yaml:/home/sdc/sdc-agents.yaml:ro",
        "-v", "/path/to/data:/data:ro",
        "-e", "SDC_AGENT=introspect",
        "ghcr.io/semanticdatacharter/sdc-agents"
      ]
    }
  }
}
```

---

## Cursor

Add to `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "sdc-catalog": {
      "command": "sdc-agents",
      "args": ["serve", "--mcp", "catalog"]
    },
    "sdc-introspect": {
      "command": "sdc-agents",
      "args": ["serve", "--mcp", "introspect"]
    },
    "sdc-mapping": {
      "command": "sdc-agents",
      "args": ["serve", "--mcp", "mapping"]
    },
    "sdc-generator": {
      "command": "sdc-agents",
      "args": ["serve", "--mcp", "generator"]
    },
    "sdc-validation": {
      "command": "sdc-agents",
      "args": ["serve", "--mcp", "validation"]
    },
    "sdc-distribution": {
      "command": "sdc-agents",
      "args": ["serve", "--mcp", "distribution"]
    }
  }
}
```

If your config file is not in the current directory, add `"--config", "/path/to/sdc-agents.yaml"` before `"serve"` in each `args` array.

---

## Generic stdio Client

Any MCP client that supports stdio transport can connect:

```bash
# Start a single agent as an MCP server
sdc-agents serve --mcp catalog

# With explicit config path
sdc-agents --config /path/to/sdc-agents.yaml serve --mcp introspect
```

The server communicates via stdin/stdout using the MCP protocol. Stderr is used for status messages.

---

## Running Multiple Agents

Each `serve --mcp` invocation runs one agent as one MCP server process. To use multiple agents simultaneously, start separate processes:

```bash
# Terminal 1
sdc-agents serve --mcp catalog

# Terminal 2
sdc-agents serve --mcp introspect

# Terminal 3
sdc-agents serve --mcp mapping
```

In Claude Desktop or Cursor, each agent is configured as a separate `mcpServers` entry (as shown above). The client manages the lifecycle of each server process independently.

---

## Use-Case Matrix

Which agents to configure for common workflows:

| Workflow | Agents Needed |
|---|---|
| Browse published schemas | `catalog` |
| Explore a datasource | `introspect` |
| Map columns to schema components | `catalog` + `introspect` + `mapping` |
| Generate XML from CSV | `catalog` + `introspect` + `mapping` + `generator` |
| Full pipeline (generate + validate + distribute) | All 6 agents |
| Validate existing XML files | `validation` |
| Distribute existing packages | `distribution` |
| Bootstrap a triplestore | `catalog` + `distribution` |

---

## Tool Availability per Agent

When you connect an MCP server, the client sees only that agent's tools:

| MCP Server | Tools Exposed |
|---|---|
| `sdc-catalog` | `catalog_list_schemas`, `catalog_get_schema`, `catalog_download_schema_rdf`, `catalog_download_skeleton`, `catalog_download_ontologies` |
| `sdc-introspect` | `introspect_sql`, `introspect_csv`, `introspect_json`, `introspect_mongodb` |
| `sdc-mapping` | `mapping_suggest`, `mapping_confirm`, `mapping_list` |
| `sdc-generator` | `generate_instance`, `generate_batch`, `generate_preview` |
| `sdc-validation` | `validate_instance`, `sign_instance`, `validate_batch` |
| `sdc-distribution` | `inspect_package`, `list_destinations`, `distribute_package`, `distribute_batch`, `bootstrap_triplestore` |

For full tool documentation, see the [Agent & Tool Reference](tool-reference.md).
