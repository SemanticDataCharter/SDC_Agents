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

### Prerequisites

- Python 3.11+
- Google ADK 1.25+ (`pip install google-adk`)

### Installation

```bash
pip install -e ".[dev]"
```

### Configuration

Copy `sdc-agents.example.yaml` to `sdc-agents.yaml` and fill in values:

```yaml
sdcstudio:
  base_url: "https://sdcstudio.example.com"
  api_key: "${SDC_API_KEY}"          # VaaS token (Validation Agent only)

cache:
  root: ".sdc-cache"
  ttl_hours: 24

audit:
  path: ".sdc-cache/audit.jsonl"
  log_level: "standard"    # "standard" summarizes outputs; "verbose" logs full payloads

datasources:
  my_database:
    type: sql
    connection_string: "${DB_CONNECTION}"   # env var substitution
  my_csv:
    type: csv
    path: "/data/exports/records.csv"

output:
  directory: "./output"
  formats:
    - "xml"

destinations:
  triplestore:
    type: fuseki
    endpoint: "${FUSEKI_URL}"
    auth: "${FUSEKI_AUTH}"
  graph_database:
    type: neo4j
    endpoint: "${NEO4J_URL}"
    database: "sdc4"
  archive:
    type: filesystem
    path: "./archive/{ct_id}/{instance_id}/"
    create_directories: true
```

Environment variables use `${VAR}` syntax. Missing variables cause an immediate `KeyError` (fail closed).

### Usage (ADK — Primary)

```python
from sdc_agents.common.config import load_config
from sdc_agents.agents.catalog import create_catalog_agent
from sdc_agents.agents.introspect import create_introspect_agent
from sdc_agents.agents.mapping import create_mapping_agent
from sdc_agents.agents.generator import create_generator_agent
from sdc_agents.agents.validation import create_validation_agent
from sdc_agents.agents.distribution import create_distribution_agent

config = load_config("sdc-agents.yaml")

# Each factory returns an LlmAgent with its scoped BaseToolset
catalog_agent = create_catalog_agent(config)
introspect_agent = create_introspect_agent(config)
mapping_agent = create_mapping_agent(config)
generator_agent = create_generator_agent(config)
validation_agent = create_validation_agent(config)
distribution_agent = create_distribution_agent(config)
```

Or construct agents directly with toolsets:

```python
from sdc_agents.common.config import load_config
from sdc_agents.toolsets.catalog import CatalogToolset
from google.adk.agents import LlmAgent

config = load_config("sdc-agents.yaml")

catalog_agent = LlmAgent(
    name="catalog",
    model="gemini-2.0-flash",
    description="Discovers SDC4 schemas from SDCStudio Catalog API.",
    instruction="Discover published SDC4 schemas and download artifacts.",
    tools=[CatalogToolset(config=config)],
)
```

### Usage (MCP — Secondary)

Each agent can be served as an MCP stdio server for non-ADK clients:

```bash
# Start the Catalog Agent as an MCP server
sdc-agents serve --mcp catalog

# Start the Introspect Agent as an MCP server
sdc-agents serve --mcp introspect

# Any of the 6 agents: catalog, distribution, generator, introspect, mapping, validation
sdc-agents serve --mcp validation
```

### CLI Commands

```bash
# Show configuration summary and agent inventory
sdc-agents info
sdc-agents info --config path/to/sdc-agents.yaml

# Validate a config file (useful in CI)
sdc-agents validate-config
sdc-agents validate-config --config path/to/sdc-agents.yaml

# Inspect the audit log
sdc-agents audit show                        # last 50 records
sdc-agents audit show --agent catalog        # filter by agent
sdc-agents audit show --last 24h --limit 20  # recent records
sdc-agents audit show --audit-path ./logs/audit.jsonl  # custom path
```

### Docker

A single image serves all 6 agents. Select the agent at runtime with `SDC_AGENT`:

```bash
# Serve a single agent as an MCP server
docker run -v ./sdc-agents.yaml:/home/sdc/sdc-agents.yaml:ro \
  -e SDC_AGENT=catalog \
  ghcr.io/semanticdatacharter/sdc-agents

# Run any CLI command
docker run -v ./sdc-agents.yaml:/home/sdc/sdc-agents.yaml:ro \
  ghcr.io/semanticdatacharter/sdc-agents info

docker run -v ./sdc-agents.yaml:/home/sdc/sdc-agents.yaml:ro \
  ghcr.io/semanticdatacharter/sdc-agents validate-config
```

Build locally:

```bash
docker build -t sdc-agents .
docker run sdc-agents  # prints usage hint
```

### CI/CD

