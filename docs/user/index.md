# SDC Agents User Documentation

SDC Agents is an open-source suite of six purpose-scoped agents built on Google's [Agent Development Kit (ADK)](https://google.github.io/adk-docs/) that transform data from SQL databases, CSV files, JSON sources, and MongoDB collections into validated, multi-format SDC4 artifacts — without requiring the user to write XML, RDF, or GQL by hand.

For installation and quick start, see the [README](../../README.md#quick-start).

---

## Pipeline Overview

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│ Catalog Agent│     │ Introspect Agent │     │              │
│  (5 tools)   │     │    (5 tools)     │     │              │
│              │     │                  │     │              │
│ Discovers    │     │ Examines your    │     │ Mapping Agent│
│ published    │     │ datasources      │     │  (3 tools)   │
│ SDC4 schemas │     │ (read-only)      │     │              │
└──────┬───────┘     └────────┬─────────┘     │ Suggests     │
       │                      │               │ column →     │
       ▼                      ▼               │ component    │
  .sdc-cache/           .sdc-cache/           │ mappings     │
  schemas/              introspections/       └──────┬───────┘
       │                      │                      │
       └──────────┬───────────┘                      │
                  │                                  ▼
                  │                            .sdc-cache/
                  │                            mappings/
                  │                                  │
                  └──────────┬───────────────────────┘
                             ▼
                    ┌──────────────────┐
                    │ Generator Agent  │
                    │   (3 tools)      │
                    │                  │
                    │ Produces SDC4    │
                    │ XML instances    │
                    └────────┬─────────┘
                             │
                             ▼
                       ./output/*.xml
                             │
                             ▼
                    ┌──────────────────┐
                    │ Validation Agent │
                    │   (3 tools)      │
                    │                  │
                    │ Validates & signs│
                    │ via VaaS API     │
                    └────────┬─────────┘
                             │
                             ▼
                    ./output/*.pkg.zip
                             │
                             ▼
                    ┌────────────────────┐
                    │ Distribution Agent │
                    │    (5 tools)       │
                    │                    │
                    │ Routes packages to │
                    │ your destinations  │
                    └────────────────────┘
                             │
                     ┌───────┼───────┐
                     ▼       ▼       ▼
                  Fuseki   Neo4j  Filesystem
                  GraphDB  REST API
```

Each agent communicates through **files on disk** (the `.sdc-cache/` directory and `./output/`), not direct calls. Every handoff is an inspectable, version-controllable artifact.

---

## Security Model

1. **No agent has both datasource access and network access.** The Introspect Agent reads your data but has no network. The Catalog and Validation Agents access the network but never touch your datasources.
2. **Read-only datasource access.** SQL queries are restricted to SELECT. CSV and JSON files are read, never modified. MongoDB access uses `find()` only.
3. **Append-only audit log.** Every tool call is logged to `.sdc-cache/audit.jsonl` with agent name, tool name, inputs, outputs, timestamp, and duration. Credentials are automatically redacted.

---

## Cache Directory Structure

```
.sdc-cache/
├── audit.jsonl              # Append-only audit log
├── schemas/
│   └── dm-{ct_id}.json      # Cached schema details (immutable)
├── ontologies/
│   ├── *.rdf                # Downloaded ontology files
│   └── *.ttl
├── introspections/          # Introspection results
├── mappings/
│   └── {name}.json          # Confirmed column-to-component mappings
├── skeletons/
│   └── dm-{ct_id}.xml       # Downloaded XML skeleton templates
└── field_mappings/
    └── dm-{ct_id}.json      # Skeleton field → placeholder mappings
```

The cache root defaults to `.sdc-cache` but is configurable via the `cache.root` setting.

---

## Documentation Contents

| Document | Description |
|---|---|
| **[Configuration Reference](configuration.md)** | All config fields, annotated YAML, environment variable substitution, working examples |
| **[Agent & Tool Reference](tool-reference.md)** | All 24 tools across 6 agents — parameters, return shapes, access scopes |
| **[MCP Integration](mcp-integration.md)** | Serve agents as MCP servers for Claude Desktop, Cursor, and generic stdio clients |
| **[Common Workflows](workflows.md)** | Step-by-step guides: CSV to validated XML, audit troubleshooting, triplestore bootstrap |

---

## External References

- [README — Quick Start](../../README.md#quick-start)
- [Product Requirements Document](../dev/SDC_AGENTS_PRD.md)
- [Contributing Guide](../../CONTRIBUTING.md)
- [Security Policy](../../SECURITY.md)
- [Changelog](../../CHANGELOG.md)
