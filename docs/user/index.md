# SDC Agents User Documentation

SDC Agents is an open-source suite of nine purpose-scoped agents built on Google's [Agent Development Kit (ADK)](https://google.github.io/adk-docs/) for **design time**: they read a customer's existing data sources (SQL databases, BigQuery, MongoDB collections, CSV and JSON files) and help build SDC4 model components and models in SDCStudio.

For installation and quick start, see the [README](../../README.md#quick-start).

> **Not for operational ingest.** SDC Agents are not the path for a customer's live data. In production, data reaches Governed Data Records through ETL you build into the application SDCStudio generates from a published model: a Django app stack (PostgreSQL; Lightweight adds Apache Fuseki, Enterprise adds GraphDB) or a Supabase kit (TypeScript, with a `gate` Edge Function through which every record is stored; no graph database yet). See SDCStudio's [App Generation guide](https://github.com/Axius-SDC/SDCStudio/blob/main/docs/user-guides/app-generation.md).

---

## Building a Model

The primary path: from a data source to a published model in SDCStudio.

```
 Customer data source (read-only)        Customer context files
              │                                    │
              ▼                                    ▼
   ┌────────────────────┐              ┌────────────────────┐
   │ Introspect Agent   │              │ Knowledge Agent    │
   │ (6 tools)          │              │ (3 tools)          │
   │ structure, types,  │              │ local vector index │
   │ constraints        │              │ of dictionaries,   │
   └─────────┬──────────┘              │ glossaries, TTL    │
             │                         └─────────┬──────────┘
             ▼                                   ▼
   .sdc-cache/introspections/          .sdc-cache/knowledge/
   (structure only)
             │
             │      ┌────────────────────┐   ┌──────────────────────────┐
             │      │ Catalog Agent      │   │ Semantic Discovery Agent │
             │      │ (7 tools)          │   │ (1 tool, ADK-only)       │
             │      │ published models   │   │ Vertex AI Search         │
             │      └─────────┬──────────┘   └──────────────────────────┘
             │                ▼
             │      .sdc-cache/schemas/
             ├────────────────┤
             ▼                ▼
   ┌────────────────────┐   ┌──────────────────────────────┐
   │ Mapping Agent      │   │ Assembly Agent (4 tools)     │
   │ (3 tools)          │   │ discover reusable components,│
   │ column → component │   │ propose Cluster hierarchy,   │
   │ suggestions        │   │ select contextual components,│
   └────────────────────┘   │ assemble_model               │
                            └──────────────┬───────────────┘
                                           ▼
                              SDCStudio Assembly API
                     (creates new components, publishes the model)
```

1. **Introspect** the source. Only structure reaches the cache and the audit log; sample values go back to the caller and nowhere else.
2. **Gather context.** The Knowledge Agent indexes the customer's own documents for `query_knowledge`; the Semantic Discovery Agent searches a Vertex AI Search data store. Their answers inform the conversation; no tool feeds them into assembly automatically.
3. **Suggest mappings.** `mapping_suggest` ranks components of a cached published model for each column by type compatibility and name similarity; `mapping_confirm` saves the chosen mapping.
4. **Assemble.** `discover_components` searches the published catalog for reusable components, `propose_cluster_hierarchy` arranges matches (and unmatched columns, as components to create) into Clusters, and `assemble_model` posts the tree to the Assembly API. SDCStudio **publishes** the model: synchronously when every component is reused, or as a background task when new components must be created.

## Testing a Model with Sample Records

Optional, once a model is published.

```
Catalog Agent    catalog_download_skeleton   → .sdc-cache/skeletons/
Mapping Agent    mapping_confirm             → .sdc-cache/mappings/
Generator Agent  generate_preview / _batch   → ./output/*.xml
Validation Agent validate_instance / _batch  → valid / errors per record
```

The Generator reads **CSV or JSON files only** (or a record passed in directly) and re-reads the whole file for every record, so it suits a handful of test records, not loading data. Validation is local and free, against the model's published XSD.

## Development Triplestore

The Distribution Agent's `bootstrap_triplestore` loads the SDC4 ontologies and a model's schema RDF into a Fuseki or GraphDB instance you configure, for exploring a model's semantics while you build it. Its package tools (`inspect_package`, `distribute_package`, `distribute_batch`) are **deprecated**, with removal planned for 4.6.0: they read `.pkg.zip` packages that nothing produces since the validation service (VaaS) was retired.

Each agent communicates through **files on disk** (the `.sdc-cache/` directory and `./output/`), not direct calls. Every handoff is an inspectable, version-controllable artifact.

---

## Security Model

1. **No agent has both datasource access and network access.** The Introspect Agent reads your data but has no network. The Catalog, Validation and Assembly Agents access SDCStudio but never touch your datasources. The Semantic Discovery Agent accesses GCP Vertex AI Search but never touches datasources. The Generator reads a datasource file but has no network.
2. **Read-only datasource access.** SQL queries are restricted to a single SELECT on a read-only connection. CSV and JSON files are read, never modified. MongoDB access uses `find()` only.
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
├── knowledge/
│   └── {source_name}.json   # Knowledge source metadata (Knowledge Agent)
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
| **[Agent & Tool Reference](tool-reference.md)** | All 35 tools across 9 agents — parameters, return shapes, access scopes |
| **[MCP Integration](mcp-integration.md)** | Serve agents as MCP servers for Claude Desktop, Cursor, and generic stdio clients |
| **[Common Workflows](workflows.md)** | Step-by-step guides: building a model from a datasource, testing it with sample records, audit troubleshooting, development triplestore |

---

## External References

- [README — Quick Start](../../README.md#quick-start)
- [Product Requirements Document](../dev/SDC_AGENTS_PRD.md)
- [Contributing Guide](../../CONTRIBUTING.md)
- [Security Policy](../../SECURITY.md)
- [Changelog](../../CHANGELOG.md)