- **CI** (`.github/workflows/ci.yml`): Runs on push to `dev` and PRs to `main`. Lints with ruff, checks formatting with black, runs pytest with coverage across Python 3.11/3.12/3.13.
- **Docker** (`.github/workflows/docker.yml`): Builds and pushes to GHCR on push to `main` and `v*` tags.
- **PyPI** (`.github/workflows/release.yml`): Publishes to PyPI on `v*` tags via OIDC trusted publisher (no API tokens).

**One-time setup** (maintainer):
1. Configure [PyPI trusted publisher](https://docs.pypi.org/trusted-publishers/) — owner: `SemanticDataCharter`, repo: `SDC_Agents`, workflow: `release.yml`, environment: `pypi`
2. Create a `pypi` environment in GitHub repo settings (Settings > Environments)

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=sdc_agents

# Run specific test modules
pytest tests/toolsets/test_catalog.py
pytest tests/security/
```

---

## Documentation

- **[User Documentation](docs/user/index.md)** — configuration, tool reference, MCP integration, workflow guides
- **[Product Requirements](docs/dev/SDC_AGENTS_PRD.md)** — full agent specifications, tools, security model, type mapping tables
- **[Contributing](CONTRIBUTING.md)** — development setup, coding standards, PR workflow
- **[Security Policy](SECURITY.md)** — vulnerability reporting, agent isolation model
- **[Changelog](CHANGELOG.md)** — release history

---

## Implementation Phases

| Phase | Goal | Status |
|---|---|---|
| **Phase 1** | Catalog, Introspect, and Mapping agents with shared infra | **Complete** |
| **Phase 2** | Generator and Validation agents, Introspect extensions | **Complete** |
| **Phase 3** | Distribution Agent with multi-destination delivery | **Complete** |
| **Phase 4** | Production hardening: CLI, Docker, CI/CD, MCP export, documentation | **Complete** |
| **Phase 5** | Knowledge Agent + Component Assembly Agent | Future |
| **Phase 6** | ADK ecosystem contributions (`adk-sparql-tools`, Integration Page) | Future |

### What's Implemented (Phases 1–3)

**Common infrastructure**:
- Pydantic config with `${VAR}` substitution (fail closed), append-only JSONL audit logger with credential redaction, cache manager with path helpers

**CatalogToolset** (5 tools): `catalog_list_schemas`, `catalog_get_schema`, `catalog_download_schema_rdf`, `catalog_download_skeleton`, `catalog_download_ontologies` — httpx async, cache-first for immutable schemas

**IntrospectToolset** (5 tools): `introspect_sql` (SELECT-only enforcement), `introspect_csv` (type inference for 10 types), `introspect_json` (JSONPath extraction), `introspect_mongodb` (BSON-to-SDC4 type mapping), `introspect_bigquery` (BigQuery schema extraction via `asyncio.to_thread`)

**MappingToolset** (3 tools): `mapping_suggest` (type compatibility + name similarity), `mapping_confirm`, `mapping_list`

**GeneratorToolset** (3 tools): `generate_instance`, `generate_batch`, `generate_preview` — skeleton-based XML generation with placeholder substitution and optional element pruning

**ValidationToolset** (3 tools): `validate_instance`, `sign_instance`, `validate_batch` — VaaS API with path confinement, token auth, artifact package (.pkg.zip) support

**DistributionToolset** (5 tools): `inspect_package`, `list_destinations`, `distribute_package`, `distribute_batch`, `bootstrap_triplestore` — httpx-only connectors for SPARQL Graph Store, Neo4j HTTP, REST API, and filesystem

**Agent factories**: `create_catalog_agent()`, `create_introspect_agent()`, `create_mapping_agent()`, `create_generator_agent()`, `create_validation_agent()`, `create_distribution_agent()`

**159 tests, 82% coverage** — 6 toolsets with 24 disjoint tools, security isolation tests (SQL write rejection, datasource name enforcement, path confinement, credential redaction, no cross-scope tool leakage)

**Consumer-first**: all tests use `httpx.MockTransport` — zero live SDCStudio, Fuseki, or Neo4j dependency

---

## Related Projects

- **[SDCStudio](https://github.com/Axius-SDC/SDCStudio)** — SDC4 data model creation and management platform (provides Catalog and VaaS APIs)
- **[SDCRM](https://github.com/SemanticDataCharter/SDCRM)** — SDC4 Reference Model specification
- **[Form2SDCTemplate](https://github.com/SemanticDataCharter/Form2SDCTemplate)** — PDF/DOCX to SDC template conversion
- **[Google ADK](https://google.github.io/adk-docs/)** — Agent Development Kit (agent framework)

---

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
