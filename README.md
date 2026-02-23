# SDC Agents

**Purpose-scoped MCP agents for producing SDC4-compliant data artifacts from existing datastores.**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![SDC4](https://img.shields.io/badge/SDC-Generation_4-green.svg)](https://github.com/SemanticDataCharter/SDCRM)

---

## What is SDC Agents?

SDC Agents is an open-source suite of **six purpose-scoped MCP (Model Context Protocol) agents** that transform data from SQL databases, CSV files, and JSON sources into validated, multi-format SDC4 artifacts — without requiring the user to write XML, RDF, or GQL by hand.

Each agent has narrowly defined tool access, auditable activity, and enforced isolation boundaries. No single agent can reach across scope boundaries — a compromised or misbehaving agent has blast radius limited to its purpose.

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
3. **Tools are declarative** — described in MCP schema; no arbitrary code execution
4. **Structured audit log** — every tool call logged with agent, tool, inputs, outputs, timestamp
5. **No credential sharing** — each agent has its own credential scope
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

- **Catalog API** (public, no auth) — schema discovery, component trees, skeleton templates, schema-level RDF, reference ontologies
- **VaaS API** (token auth) — XML validation, signing, artifact package generation

See [docs/dev/SDC_AGENTS_PRD.md](docs/dev/SDC_AGENTS_PRD.md) for the full API contract and agent specifications.

---

## Quick Start

> **Note**: SDC Agents is in active development. The instructions below describe the target workflow.

### Prerequisites

- Python 3.11+
- Access to a published SDC4 schema on an SDCStudio instance

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

### Usage (MCP)

Each agent is a standalone MCP server. Point your MCP client (Claude, LangChain, or any MCP-compatible framework) at the agent you need:

```bash
# Start the Catalog Agent MCP server
sdc-agents serve catalog

# Start the Introspect Agent MCP server
sdc-agents serve introspect
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
| **Phase 1** | Catalog, Introspect, and Mapping agents | Planned |
| **Phase 2** | Generator and Validation agents (end-to-end flow) | Planned |
| **Phase 3** | VaaS artifact packages + Distribution Agent | Planned |
| **Phase 4** | Production hardening, PyPI, Docker images | Planned |

---

## Related Projects

- **[SDCStudio](https://github.com/Axius-SDC/SDCStudio)** — SDC4 data model creation and management platform (provides Catalog and VaaS APIs)
- **[SDCRM](https://github.com/SemanticDataCharter/SDCRM)** — SDC4 Reference Model specification
- **[Form2SDCTemplate](https://github.com/SemanticDataCharter/Form2SDCTemplate)** — PDF/DOCX to SDC template conversion

---

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
