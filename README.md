# SDC Agents

**Purpose-scoped ADK agents for producing SDC4-compliant data artifacts from existing datastores.**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![SDC4](https://img.shields.io/badge/SDC-Generation_4-green.svg)](https://github.com/SemanticDataCharter/SDCRM)

---

## What is SDC Agents?

SDC Agents is an open-source suite of **six purpose-scoped agents** built on Google's [Agent Development Kit (ADK)](https://google.github.io/adk-docs/) that transform data from SQL databases, CSV files, and JSON sources into validated, multi-format SDC4 artifacts — without requiring the user to write XML, RDF, or GQL by hand.

Each agent is an ADK `LlmAgent` with a narrowly scoped `BaseToolset`, auditable activity, and enforced isolation boundaries. No single agent can reach across scope boundaries — a compromised or misbehaving agent has blast radius limited to its purpose.

**MCP compatibility**: Each toolset can also be exported as an MCP server for framework-agnostic integration with non-ADK clients.

---

## Architecture: Six Agents

| Agent | Purpose | Network | Datasource Access |
|---|---|---|---|
| **Catalog Agent** | Discover published SDC4 schemas and download artifacts from SDCStudio | HTTPS (no auth) | None |
| **Introspect Agent** | Examine customer datasources and extract structure (read-only) | None | Read-only |
| **Mapping Agent** | Suggest and manage column-to-component mappings | None | None |
| **Generator Agent** | Produce SDC4 XML instances from mapped data | None | Read-only |
| **Validation Agent** | Validate and sign XML instances via VaaS API | HTTPS (token auth) | None |
| **Distribution Agent** | Route artifact packages to customer-local destinations | Customer-local only | None |

### Security Principles

1. **No agent has both datasource access and network access**
2. **Read-only datasource access** — no agent can write to customer data
3. **Tools are declarative Python functions** — ADK derives schemas from type hints and docstrings
4. **Structured audit log** — every tool call logged with agent, tool, inputs, outputs, timestamp
5. **No credential sharing** — each `BaseToolset` receives only its own credential scope
6. **Fail closed** — errors are returned, never retried with escalated privileges

### Data Flow

Agents communicate through **files on disk**, not direct calls. Every handoff is an inspectable, version-controllable artifact:

```
Catalog Agent → .sdc-cache/schemas/     ─┐
Introspect Agent → .sdc-cache/introspections/ ─┤
                                               ▼
                                    Mapping Agent → .sdc-cache/mappings/
                                               ▼
                                    Generator Agent → ./sdc-output/*.xml
                                               ▼
                                    Validation Agent → ./sdc-output/*.pkg.zip
                                               ▼
                                    Distribution Agent → customer destinations
```

---

## SDCStudio API Dependencies

SDC Agents consumes two sets of endpoints from [SDCStudio](https://github.com/Axius-SDC/SDCStudio):

- **Catalog API** (public, no auth) — schema discovery, component trees, skeleton templates, schema-level RDF, reference ontologies. The Catalog Agent uses ADK's `OpenAPIToolset` to auto-generate bindings from SDCStudio's existing OpenAPI spec.
- **VaaS API** (token auth) — XML validation, signing, artifact package generation

See [docs/dev/SDC_AGENTS_PRD.md](docs/dev/SDC_AGENTS_PRD.md) for the full API contract and agent specifications.

---

## Quick Start

> **Note**: SDC Agents is in active development. The instructions below describe the target workflow.

### Prerequisites

- Python 3.11+
- Access to a published SDC4 schema on an SDCStudio instance
- Google ADK (`pip install google-adk`)

### Installation

```bash
pip install sdc-agents
```

### Configuration

Create `sdc-agents.yaml` in your project directory:

```yaml
sdcstudio:
  base_url: "https://sdcstudio.com"
  api_key: "${SDC_API_KEY}"        # Validation Agent only

datasources:
  my_database:
    type: sql
    connection: "${DB_URL}"

output:
  directory: "./sdc-output"
```

### Usage (ADK — Primary)

```python
from sdc_agents.config import load_config
from sdc_agents.toolsets.catalog import CatalogToolset
from google.adk.agents import LlmAgent

config = load_config("sdc-agents.yaml")

catalog_agent = LlmAgent(
    name="catalog",
    model="gemini-2.0-flash",
    instruction="Discover published SDC4 schemas and download artifacts.",
    tools=CatalogToolset(config=config).get_tools(),
)
```

### Usage (MCP — Secondary)

Each agent can also be served as an MCP server for non-ADK clients:

```bash
# Start the Catalog Agent as an MCP server
sdc-agents serve --mcp catalog

# Start the Introspect Agent as an MCP server
sdc-agents serve --mcp introspect
```

### Usage (CLI)

```bash
# List published schemas
sdc-agents catalog list

# Introspect a datasource
sdc-agents introspect my_database

# Suggest mappings
sdc-agents mapping suggest --schema <ct_id> --datasource my_database
```

---

## Documentation

- **[Product Requirements](docs/dev/SDC_AGENTS_PRD.md)** — full agent specifications, tools, security model, type mapping tables
- **[Contributing](CONTRIBUTING.md)** — development setup, coding standards, PR workflow
- **[Security Policy](SECURITY.md)** — vulnerability reporting, agent isolation model
- **[Changelog](CHANGELOG.md)** — release history

---

## Implementation Phases

| Phase | Goal | Status |
|---|---|---|
| **Phase 1** | Catalog, Introspect, and Mapping agents (ADK BaseToolset + LlmAgent) | Planned |
| **Phase 2** | Generator and Validation agents, OpenAPIToolset integration | Planned |
| **Phase 3** | VaaS artifact packages + Distribution Agent | Planned |
| **Phase 4** | Production hardening, PyPI, MCP export adapters, ADK Integration Page | Planned |
| **Phase 5** | Component Assembly Agent (future — create-and-consume) | Future |

---

## Related Projects

- **[SDCStudio](https://github.com/Axius-SDC/SDCStudio)** — SDC4 data model creation and management platform (provides Catalog and VaaS APIs)
- **[SDCRM](https://github.com/SemanticDataCharter/SDCRM)** — SDC4 Reference Model specification
- **[Form2SDCTemplate](https://github.com/SemanticDataCharter/Form2SDCTemplate)** — PDF/DOCX to SDC template conversion
- **[Google ADK](https://google.github.io/adk-docs/)** — Agent Development Kit (agent framework)

---

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
