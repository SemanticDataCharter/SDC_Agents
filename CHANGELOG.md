# Changelog

All notable changes to SDC Agents will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
aligned with SDC Generation 4.

## Version Scheme

- **Major (4.x.x)**: SDC Generation 4 compatibility
- **Minor (4.X.x)**: New agents, tools, or connector types
- **Patch (4.x.X)**: Bug fixes, documentation updates, minor enhancements

---

## [Unreleased]

### Changed
- **Architecture revision: MCP-first → ADK-native** — Agents are now ADK `LlmAgent` instances with scoped `BaseToolset` implementations. Tools are Python functions wrapped in `FunctionTool` with type hints and docstrings (ADK derives schemas from these). MCP is retained as a secondary compatibility export via `adk_to_mcp_tool_type`.
- D1 decision revised: "No orchestration — SDC provides primitives only" → "ADK-native orchestration with MCP compatibility"
- Success criterion 6 updated: "MCP tool interfaces compatible with major frameworks" → "ADK-native with MCP compatibility layer"
- Tool specifications rewritten as Python function signatures with type hints and docstrings

### Added
- Repository scaffolding (README, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, CHANGELOG)
- Product Requirements Document (`docs/dev/SDC_AGENTS_PRD.md`)
- ADK runner configuration example showing agent instantiation and composition
- `OpenAPIToolset` integration for Catalog API (auto-generated from SDCStudio's drf-yasg spec)
- `BaseToolset` pattern: `CatalogToolset`, `IntrospectToolset`, `MappingToolset`, `GeneratorToolset`, `ValidationToolset`, `DistributionToolset`
- Shared `AuditLogger` class (append-only `.sdc-cache/audit.jsonl`)
- Agent-to-agent handoff via `ToolContext.actions.transfer_to_agent`
- ADK `AuthCredential` pattern for Validation Agent VaaS token
- MCP Export section documenting secondary MCP server interface
- ADK Integration Page deliverable (Phase 4) — contribute to `google/adk-docs` integrations directory
- Component Assembly Design Document (`docs/dev/COMPONENT_ASSEMBLY_DESIGN.md`)
- Design decisions D3–D9 for Phase 5 component assembly architecture:
  - D3: Reference components by `ct_id`, never copy — reuse across models and domains
  - D4: Fully autonomous pipeline — no human-in-the-loop, published output
  - D5: Assembly API authentication via API key → Modeler user → default project
  - D6: SDC_Agents proposes Cluster labels from data source analysis
  - D7: Contextual components discovered from SDCStudio's Default project library
  - D8: Arbitrarily complex nested Cluster hierarchies
  - D9: Intelligence on both sides — agents analyze, SDCStudio assembles
- **Knowledge Agent** (Phase 5) — ingests customer-side contextual resources (data dictionaries, PDFs, ontologies) into `.sdc-cache/knowledge/`
- **Component Assembly Agent** (Phase 5) — discovers catalog components, proposes Cluster hierarchy, calls SDCStudio Assembly API, produces fully published data models
- `knowledge:` configuration section for customer context resources (CSV, PDF, JSON, TTL)
- `default_library_project` setting for contextual component discovery
- Assembly API key in credential isolation model
- Open questions O7–O10 (knowledge scope, assembly failures, matching intelligence, multi-source assembly)
- Success criterion 10: autonomous assembly pipeline end-to-end
- **ADK Ecosystem Integration alignment** — leverage existing ADK integrations instead of custom connectors:
  - MCP Toolbox for Databases as Introspect Agent SQL connector layer (30+ data sources)
  - ADK MongoDB integration for `introspect_mongodb` tool
  - ADK BigQuery and Spanner integrations for GCP-native introspection
  - Chroma (local) and Vertex AI RAG Engine (GCP) as Knowledge Agent vector store backends
  - `OpenAPIToolset` for Catalog API (already documented)
- **ADK Ecosystem Contribution** (Phase 4) — contribute SPARQL integration to `google/adk-docs`:
  - `adk-sparql-tools` — SPARQL 1.1 / Fuseki / GraphDB (fills gap: no triplestore integrations in ADK ecosystem)
  - ~~`adk-neo4j-tools`~~ — superseded by MCP Toolbox for Databases (Neo4j + Dgraph support)
- `introspect_mongodb` tool for Introspect Agent — MongoDB document schema analysis
- MongoDB BSON to SDC4 type mapping table
- `mongodb` and `bigquery` datasource type examples in configuration
- Knowledge Agent vector store backend configuration (chroma, vertex-ai-rag, qdrant, pinecone)
- ADK Ecosystem Integrations Used reference table in PRD
- **ADK API verification and corrections**:
  - `OpenAPIToolset` import path corrected to `google.adk.tools.openapi_tool.openapi_spec_parser.openapi_toolset`
  - `OpenAPIToolset` requires `spec_str`/`spec_dict` (no `spec_url` parameter); requires **OpenAPI 3.x** (not Swagger 2.0)
  - `AuthCredential` pattern clarified: custom `FunctionTool` wrappers manage credentials internally; `AuthCredential` is for `OpenAPIToolset` integration
  - `LlmAgent` `description` parameter added to all agents (required for `transfer_to_agent` routing)
  - `LongRunningFunctionTool` specified for batch operations in PRD (deferred — all batch tools use regular `FunctionTool` in implementation)
  - `DatabaseSessionService` noted as production alternative to `InMemorySessionService`
- **Observability** (Phase 4) — Google Cloud Trace, OpenTelemetry export, Phoenix, MLflow
- Vertex AI Search referenced for Phase 5 semantic component discovery
- MCP stateful connection scalability constraint documented
- **Phase 1 implementation** — three working agents with shared infrastructure (consumer-first, no live SDCStudio dependency):
  - `pyproject.toml` — hatchling build with google-adk, pydantic, pyyaml, httpx, sqlalchemy deps
  - `sdc_agents.common.config` — Pydantic config models with YAML loader and `${VAR}` env substitution (fail-closed)
  - `sdc_agents.common.audit` — `AuditLogger` append-only JSONL with automatic credential redaction (connection/token/key/password/secret)
  - `sdc_agents.common.cache` — `CacheManager` with path helpers for schemas/ontologies/introspections/mappings
  - `sdc_agents.toolsets.catalog` — `CatalogToolset(BaseToolset)` with 5 tools, httpx async client, cache-first for immutable schemas
  - `sdc_agents.toolsets.introspect` — `IntrospectToolset(BaseToolset)` with 2 tools, SELECT-only SQL regex enforcement, CSV type inference (boolean/integer/decimal/date/datetime/time/email/URL/UUID/string)
  - `sdc_agents.toolsets.mapping` — `MappingToolset(BaseToolset)` with 3 tools, TYPE_COMPATIBILITY matrix, name similarity scoring, persist/list
  - `sdc_agents.agents.catalog` — `create_catalog_agent()` factory → `LlmAgent` with `CatalogToolset`
  - `sdc_agents.agents.introspect` — `create_introspect_agent()` factory → `LlmAgent` with `IntrospectToolset`
  - `sdc_agents.agents.mapping` — `create_mapping_agent()` factory → `LlmAgent` with `MappingToolset`
  - 68 tests (92% coverage) including security isolation: SQL write rejection, datasource name enforcement, tool scope isolation
  - Mock fixtures matching SDCStudio serializer shapes via `httpx.MockTransport`

### Completed — Phase 1: Core Agents
- Project scaffolding (Python package, per-agent ADK `BaseToolset` + `LlmAgent` definitions)
- Shared `AuditLogger` library (append-only JSON lines)
- YAML configuration loader with env var substitution
- **Catalog Agent**: `CatalogToolset` with `catalog_list_schemas`, `catalog_get_schema`, `catalog_download_skeleton`, `catalog_download_schema_rdf`, `catalog_download_ontologies`
- **Introspect Agent**: `IntrospectToolset` with `introspect_sql` (SQLAlchemy async, SELECT-only), `introspect_csv` (type inference)
- **Mapping Agent**: `MappingToolset` with `mapping_suggest`, `mapping_confirm`, `mapping_list`
- Unit tests for all tools (68 tests, 92% coverage)
- Security tests: tool scope isolation, SQL write rejection, datasource name enforcement

### Completed — Phase 2: Generation and Validation
- **Generator Agent**: `GeneratorToolset` with `generate_instance`, `generate_batch`, `generate_preview` — skeleton-based XML generation with placeholder substitution and optional element pruning
- **Validation Agent**: `ValidationToolset` with `validate_instance`, `sign_instance`, `validate_batch` — VaaS API integration with path confinement, token auth, artifact package (.pkg.zip) support
- **Introspect Agent extensions**: 2→4 tools — `introspect_json` (JSONPath extraction), `introspect_mongodb` (BSON-to-SDC4 type mapping)
- Config additions: `api_key`, `toolbox_url`, `jsonpath`, `database`, `collection`
- Cache additions: `skeleton_path()`, `field_mapping_path()`
- Dependencies: motor>=3.6, jsonpath-ng>=1.6, mongomock (dev), toolbox-adk (optional)
- 115 tests (47 new), 2 skipped. Security: 5 toolsets disjoint, path confinement, token redaction
- Implementation: regular `FunctionTool` for batch (not `LongRunningFunctionTool`), httpx `MockTransport` for VaaS

### Completed — Phase 3: Artifact Package and Distribution
- **Distribution Agent**: `DistributionToolset` with `inspect_package`, `list_destinations`, `distribute_package`, `distribute_batch`, `bootstrap_triplestore`
- `DestinationConfig` Pydantic model (fuseki, graphdb, neo4j, rest_api, filesystem types) + `destinations` dict on `SDCAgentsConfig`
- Fuseki/GraphDB triplestore connector (SPARQL Graph Store Protocol PUT, idempotent bootstrap via ASK query)
- Neo4j HTTP API connector (transactional endpoint POST)
- REST API connector (configurable POST/PUT with custom headers)
- Filesystem connector (path pattern substitution with optional directory creation)
- Destination health checks (`list_destinations` with per-destination connectivity probes)
- httpx-only connectors — no neo4j-driver dependency; per-artifact failure isolation
- 143 tests (28 new), 2 skipped. Security: 6 toolsets disjoint (5+4+3+3+3+5 = 23 total tools), Distribution path confinement, destination credential redaction
- Implementation: regular `FunctionTool` for batch (not `LongRunningFunctionTool`), httpx `MockTransport` for all connectors

### Planned — Phase 4: Production Hardening
- PyPI packaging (`pip install sdc-agents`)
- MCP export adapters (per-agent MCP server mode)
- ADK Integration Page contribution to `google/adk-docs`
- **ADK Ecosystem Contribution** to `google/adk-docs` integrations directory:
  - `adk-sparql-tools` — SPARQL 1.1 / Fuseki / GraphDB (no triplestore integration exists in ADK ecosystem)
  - ~~`adk-neo4j-tools`~~ — superseded by MCP Toolbox for Databases (Neo4j + Dgraph support)
- Docker images (one per agent)
- GitHub Actions CI/CD
- Comprehensive documentation and example configurations

### Planned — Phase 5: Component Assembly and Knowledge (Future)
- **Knowledge Agent**: `KnowledgeToolset` — ingest data dictionaries, PDFs, glossaries, ontologies into knowledge index (Chroma local / Vertex AI RAG Engine managed)
- **Component Assembly Agent**: `AssemblyToolset` — analyze data sources, discover matching catalog components, propose Cluster hierarchies, call SDCStudio Assembly API
- Fully autonomous: published, generated data model output — no human-in-the-loop (D4)
- Components referenced by `ct_id`, never copied (D3)
- Contextual components (Audit, Attestation, Party, etc.) from Default project library (D7)
- SDCStudio dependency: `POST /api/v1/dmgen/assemble/` endpoint

---

## Links

- [Repository](https://github.com/SemanticDataCharter/SDC_Agents)
- [Issue Tracker](https://github.com/SemanticDataCharter/SDC_Agents/issues)
- [Discussions](https://github.com/SemanticDataCharter/SDC_Agents/discussions)
- [SDC Ecosystem](https://github.com/SemanticDataCharter)

---

*For security-related changes, see [SECURITY.md](SECURITY.md)*

*For contribution guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md)*
