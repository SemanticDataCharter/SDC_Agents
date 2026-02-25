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

---

## Coexistence with Platform MCP Servers

SDC Agents' MCP servers run alongside MCP servers from other platforms in the same client. This lets you query data from Databricks, Snowflake, or other sources and produce SDC4 artifacts in a single session — each server provides its own tools, the client sees them all.

### Claude Desktop: SDC Agents + Snowflake

Snowflake publishes a managed MCP server that exposes Cortex Analyst (NL-to-SQL), Cortex Search (semantic search), and direct SQL execution. Configure it alongside SDC Agents so Claude can query Snowflake data and then map, generate, and validate SDC4 artifacts:

```json
{
  "mcpServers": {
    "snowflake": {
      "command": "npx",
      "args": [
        "-y", "@anthropic-ai/mcp-client",
        "--transport", "sse",
        "--url", "https://<account>.snowflakecomputing.com/api/v2/databases/<db>/schemas/<schema>/mcp-servers/<server_name>"
      ],
      "env": {
        "SNOWFLAKE_TOKEN": "<your-oauth-token>"
      }
    },
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

With this configuration, a typical session might look like:

1. Use Snowflake's `SYSTEM_EXECUTE_SQL` tool to explore table structure
2. Use SDC Agents' `catalog_list_schemas` to find a matching SDC4 schema
3. Use `introspect_sql` (pointing at Snowflake via SQLAlchemy) to extract column metadata
4. Use `mapping_suggest` and `mapping_confirm` to map columns to schema components
5. Use `generate_batch` to produce XML instances
6. Use `validate_batch` to validate and sign
7. Use `distribute_batch` to deliver to destinations

### Claude Desktop: SDC Agents + Databricks

Databricks publishes a `databricks-mcp` server that exposes Unity Catalog functions, Genie (NL-to-SQL), DBSQL, and Vector Search. Install it alongside SDC Agents:

```bash
pip install databricks-mcp
```

```json
{
  "mcpServers": {
    "databricks": {
      "command": "databricks-mcp",
      "args": ["--profile", "DEFAULT"],
      "env": {
        "DATABRICKS_HOST": "https://adb-1234567890.12.azuredatabricks.net",
        "DATABRICKS_TOKEN": "<your-personal-access-token>"
      }
    },
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

### Cursor: SDC Agents + Platform MCP Servers

The same pattern applies to `.cursor/mcp.json`. Add the platform server entry alongside the SDC Agents entries:

```json
{
  "mcpServers": {
    "databricks": {
      "command": "databricks-mcp",
      "args": ["--profile", "DEFAULT"]
    },
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

### How It Works

MCP clients (Claude Desktop, Cursor, Claude Code) manage each server as an independent process. There is no conflict between servers — each exposes its own tool namespace:

| Server | Tool Namespace | What It Provides |
|---|---|---|
| Snowflake MCP | `CORTEX_ANALYST_MESSAGE`, `SYSTEM_EXECUTE_SQL`, ... | Query and explore Snowflake data |
| Databricks MCP | Unity Catalog functions, Genie, DBSQL, Vector Search | Query and explore Databricks data |
| SDC Agents (6 servers) | `catalog_*`, `introspect_*`, `mapping_*`, `generate_*`, `validate_*`, `distribute_*`, ... | Semantic modeling, validation, distribution |

The platform MCP servers handle data access and exploration. SDC Agents handles everything after: schema discovery, column mapping, XML generation, validation, signing, and multi-destination distribution.

### Two Paths for Data Access

When using SDC Agents alongside a platform MCP server, you have two ways to get data into the pipeline:

1. **Direct via `introspect_sql`** — Configure the platform as a `sql` datasource in `sdc-agents.yaml` (see [Cloud Data Platforms](configuration.md#cloud-data-platforms)). The Introspect Agent queries the platform directly through SQLAlchemy.

2. **Platform MCP for exploration, SDC Agents for modeling** — Use the platform's MCP tools to explore and understand your data interactively, then use SDC Agents' tools to build the formal SDC4 artifacts. This is useful when you need the platform's specialized capabilities (Genie NL-to-SQL, Cortex Search, Vector Search) before committing to a mapping.

Both paths produce the same output: validated SDC4 artifacts in `.sdc-cache/` and `./output/`.
