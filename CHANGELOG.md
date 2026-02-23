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

### Added
- Repository scaffolding (README, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, CHANGELOG)
- Product Requirements Document (`docs/dev/SDC_AGENTS_PRD.md`)

### Planned — Phase 1: Core Agents
- Project scaffolding (Python package, per-agent MCP server entry points)
- Shared audit log library (append-only JSON lines)
- YAML configuration loader with env var substitution
- **Catalog Agent**: `catalog_list_schemas`, `catalog_get_schema`, `catalog_download_skeleton`, `catalog_download_schema_rdf`, `catalog_download_ontologies`
- **Introspect Agent**: `introspect_sql`, `introspect_csv`
- **Mapping Agent**: `mapping_suggest`, `mapping_confirm`, `mapping_list`
- Unit tests for all tools
- Security tests: verify agents cannot access out-of-scope resources

### Planned — Phase 2: Generation and Validation
- **Generator Agent**: `generate_instance`, `generate_batch`, `generate_preview`
- **Validation Agent**: `validate_instance`, `sign_instance`, `validate_batch`
- `introspect_json` tool for Introspect Agent
- CLI wrapper for non-MCP usage
- Integration tests against SDCStudio staging environment

### Planned — Phase 3: Artifact Package and Distribution
- **Distribution Agent**: `distribute_package`, `distribute_batch`, `list_destinations`, `inspect_package`, `bootstrap_triplestore`
- Fuseki/GraphDB triplestore connector
- Neo4j/Memgraph graph DB connector
- REST API and filesystem connectors
- Destination health checks

### Planned — Phase 4: Production Hardening
- PyPI packaging (`pip install sdc-agents`)
- MCP registry listings (one per agent)
- Docker images (one per agent)
- GitHub Actions CI/CD
- Comprehensive documentation and example configurations

---

## Links

- [Repository](https://github.com/SemanticDataCharter/SDC_Agents)
- [Issue Tracker](https://github.com/SemanticDataCharter/SDC_Agents/issues)
- [Discussions](https://github.com/SemanticDataCharter/SDC_Agents/discussions)
- [SDC Ecosystem](https://github.com/SemanticDataCharter)

---

*For security-related changes, see [SECURITY.md](SECURITY.md)*

*For contribution guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md)*
