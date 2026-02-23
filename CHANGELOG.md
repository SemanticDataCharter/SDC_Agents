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
- Phase 5 placeholder: Component Assembly Agent (future — create-and-consume)
- "Future: Component Assembly" scope boundary for post-Phase 4 schema creation capability

### Planned — Phase 1: Core Agents
- Project scaffolding (Python package, per-agent ADK `BaseToolset` + `LlmAgent` definitions)
- Shared `AuditLogger` library (append-only JSON lines)
- YAML configuration loader with env var substitution
- **Catalog Agent**: `CatalogToolset` with `catalog_list_schemas`, `catalog_get_schema`, `catalog_download_skeleton`, `catalog_download_schema_rdf`, `catalog_download_ontologies`
- **Introspect Agent**: `IntrospectToolset` with `introspect_sql`, `introspect_csv`
- **Mapping Agent**: `MappingToolset` with `mapping_suggest`, `mapping_confirm`, `mapping_list`
- Unit tests for all tools
- Security tests: verify agents cannot access out-of-scope resources

### Planned — Phase 2: Generation and Validation
- **Generator Agent**: `GeneratorToolset` with `generate_instance`, `generate_batch`, `generate_preview`
- **Validation Agent**: `ValidationToolset` with `validate_instance`, `sign_instance`, `validate_batch`
- `introspect_json` tool for `IntrospectToolset`
- `OpenAPIToolset` integration for Catalog API
- CLI wrapper for non-ADK usage
- Integration tests against SDCStudio staging environment

### Planned — Phase 3: Artifact Package and Distribution
- **Distribution Agent**: `DistributionToolset` with `distribute_package`, `distribute_batch`, `list_destinations`, `inspect_package`, `bootstrap_triplestore`
- Fuseki/GraphDB triplestore connector
- Neo4j/Memgraph graph DB connector
- REST API and filesystem connectors
- Destination health checks

### Planned — Phase 4: Production Hardening
- PyPI packaging (`pip install sdc-agents`)
- MCP export adapters (per-agent MCP server mode)
- ADK Integration Page contribution to `google/adk-docs`
- Docker images (one per agent)
- GitHub Actions CI/CD
- Comprehensive documentation and example configurations

### Planned — Phase 5: Component Assembly (Future)
- Component Assembly Agent — discover and assemble reusable catalog components into bespoke data models

---

## Links

- [Repository](https://github.com/SemanticDataCharter/SDC_Agents)
- [Issue Tracker](https://github.com/SemanticDataCharter/SDC_Agents/issues)
- [Discussions](https://github.com/SemanticDataCharter/SDC_Agents/discussions)
- [SDC Ecosystem](https://github.com/SemanticDataCharter)

---

*For security-related changes, see [SECURITY.md](SECURITY.md)*

*For contribution guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md)*
