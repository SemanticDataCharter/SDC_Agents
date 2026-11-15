# SDC Agents

**Purpose-scoped ADK agents that read your existing data sources and help you build SDC4 model components and models in SDCStudio.**

[![PyPI](https://img.shields.io/pypi/v/sdc-agents.svg)](https://pypi.org/project/sdc-agents/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![SDC4](https://img.shields.io/badge/SDC-Generation_4-green.svg)](https://github.com/SemanticDataCharter/SDCRM)

![SDC Agents — The key to SDCStudio's self-assembling semantic infrastructure](SDC_Agents_Key.png)

---

## What is SDC Agents?

SDC Agents is an open-source suite of **nine purpose-scoped agents** built on Google's [Agent Development Kit (ADK)](https://google.github.io/adk-docs/) for **design time**: building SDC4 data models in [SDCStudio](https://github.com/Axius-SDC/SDCStudio) from the data sources a customer already has. The agents:

1. **Introspect structure.** Read the structure of SQL databases, BigQuery, MongoDB collections, CSV and JSON files (read-only; sample values go back to the caller but are stripped from the cache and audit log).
2. **Gather context.** Index the customer's data dictionaries, glossaries and ontologies (Knowledge Agent), and search a Vertex AI Search data store for SDC4 resources (Semantic Discovery Agent).
3. **Suggest mappings.** Rank published SDC4 components for each column by type compatibility and name similarity.
4. **Assemble models.** Find reusable catalog components, propose a Cluster hierarchy, and call SDCStudio's Assembly API, which creates any new components and **publishes** the data model.

The instance tools (Generator and Validation agents) produce **sample records for testing a model**: they fill the model's XML skeleton from a few rows of a CSV or JSON file and validate the result against the published schema.

> **Not for operational ingest.** SDC Agents are not the path for a customer's live data. In production, data reaches Governed Data Records through ETL you build into the application SDCStudio generates from a published model: a Django app stack (PostgreSQL; Lightweight adds Apache Fuseki, Enterprise adds GraphDB) or a Supabase kit (TypeScript, where every record goes through a `gate` Edge Function; no graph database yet). See SDCStudio's [App Generation guide](https://github.com/Axius-SDC/SDCStudio/blob/main/docs/user-guides/app-generation.md).

Each agent is an ADK `LlmAgent` with a narrowly scoped `BaseToolset`, auditable activity, and enforced isolation boundaries. No single agent can reach across scope boundaries — a compromised or misbehaving agent has blast radius limited to its purpose.

**MCP compatibility**: Each toolset can also be exported as an MCP server for framework-agnostic integration with non-ADK clients.

---

## Architecture: Nine Agents

| Agent | Purpose | Network | Datasource Access |
|---|---|---|---|
| **Catalog Agent** | Discover published SDC4 schemas and download artifacts from SDCStudio | HTTPS (optional token auth) | None |
| **Introspect Agent** | Examine customer datasources and extract structure (read-only) | None | Read-only |
| **Mapping Agent** | Suggest and manage column-to-component mappings | None | None |
| **Generator Agent** | Produce sample SDC4 XML records from a CSV or JSON file, for testing a model | None | Read-only |
| **Validation Agent** | Validate sample records locally against their published schemas; settle an exchange on the Verifiable Settlement Layer for a signed receipt | HTTPS (public catalog for schemas; token auth for settlement) | None |
| **Distribution Agent** | Load SDC4 ontologies and schema RDF into a development triplestore; check destination connectivity (package tools deprecated) | Configured destinations only | None |
| **Knowledge Agent** | Index customer context (CSV, JSON, TTL, Markdown, PDF, DOCX) into a local vector store | None | Read-only (files) |
| **Assembly Agent** | Discover reusable components, propose Cluster hierarchies, assemble and publish models through the Assembly API | HTTPS (Assembly API) | None |
| **Semantic Discovery Agent** | Search Vertex AI Search for SDC4 resources (ADK-only) | GCP (Vertex AI Search) | None |

### Security Principles

1. **No agent has both datasource access and network access**
2. **Read-only datasource access** — no agent can write to customer data
3. **Tools are declarative Python functions** — ADK derives schemas from type hints and docstrings
4. **Structured audit log** — every tool call logged with agent, tool, inputs, outputs, timestamp
5. **No credential sharing** — each `BaseToolset` receives only its own credential scope
6. **Fail closed** — errors are returned, never retried with escalated privileges

### IEEE 7000-2021 Alignment

SDC Agents is designed consistent with [IEEE 7000-2021](https://standards.ieee.org/ieee/7000/6781/) Value-based Engineering principles for ethical autonomous system design:

- **Transparency** — append-only structured audit log records every tool invocation with agent, tool, inputs, outputs, timestamp, and duration
- **Traceability** — all inter-agent handoffs are inspectable files on disk (`.sdc-cache/`), not opaque in-memory calls
- **Harm minimization** — purpose-scoped isolation ensures no single agent can access both customer datasources and external networks; blast radius is confined to each agent's scope
- **Stakeholder value preservation** — SDC4's curated, constraint-based semantic model (`xsd:restriction` only, immutable schemas) encodes data integrity and endurance as system-level guarantees, not optional features

### Data Flow

Agents communicate through **files on disk**, not direct calls. Every handoff is an inspectable, version-controllable artifact.

**Building a model (the primary path):**

```
Introspect Agent  → .sdc-cache/introspections/   (structure only)
Knowledge Agent   → .sdc-cache/knowledge/        (local vector index)
Catalog Agent     → .sdc-cache/schemas/          (published models to match against)
                          ▼
Mapping Agent     → .sdc-cache/mappings/         (column → component suggestions)
                          ▼
Assembly Agent    → SDCStudio Assembly API       (creates components, publishes the model)
```

**Testing a published model with sample records (optional):**

```
Catalog Agent     → .sdc-cache/skeletons/        (the model's XML skeleton)
Generator Agent   → ./output/*.xml               (a few rows of a CSV or JSON file)
Validation Agent  → pass/fail per record         (local, against the published XSD)
```

The generator reads **CSV or JSON files only** (not SQL, MongoDB or BigQuery), and it re-reads and re-parses the whole file for every record it writes, so a batch of *n* rows reads the file *n* times. That is fine for a handful of sample records and unsuited to bulk loading, which is not what it is for (see *Not for operational ingest* above).

---

## SDCStudio API Dependencies

SDC Agents consumes three sets of endpoints from [SDCStudio](https://github.com/Axius-SDC/SDCStudio):

- **Catalog API** (public, optional token auth) — schema discovery, component trees, skeleton templates, schema-level RDF and XSD, reference ontologies, wallet balance (token)
- **Assembly API** (token auth) — `POST /api/v1/dmgen/assemble/`: create any new components, build and **publish** the data model, and return it (decision D4 in [COMPONENT_ASSEMBLY_DESIGN.md](docs/dev/COMPONENT_ASSEMBLY_DESIGN.md))
- **Verifiable Settlement Layer** (token auth) — `POST /api/v1/vsl/settle`: validate, govern and sign one exchange; returns a Settlement Receipt (1,000 credits). Validation itself is local, with [sdcvalidator](https://pypi.org/project/sdcvalidator/) against the schema from the catalog, and free.

> **Authenticated Catalog Lookups**: When an API key is provided, catalog search results are filtered according to the Modeler's project preferences configured in SDCStudio. If the Modeler's `prj_filter` setting is enabled (the default), results are scoped to their default project. Without an API key, the catalog returns all published public schemas. This means the same `catalog_list_schemas` tool returns personalized results for authenticated users and broad results for anonymous browsing, with no change to the tool interface.

See [docs/dev/SDC_AGENTS_PRD.md](docs/dev/SDC_AGENTS_PRD.md) for the full API contract and agent specifications.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Google ADK 1.28.1+ (`pip install google-adk`), the floor set by CVE-2026-4810

### Installation

SDC_Agents needs **its own environment**. It depends on `google-adk`, which
SDCStudio deliberately removed during the 2026-08 AI-stack modernization
because its pin cascade was holding other packages back and blocking
Dependabot. Running these tests in the SDCStudio environment fails on a missing
ADK; running them in an unrelated environment gives a mismatched ADK and a wall
of environmental failures.

```bash
conda env create -f environment.yml
conda activate SDC_Agents
pip install -e ".[dev]"
```

Or without conda:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

The `dev` extra pulls BigQuery, because the BigQuery introspection tests are
part of the suite.

```bash
pytest -q          # 450 passed, 2 skipped
```

### Configuration

Copy `sdc-agents.example.yaml` to `sdc-agents.yaml` and fill in values:

```yaml
sdcstudio:
  base_url: "https://sdcstudio.example.com"
  api_key: "${SDC_API_KEY}"          # SDCStudio API key (catalog preferences, assembly, settlement, wallet)

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

# Optional: a development triplestore for bootstrap_triplestore
destinations:
  dev_triplestore:
    type: fuseki
    endpoint: "${FUSEKI_URL}"
    auth: "${FUSEKI_AUTH}"
```

Environment variables use `${VAR}` syntax. Missing variables cause an immediate `KeyError` (fail closed).

### Usage (ADK — Primary)

```python
from sdc_agents.common.config import load_config
from sdc_agents.agents.introspect import create_introspect_agent
from sdc_agents.agents.knowledge import create_knowledge_agent
from sdc_agents.agents.catalog import create_catalog_agent
from sdc_agents.agents.mapping import create_mapping_agent
from sdc_agents.agents.assembly import create_assembly_agent
from sdc_agents.agents.generator import create_generator_agent
from sdc_agents.agents.validation import create_validation_agent

config = load_config("sdc-agents.yaml")

# Each factory returns an LlmAgent with its scoped BaseToolset
# Design time: build and publish a model
introspect_agent = create_introspect_agent(config)
knowledge_agent = create_knowledge_agent(config)
catalog_agent = create_catalog_agent(config)
mapping_agent = create_mapping_agent(config)
assembly_agent = create_assembly_agent(config)

# Optional: sample records for testing the published model
generator_agent = create_generator_agent(config)
validation_agent = create_validation_agent(config)
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

# Any of the 8 MCP agents: assembly, catalog, distribution, generator, introspect, knowledge, mapping, validation
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

A single image serves all 8 MCP-servable agents. Select the agent at runtime with `SDC_AGENT`:

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

CI runs `ruff check`, then `black --check`, then `pytest`, across Python 3.11,
3.12 and 3.13. Run the formatters before pushing or the lint step fails on
whitespace.

### Releasing

**Two steps, and the second one is silent if you forget it.** Merging to `main`
publishes the Docker image, because `docker.yml` triggers on pushes to `main`.
It does **not** publish to PyPI. `release.yml` triggers on a **tag**:

```bash
# after the PR is merged and main carries the new version
git checkout main && git pull
git tag -a v4.4.1 -m "4.4.1"   # must match `version` in pyproject.toml
git push origin v4.4.1
```

The tag push builds and publishes to PyPI via trusted publishing. A merge with
no tag looks like a successful release and ships nothing, which is exactly what
happened with 4.4.1 before this note existed.

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
| **Phase 3** | Distribution Agent with multi-destination delivery | **Complete** (package delivery deprecated: nothing produces packages since VaaS was retired) |
| **Phase 4** | Production hardening: CLI, Docker, CI/CD, MCP export, documentation | **Complete** |
| **Phase 5** | Knowledge Agent + Component Assembly Agent | **Complete** |
| **Phase 5.5** | PDF/DOCX Knowledge Sources + Semantic Discovery Agent | **Complete** |
| **Phase 6** | ADK ecosystem contributions (`adk-sparql-tools`, Integration Page) | **Complete** |

### What's Implemented

**Common infrastructure**:
- Pydantic config with `${VAR}` substitution (fail closed), append-only JSONL audit logger with credential redaction, cache manager with path helpers

**CatalogToolset** (7 tools): `catalog_list_schemas`, `catalog_get_schema`, `catalog_download_schema_rdf`, `catalog_download_schema_xsd`, `catalog_download_skeleton`, `catalog_download_ontologies`, `catalog_check_wallet` — httpx async, cache-first for immutable schemas, optional token auth for Modeler-scoped results

**IntrospectToolset** (6 tools): `introspect_sql` (read-only SELECT enforcement), `introspect_sql_schema` (catalog metadata via SQLAlchemy's inspector), `introspect_csv` (type inference for 10 types), `introspect_json` (JSONPath extraction), `introspect_mongodb` (BSON-to-SDC4 type mapping), `introspect_bigquery` (BigQuery schema extraction via `asyncio.to_thread`)

**MappingToolset** (3 tools): `mapping_suggest` (type compatibility + name similarity), `mapping_confirm`, `mapping_list`

**GeneratorToolset** (3 tools): `generate_instance`, `generate_batch`, `generate_preview` — sample records for testing a model: skeleton-based XML generation with placeholder substitution and optional element pruning. Reads CSV or JSON files only (or a record passed in directly), and re-reads the whole file for each row

**ValidationToolset** (3 tools): `validate_instance`, `settle_instance`, `validate_batch` — local validation with sdcvalidator (the instance's `dm-<ct_id>` names the schema, fetched once from the public catalog), recover mode, settlement on the Verifiable Settlement Layer with the receipt written beside the record, path confinement

**DistributionToolset** (5 tools): `bootstrap_triplestore` (load SDC4 ontologies and schema RDF into Fuseki or GraphDB, idempotent), `list_destinations` (connectivity check); deprecated, removal planned for 4.7.0: `inspect_package`, `distribute_package`, `distribute_batch`, which route `.pkg.zip` packages that nothing produces since the validation service (VaaS) was retired

**KnowledgeToolset** (3 tools): `ingest_knowledge_source`, `query_knowledge`, `list_indexed_sources` — local Chroma vector store

**AssemblyToolset** (4 tools): `discover_components`, `propose_cluster_hierarchy`, `select_contextual_components`, `assemble_model` — catalog-first component reuse; `assemble_model` posts to the Assembly API, which publishes the model (synchronously when every component is reused, as a background task when some must be created)

**SemanticDiscoveryToolset** (1 tool, ADK-only): `vertex_ai_search`

**Agent factories**: one `create_<name>_agent()` per agent in `sdc_agents.agents`

**9 toolsets with 35 disjoint tools** — security isolation tests (SQL write rejection, datasource name enforcement, path confinement, credential redaction, no cross-scope tool leakage)

**Consumer-first**: all tests use `httpx.MockTransport` — zero live SDCStudio, Fuseki, or Neo4j dependency

---

## Related Projects

- **[SDCStudio](https://github.com/Axius-SDC/SDCStudio)** — SDC4 data model creation and management platform (provides the Catalog and Assembly APIs and the Verifiable Settlement Layer; generates the app stacks and Supabase kits that carry operational data)
- **[SDCRM](https://github.com/SemanticDataCharter/SDCRM)** — SDC4 Reference Model specification
- **[Form2SDCTemplate](https://github.com/SemanticDataCharter/Form2SDCTemplate)** — PDF/DOCX to SDC template conversion
- **[Google ADK](https://google.github.io/adk-docs/)** — Agent Development Kit (agent framework)

---

## License & Ownership

Copyright 2025-2026 [Axius SDC, Inc.](https://axius-sdc.github.io)

Licensed under the Apache License 2.0 — see [LICENSE](LICENSE) for details.

SDC Agents is controlled and maintained by Axius SDC, Inc. The [SemanticDataCharter](https://github.com/SemanticDataCharter) GitHub organization hosts the open-source SDC4 ecosystem on behalf of Axius SDC, Inc.
