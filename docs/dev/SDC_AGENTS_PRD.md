# SDC Agents: Purpose-Scoped MCP Agents for SDC4 Data Operations

**Date**: 2026-02-23
**Status**: Draft
**Author**: Timothy W. Cook / Claude Code
**Repository**: `SemanticDataCharter/SDC_Agents` (Apache 2.0 License)
**Related**: SDCStudio `docs/dev/agentic-registry/SDCStudio_API_Agents_PRD.md` (SDCStudio-side enhancement spec)

---

## Executive Summary

### Problem

Organizations with existing datastores (SQL databases, JSON files, CSV exports) need to produce SDC4-compliant XML instances from their data. Today this requires manual schema study, hand-written mapping code, and bespoke validation scripts — a barrier to SDC4 adoption.

A single monolithic agent with broad access to datasources, file systems, and remote APIs creates an unacceptable trust surface. Customers handling sensitive data (healthcare, finance, government) need to know exactly what each agent can do, what it cannot do, and have a complete audit trail of every action.

### Solution

**SDC Agents** is an open-source suite of **purpose-scoped MCP agents**, each with narrowly defined tool access and auditable activity:

| Agent | Scope | Can Access | Cannot Access |
|---|---|---|---|
| **Catalog Agent** | Schema discovery + artifacts | SDCStudio Catalog API (read-only, no auth) | Datasources, file system, VaaS API |
| **Introspect Agent** | Datasource structure extraction | Customer datasources (read-only) | SDCStudio APIs, file system writes |
| **Mapping Agent** | Column-to-component mapping | Cached schemas + introspection results | Datasources directly, SDCStudio APIs |
| **Generator Agent** | XML instance generation | Mapping configs, datasource (read-only) | SDCStudio APIs, schema downloads |
| **Validation Agent** | Instance validation and signing | VaaS API (token auth), local XML files | Datasources, schema management |
| **Distribution Agent** | Artifact package routing | Unpacked artifact files, configured destinations | SDCStudio APIs, datasources |

Each agent is a standalone MCP server. An orchestrating agent or human operator composes them — but no single agent can reach across boundaries. A compromised or misbehaving agent has blast radius limited to its scope.

### Value Proposition

- **Least-privilege by design** — each agent has the minimum tools for its job
- **Auditable** — every MCP tool invocation is logged with inputs, outputs, and timestamps
- **Data residency by default** — four of six agents run entirely locally with no network access. Only the Catalog Agent (public schema reads) and Validation Agent (VaaS API) make outbound calls. See [Data Residency and VaaS Transit](#data-residency-and-vaas-transit) for the precise data handling model.
- **Composable** — use one agent, some agents, or all agents depending on need
- **Open source (Apache 2.0)** — customers can audit every line of code

### Security Principles

1. **No agent has both datasource access and network access** — the Introspect Agent reads data but cannot call APIs; the Validation Agent calls APIs but cannot read datasources
2. **Read-only datasource access** — no agent can write to, modify, or delete customer data
3. **Tools are declarative, not imperative** — tools describe what they do in their MCP schema; the agent cannot run arbitrary code
4. **Structured audit log** — every tool call writes a JSON audit record (agent, tool, inputs, outputs, timestamp, duration)
5. **No credential sharing** — each agent has its own credential scope; the Catalog Agent has no credentials; the Validation Agent has the VaaS API token; the Introspect Agent has datasource credentials
6. **Fail closed** — if an agent encounters an error, it returns the error; it does not retry, escalate privileges, or fall back to broader access

---

## Architecture

### Agent Isolation Model

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Customer Infrastructure                           │
│                                                                          │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────────────────┐       │
│  │  SQL / JSON  │   │  Mapping    │   │      XML Output         │       │
│  │  / CSV Data  │   │  Configs    │   │      Directory          │       │
│  └──────┬───────┘   └──────┬──────┘   └────────────┬────────────┘       │
│         │ read-only        │ read/write             │ read/write         │
│         ▼                  ▼                        ▼                    │
│  ┌─────────────┐   ┌─────────────┐   ┌──────────────────────────┐      │
│  │  Introspect │   │   Mapping   │   │     Generator Agent      │      │
│  │    Agent     │   │    Agent    │   │                          │      │
│  │             │   │             │   │  reads: mapping configs   │      │
│  │  tools: 3   │   │  tools: 3   │   │  reads: datasource       │      │
│  │  network: ✗ │   │  network: ✗ │   │  writes: XML files       │      │
│  │  writes: ✗  │   │  writes: ✓  │   │  network: ✗              │      │
│  └──────┬──────┘   │  (configs   │   │  tools: 3                │      │
│         │          │   only)     │   └────────────┬─────────────┘      │
│         │          └─────────────┘                │                      │
│         │                                         │                      │
│  ┌──────▼──────────────────────────────────────────▼───────────────────┐ │
│  │                     Audit Log (append-only)                         │ │
│  │   {agent, tool, inputs, outputs, timestamp, duration_ms}           │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌─────────────┐                          ┌──────────────────────────┐  │
│  │   Catalog   │──── HTTPS (no auth) ────▶│  SDCStudio               │  │
│  │    Agent    │                          │  Catalog API             │  │
│  │  tools: 5   │                          └──────────────────────────┘  │
│  │  network: ✓ │                                                        │
│  │  datasrc: ✗ │                          ┌──────────────────────────┐  │
│  └─────────────┘                          │  SDCStudio               │  │
│  ┌─────────────┐──── HTTPS (token) ──────▶│  VaaS API                │  │
│  │ Validation  │                          │                          │  │
│  │    Agent    │◀── artifact package ─────│  ?package=true returns   │  │
│  │  tools: 3   │    (.zip)                │  .zip with all formats   │  │
│  │  network: ✓ │                          └──────────────────────────┘  │
│  │  datasrc: ✗ │                                                        │
│  └──────┬──────┘                                                        │
│         │ writes .zip                                                    │
│         ▼                                                                │
│  ┌──────────────┐   ┌───────────────────────────────────────────────┐   │
│  │  Artifact    │   │  Customer Destinations                        │   │
│  │  Packages    │──▶│                                               │   │
│  │  (.zip)      │   │  ┌──────────┐ ┌────────┐ ┌───────┐ ┌──────┐ │   │
│  └──────┬───────┘   │  │ Fuseki / │ │ Neo4j /│ │ REST  │ │ File │ │   │
│         │ read-only │  │ GraphDB  │ │ GraphDB│ │ APIs  │ │System│ │   │
│         ▼           │  └──────────┘ └────────┘ └───────┘ └──────┘ │   │
│  ┌─────────────┐    └───────────────────────────────────────────────┘   │
│  │Distribution │──── writes to configured destinations only             │
│  │   Agent     │                                                        │
│  │  tools: 4   │                                                        │
│  │  network: ✓ │  (customer-local endpoints: triplestore, graph DB)     │
│  │  datasrc: ✗ │                                                        │
│  └─────────────┘                                                        │
└──────────────────────────────────────────────────────────────────────────┘
```

### Data Flow Between Agents

Agents communicate through **files on disk**, not direct calls. This makes every handoff inspectable:

```
Catalog Agent                    Introspect Agent
    │                                │
    ├─▶ .sdc-cache/schemas/          │
    │   {ct_id}_detail.json          ▼
    │   {ct_id}_skeleton.xml     .sdc-cache/introspections/{name}.json
    │   {ct_id}_field_mapping.json   │
    │   dm-{ct_id}.ttl               │
    │   dm-{ct_id}_shacl.ttl         │
    │   dm-{ct_id}.gql               │
    ├─▶ .sdc-cache/ontologies/       │
    │   sdc4.ttl, sdc4-meta.ttl      │
    │                                │
    └──────────┐  ┌──────────────────┘
               ▼  ▼
          Mapping Agent
               │
               ▼
    .sdc-cache/mappings/{name}.json
               │
               ▼
         Generator Agent
               │
               ▼
    ./sdc-output/{ct_id}_{index}.xml
               │
               ▼
       Validation Agent ──── VaaS API (?package=true) ────▶ SDCStudio
               │                                               │
               │◀───── artifact package (.zip) ────────────────┘
               │
               ▼
    ./sdc-output/{ct_id}_{index}.pkg.zip
               │
               ▼
       Distribution Agent
               │
               ├──▶ instance.json ──────▶ REST API / document store
               ├──▶ instance.ttl ───────▶ Fuseki / GraphDB (named graph)
               ├──▶ instance.gql ───────▶ Neo4j / property graph DB
               ├──▶ instance.jsonld ────▶ linked data endpoint
               └──▶ instance.signed.xml ▶ archive / compliance store
```

Every intermediate artifact is a human-readable file that can be inspected, version-controlled, or audited before the next agent touches it.

---

## SDCStudio API Endpoints Referenced

Only two agents make network calls. Their allowed endpoints are exhaustively listed.

### Catalog Agent (no authentication)

| Endpoint | Method | Purpose |
|---|---|---|
| `/llms.txt` | GET | Agent discovery — API docs, endpoint list |
| `/api/v1/catalog/dms/` | GET | List published data models (paginated, filterable) |
| `/api/v1/catalog/dm/{ct_id}/` | GET | Model detail — metadata, component tree, artifact URLs |
| `/api/v1/catalog/dm/{ct_id}/ttl/` | GET | Download schema-level RDF triples (Turtle) |
| `/api/v1/catalog/dm/{ct_id}/shacl/` | GET | Download SHACL shapes file |
| `/api/v1/catalog/dm/{ct_id}/gql/` | GET | Download GQL CREATE statements (schema-level) |
| `/api/v1/catalog/dm/{ct_id}/skeleton/` | GET | Download XML skeleton template + field mapping |
| `/api/v1/catalog/ontologies/` | GET | List available SDC4 reference ontologies |
| `/api/v1/catalog/ontologies/{name}/` | GET | Download a reference ontology file |

**The customer never needs the XSD.** The XSD is SDCStudio's internal concern — VaaS validates against it server-side. What the customer's agents need is:
- The **catalog detail response** with the component tree (names, types, hierarchy) — this tells the Mapping Agent what components exist and what SDC4 types they are
- The **XML skeleton + field mapping** — a pre-generated XML template with `__PLACEHOLDER__` tokens and a JSON field mapping that tells the Generator Agent exactly how to construct valid XML instances
- The **schema-level RDF** — component semantic metadata, ontology links, and type classifications for the triplestore
- The **reference ontologies** — vocabulary definitions that instance-level RDF triples reference

Fine-grained XSD constraints (min_length, max_length, enumerations, patterns) are enforced by VaaS at validation time. The Mapping Agent only needs to know "this component is an XdString" or "this component is an XdTemporal" to suggest type-compatible mappings.

> **Note**: Some of these endpoints require SDCStudio-side enhancements. See the [SDCStudio enhancement spec](https://github.com/Axius-SDC/SDCStudio/blob/main/docs/dev/agentic-registry/SDCStudio_API_Agents_PRD.md) for implementation details on the skeleton endpoint, individual artifact serving, ontology endpoint, and catalog detail serializer changes.

### Validation Agent (token authentication)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/vaas/validate/` | POST | Validate XML instance (modes: `report`, `recover`) |
| `/api/v1/vaas/validate/sign/` | POST | Validate + sign with XML-Sig (ECDSA P-256) |

Both endpoints accept an optional `?package=true` query parameter. When set, VaaS returns a zip artifact package instead of a single XML response.

No other endpoints are permitted. The agents have no general HTTP capability.

---

## Agent Specifications

### Agent 1: Catalog Agent

**Purpose**: Discover published SDC4 models and download schema-level RDF and reference ontologies from SDCStudio.

**Credential scope**: None (Catalog API is public).

**Network access**: HTTPS to configured SDCStudio base URL only.

**File access**: Write to `.sdc-cache/schemas/` and `.sdc-cache/ontologies/` only.

#### Tools

##### `catalog_list_schemas`

List published SDC4 data models.

| Field | Value |
|---|---|
| **Input** | `project` (string, optional): filter by project name; `search` (string, optional): text search |
| **Output** | Array of `{ct_id, title, description, project, artifact_urls}` |
| **API Call** | `GET /api/v1/catalog/dms/?project={project}&search={search}` |

##### `catalog_get_schema`

Get detailed metadata and component tree for a published model. The component tree tells the Mapping Agent what components exist, what SDC4 types they are, and how they're organized in Clusters.

| Field | Value |
|---|---|
| **Input** | `ct_id` (string, required): CUID2 identifier |
| **Output** | `{ct_id, title, description, project, components: [{name, type, ct_id, parent_cluster}], artifact_urls}` |
| **Side Effect** | Caches response to `.sdc-cache/schemas/{ct_id}_detail.json` |
| **API Call** | `GET /api/v1/catalog/dm/{ct_id}/` |

##### `catalog_download_schema_rdf`

Download and cache the schema-level RDF triples, SHACL shapes, and GQL for a published model. SDC4 schemas are immutable once published — the agent fetches them once and caches forever.

| Field | Value |
|---|---|
| **Input** | `ct_id` (string, required): CUID2 identifier; `formats` (array of enum: `ttl`, `shacl`, `gql`, default all three) |
| **Output** | `{ct_id, files: [{format, path, cached: bool}]}` |
| **Side Effect** | Saves to `.sdc-cache/schemas/dm-{ct_id}.ttl`, `.sdc-cache/schemas/dm-{ct_id}_shacl.ttl`, `.sdc-cache/schemas/dm-{ct_id}.gql` (only files not already cached) |
| **API Calls** | `GET /api/v1/catalog/dm/{ct_id}/ttl/`, `/shacl/`, `/gql/` (only for uncached files) |

##### `catalog_download_skeleton`

Download the pre-generated **maximal** XML skeleton template and field mapping for a published model. SDCStudio runs a variant of `SkeletonGenerator` against the published XSD to produce:

1. **XML skeleton** — a complete XML instance template with `__PLACEHOLDER__` tokens for **every** element defined in the schema, including all optional metadata elements (`act`, `vtb`, `vte`, `tr`, `modified`, `latitude`, `longitude`, `ExceptionalValue`, `ReferenceRange`). The skeleton preserves exact XSD sequence order, namespace declarations, fixed values, and Cluster/Adapter hierarchy. The Generator Agent fills in placeholders it has data for and prunes the rest.
2. **Field mapping** — a JSON dict mapping each data-bearing element to `{placeholder, ct_id, element_name, type, label, adapter_ctid, required: bool}`. The `required` flag tells the Generator Agent which placeholders **must** be filled (schema author set `minOccurs="1"`) versus which can be pruned if unmapped.

The skeleton is **immutable** for a given `ct_id` (same schema = same skeleton). The agent fetches it once and caches forever.

| Field | Value |
|---|---|
| **Input** | `ct_id` (string, required): CUID2 identifier |
| **Output** | `{ct_id, skeleton_path, field_mapping_path, cached: bool}` |
| **Side Effect** | Saves to `.sdc-cache/schemas/{ct_id}_skeleton.xml` and `.sdc-cache/schemas/{ct_id}_field_mapping.json` (only if not already cached) |
| **API Call** | `GET /api/v1/catalog/dm/{ct_id}/skeleton/` (returns JSON with `skeleton_xml` and `field_mapping` keys, only if not cached) |

##### `catalog_download_ontologies`

Download the SDC4 reference model ontologies and commonly-used third-party ontologies. This is a **one-time operation** — the ontologies are immutable for the lifetime of a major SDC version (currently SDC4).

| Field | Value |
|---|---|
| **Input** | `ontologies` (array of string, optional): specific ontology names; if omitted, downloads all SDC4 core ontologies |
| **Output** | `{files: [{name, path, cached: bool, description}]}` |
| **Side Effect** | Saves to `.sdc-cache/ontologies/` (only files not already cached) |
| **API Call** | `GET /api/v1/catalog/ontologies/` (list), `GET /api/v1/catalog/ontologies/{name}/` (download, only if not cached) |

**Available ontologies** (served from SDCStudio):

| Ontology | File | Purpose |
|---|---|---|
| `sdc4` | `sdc4.ttl` | SDC4 base type definitions (XdStringType, ClusterType, DMType, etc.) |
| `sdc4-meta` | `sdc4-meta.ttl` | SDC4 metadata predicates (isConstrainedByRmComponent, describesConceptualEntity, etc.) |
| `sdc4-base-shapes` | `sdc4_base_shapes.ttl` | SHACL shapes for validating RDF against SDC4 structure |
| `om-2` | `om-2.0.rdf` | Ontology of Units of Measure |
| `sio` | `sio-release.ttl` | Semanticscience Integrated Ontology |
| `schema-org` | `schemaorg.ttl` | Schema.org vocabulary |
| `gist` | `gistCore13.0.0.ttl` | GIST upper ontology |
| `bfo` | `bfo.ttl` | Basic Formal Ontology |
| `skos` | `skos.ttl` | Simple Knowledge Organization System |

---

## SDC4 Naming Conventions

The agents must understand SDC4's naming conventions to correctly parse schemas, construct instance documents, and route artifacts.

### Identifier Prefixes

| Prefix | Meaning | Example | Used In |
|---|---|---|---|
| `dm-{cuid2}` | Data Model | `dm-its7j6bvrb9n2fxdcxmoemod` | XSD filenames, XML root element, RDF graph URIs |
| `mc-{cuid2}` | Model Component | `mc-x7k9m2p4q8r1` | RDF subjects, XSD type names |
| `ms-{cuid2}` | Model Schema element | `ms-x7k9m2p4q8r1` | XSD element references within schema |
| `i-{cuid2}` | Instance | `i-x7k9m2p4q8r1` | Instance IDs in generated apps |
| `i-ev-{cuid2}` | Instance with EVs | `i-ev-x7k9m2p4q8r1` | Instance IDs when ExceptionalValues injected |

### Namespace URIs

| Prefix | URI | Purpose |
|---|---|---|
| `sdc4:` | `https://semanticdatacharter.com/ns/sdc4/` | SDC4 base types and identifiers |
| `sdc4-meta:` | `https://semanticdatacharter.com/ontology/sdc4-meta/` | SDC4 metadata predicates |

### File Naming Convention

| File | Pattern | Example |
|---|---|---|
| XSD schema | `dm-{ct_id}.xsd` | `dm-its7j6bvrb9n2fxdcxmoemod.xsd` |
| XML template | `dm-{ct_id}.xml` | `dm-its7j6bvrb9n2fxdcxmoemod.xml` |
| RDF triples (Turtle) | `dm-{ct_id}.ttl` | `dm-its7j6bvrb9n2fxdcxmoemod.ttl` |
| SHACL shapes | `dm-{ct_id}_shacl.ttl` | `dm-its7j6bvrb9n2fxdcxmoemod_shacl.ttl` |
| GQL CREATE | `dm-{ct_id}.gql` | `dm-its7j6bvrb9n2fxdcxmoemod.gql` |
| JSON instance | `dm-{ct_id}.json` | `dm-its7j6bvrb9n2fxdcxmoemod.json` |
| JSON-LD schema | `dm-{ct_id}.jsonld` | `dm-its7j6bvrb9n2fxdcxmoemod.jsonld` |
| HTML docs | `dm-{ct_id}.html` | `dm-its7j6bvrb9n2fxdcxmoemod.html` |

### Self-Describing Instances

Every SDC4 XML instance is self-describing. The root element name encodes the schema identity:

```xml
<sdc4:dm-its7j6bvrb9n2fxdcxmoemod
    xmlns:sdc4="https://semanticdatacharter.com/ns/sdc4/"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="https://semanticdatacharter.com/ns/sdc4/ dm-its7j6bvrb9n2fxdcxmoemod.xsd">
```

The VaaS API extracts the `ct_id` from the root element name — no additional metadata is needed to identify the schema.

---

### Agent 2: Introspect Agent

**Purpose**: Examine customer datasources and extract structure. **Read-only** — cannot modify data.

**Credential scope**: Datasource credentials (connection strings) from configuration.

**Network access**: None (no outbound HTTP). Database connections are to customer-local infrastructure only.

**File access**: Read from datasource paths (CSV, JSON). Write to `.sdc-cache/introspections/` only.

#### Tools

##### `introspect_sql`

Examine a SQL datasource and extract column structure.

| Field | Value |
|---|---|
| **Input** | `datasource` (string, required): named datasource from config; `query` (string, optional): override SQL query |
| **Output** | `{datasource, columns: [{name, sql_type, nullable, sample_values, unique_count}], row_count}` |
| **Side Effect** | Writes result to `.sdc-cache/introspections/{datasource}.json` |
| **Constraints** | Read-only queries enforced (SELECT only, no DDL/DML). Connection string from config, not from tool input. |

##### `introspect_csv`

Examine a CSV file and infer column types from sample values.

| Field | Value |
|---|---|
| **Input** | `datasource` (string, required): named datasource from config |
| **Output** | `{datasource, columns: [{name, detected_type, nullable, sample_values, unique_count}], row_count}` |
| **Side Effect** | Writes result to `.sdc-cache/introspections/{datasource}.json` |
| **Constraints** | File path from config, not from tool input. Read-only file access. |

##### `introspect_json`

Examine a JSON file or structure and extract field types.

| Field | Value |
|---|---|
| **Input** | `datasource` (string, required): named datasource from config; `jsonpath` (string, optional): JSONPath for nested extraction |
| **Output** | `{datasource, columns: [{name, json_type, nullable, sample_values, unique_count}], row_count}` |
| **Side Effect** | Writes result to `.sdc-cache/introspections/{datasource}.json` |
| **Constraints** | File path from config, not from tool input. Read-only file access. |

**Security note**: The Introspect Agent accepts datasource names (not raw connection strings or file paths) as tool input. All connection details come from the operator-controlled configuration file. This prevents prompt injection attacks from tricking the agent into connecting to unintended datasources.

---

### Agent 3: Mapping Agent

**Purpose**: Suggest and manage column-to-component mappings between introspection results and downloaded schemas.

**Credential scope**: None.

**Network access**: None.

**File access**: Read from `.sdc-cache/schemas/` and `.sdc-cache/introspections/`. Write to `.sdc-cache/mappings/`.

#### Tools

##### `mapping_suggest`

Suggest column-to-component mappings by comparing an introspection result against the cached catalog detail (component tree with SDC4 types).

| Field | Value |
|---|---|
| **Input** | `ct_id` (string, required): target schema; `datasource` (string, required): introspection result name |
| **Output** | `{mappings: [{source_column, target_component, target_type, confidence, reason}], unmapped_columns: [], unmapped_components: []}` |
| **Reads** | `.sdc-cache/schemas/{ct_id}_detail.json` (catalog detail with component tree), `.sdc-cache/introspections/{datasource}.json` |
| **Logic** | Type compatibility (see [Type Mapping Tables](#type-mapping-tables)) + name similarity scoring. Fine-grained constraints are enforced server-side by VaaS at validation time. |

##### `mapping_confirm`

Accept, adjust, and persist a mapping configuration.

| Field | Value |
|---|---|
| **Input** | `ct_id` (string, required); `datasource` (string, required); `mappings` (array of `{source_column, target_component}`); `name` (string, required): mapping profile name |
| **Output** | `{mapping_name, ct_id, datasource, column_count, valid: bool, errors: []}` |
| **Side Effect** | Writes to `.sdc-cache/mappings/{name}.json` |
| **Validation** | Type compatibility, required components covered, constraint feasibility |

##### `mapping_list`

List saved mapping profiles.

| Field | Value |
|---|---|
| **Input** | `ct_id` (string, optional): filter by schema |
| **Output** | Array of `{name, ct_id, datasource, column_count, created_at}` |
| **Reads** | `.sdc-cache/mappings/` directory listing |

---

### Agent 4: Generator Agent

**Purpose**: Produce SDC4 XML instance documents from mapped datasource records.

**Credential scope**: Datasource credentials (read-only, for fetching record data).

**Network access**: None.

**File access**: Read from `.sdc-cache/mappings/`, `.sdc-cache/schemas/`, and datasource files. Write to output directory only.

#### How the Generator builds XML without the XSD

The Generator Agent does not parse the XSD. Instead, it uses two pre-generated artifacts downloaded by the Catalog Agent:

1. **Maximal XML skeleton** (`.sdc-cache/schemas/{ct_id}_skeleton.xml`) — a complete XML template with `__PLACEHOLDER__` tokens for **every** element in the schema, including optional metadata elements. This preserves XSD sequence constraints, namespace declarations, fixed values, and the Cluster/Adapter hierarchy.

2. **Field mapping** (`.sdc-cache/schemas/{ct_id}_field_mapping.json`) — maps each placeholder to `{placeholder, ct_id, element_name, type, label, adapter_ctid, required: bool}`. The `required` flag distinguishes mandatory from optional elements.

The generation algorithm is:
1. Load the skeleton XML and field mapping
2. For each datasource record, copy the skeleton
3. For each mapping entry (source_column → target_component), look up the component's `ct_id` in the field mapping to find its placeholder string
4. Replace the placeholder with the actual data value (with appropriate type formatting)
5. **Remove all unfilled optional elements entirely** — any element where `required: false` and no mapped value exists must be **deleted from the XML tree**, not left empty
6. **Error on unfilled required elements** — if a `required: true` placeholder has no mapped value, report an error for this record
7. Write the completed XML instance

#### Tools

##### `generate_instance`

Generate a single SDC4 XML instance from one datasource record.

| Field | Value |
|---|---|
| **Input** | `mapping_name` (string, required); `row_index` (int, optional): row from datasource; `record` (object, optional): explicit key-value data |
| **Output** | `{xml_path, ct_id, root_element, row_index}` |
| **Side Effect** | Writes XML to output directory |
| **Reads** | Mapping config, skeleton XML template, field mapping JSON, datasource record |

##### `generate_batch`

Generate XML instances for multiple records.

| Field | Value |
|---|---|
| **Input** | `mapping_name` (string, required); `limit` (int, optional, default 100); `offset` (int, optional, default 0) |
| **Output** | `{count, output_dir, files: [string], errors: [{row, error}]}` |
| **Side Effect** | Writes XML files to output directory |

##### `generate_preview`

Generate XML for a single record without writing to disk — for review before committing to a batch.

| Field | Value |
|---|---|
| **Input** | `mapping_name` (string, required); `row_index` (int, optional, default 0) |
| **Output** | `{xml: string, ct_id, root_element}` |
| **Side Effect** | None — preview only |

---

### Agent 5: Validation Agent

**Purpose**: Validate and optionally sign generated XML instances via the VaaS API. Optionally request a full artifact package for downstream distribution.

**Credential scope**: VaaS API token.

**Network access**: HTTPS to configured SDCStudio base URL only (VaaS endpoints).

**File access**: Read from output directory. Write validated/signed files and artifact packages back to output directory.

#### Tools

##### `validate_instance`

Validate an XML instance against its schema via VaaS.

| Field | Value |
|---|---|
| **Input** | `xml_path` (string, required): path to XML file in output directory; `mode` (enum: `report`, `recover`, default `recover`); `package` (bool, optional, default false): request artifact package |
| **Output** | `{valid, mode, schema: {ct_id, title}, structural_errors, semantic_errors, recovered, errors: [], package_path: string or null}` |
| **Side Effect** | If recovered, writes `.recovered.xml` alongside original. If `package=true`, writes `.pkg.zip` alongside original. |
| **API Call** | `POST /api/v1/vaas/validate/?mode={mode}&package={package}` |
| **Constraints** | File must be in configured output directory. No arbitrary path access. |

##### `sign_instance`

Validate and cryptographically sign an XML instance via VaaS.

| Field | Value |
|---|---|
| **Input** | `xml_path` (string, required): path to XML file; `recover` (bool, default true); `package` (bool, optional, default false): request artifact package |
| **Output** | `{valid, signed, signature: {algorithm, issuer, timestamp, schema_ct_id, ev_count}, verification: {public_key_url, verify_command}, package_path: string or null}` |
| **Side Effect** | Writes `.signed.xml` alongside original. If `package=true`, writes `.pkg.zip` alongside original. |
| **API Call** | `POST /api/v1/vaas/validate/sign/?recover={recover}&package={package}` |

##### `validate_batch`

Validate (and optionally sign) multiple XML instances, requesting artifact packages for all.

| Field | Value |
|---|---|
| **Input** | `xml_dir` (string, optional): directory containing XML files (defaults to output directory); `sign` (bool, default false); `package` (bool, default true) |
| **Output** | `{count, results: [{xml_path, valid, signed, package_path, errors}], failed: int}` |
| **Side Effect** | Writes `.pkg.zip` files alongside each XML file |
| **Constraints** | Processes files sequentially to respect VaaS rate limits |

---

### Agent 6: Distribution Agent

**Purpose**: Unpack VaaS artifact packages and route each artifact to its configured destination on the customer's infrastructure.

**Credential scope**: Customer-local service credentials (triplestore, graph DB, REST APIs) from configuration.

**Network access**: Customer-local endpoints only (Fuseki, GraphDB, Neo4j, REST APIs). No access to SDCStudio APIs.

**File access**: Read from artifact packages in output directory. Write to configured destination paths.

#### Tools

##### `distribute_package`

Unpack an artifact package and route all artifacts to their configured destinations.

| Field | Value |
|---|---|
| **Input** | `package_path` (string, required): path to `.pkg.zip` file |
| **Output** | `{package_path, ct_id, artifacts_distributed: int, results: [{artifact, destination, status}]}` |
| **Logic** | Reads `manifest.json` from the zip. For each artifact, looks up the destination in config. Delivers the artifact. Reports per-artifact success/failure. |
| **Side Effect** | Writes artifacts to configured destinations (triplestore, graph DB, file system, REST APIs) |

##### `distribute_batch`

Distribute all artifact packages in a directory.

| Field | Value |
|---|---|
| **Input** | `package_dir` (string, optional): directory containing `.pkg.zip` files (defaults to output directory) |
| **Output** | `{count, results: [{package_path, artifacts_distributed, errors}], failed: int}` |

##### `list_destinations`

List configured distribution destinations and their status.

| Field | Value |
|---|---|
| **Input** | None |
| **Output** | Array of `{name, type, endpoint, status: "reachable" or "unreachable"}` |
| **Logic** | Reads destinations from config. Performs a connectivity check for each. |

##### `inspect_package`

Inspect the contents of an artifact package without distributing it.

| Field | Value |
|---|---|
| **Input** | `package_path` (string, required): path to `.pkg.zip` file |
| **Output** | `{ct_id, instance_id, artifacts: [{type, filename, size_bytes}], manifest: object}` |
| **Side Effect** | None — inspection only |

##### `bootstrap_triplestore`

Load SDC4 reference ontologies and schema-level RDF into the customer's triplestore. The agent checks for existing named graphs before uploading — idempotent and safe to call repeatedly.

| Field | Value |
|---|---|
| **Input** | `ct_id` (string, optional): also load schema-level RDF for a specific model; `include_third_party` (bool, default true): load third-party ontologies |
| **Output** | `{graphs_loaded: [{name, graph_uri, triple_count, status: "loaded" or "already_exists"}]}` |
| **Reads** | `.sdc-cache/ontologies/`, `.sdc-cache/schemas/dm-{ct_id}.ttl` (if ct_id provided) |
| **Side Effect** | Uploads ontology files to triplestore as named graphs (only if not already present) |
| **Named Graphs** | `urn:sdc4:ontology:sdc4`, `urn:sdc4:ontology:sdc4-meta`, `urn:sdc4:schema:dm-{ct_id}`, etc. |

**Triplestore bootstrap sequence** (automatically handled by agents):

1. **Catalog Agent** checks `.sdc-cache/ontologies/` — downloads only missing files via `catalog_download_ontologies`
2. **Catalog Agent** checks `.sdc-cache/schemas/` — downloads only missing schema-level RDF via `catalog_download_schema_rdf`
3. **Distribution Agent** runs `bootstrap_triplestore` — checks triplestore for existing named graphs, loads only what's missing
4. Instance-level RDF from artifact packages can now be distributed — the triples reference vocabulary terms that already exist in the store

**Security note**: The Distribution Agent has write access to customer-local services but cannot reach SDCStudio APIs, cannot read datasources, and cannot modify artifact packages. Destination endpoints come exclusively from the operator-controlled configuration file, not from tool inputs or manifest contents.

---

## Type Mapping Tables

These tables drive the Mapping Agent's `mapping_suggest` tool. They map source data types to SDC4 component types.

### SQL to SDC4

| SQL Type | SDC4 Component | Notes |
|---|---|---|
| `VARCHAR`, `TEXT`, `CHAR` | XdString | `max_length` from column definition |
| `CHAR(n)` (fixed) | XdString | `exact_length = n` |
| `ENUM` | XdString (with `enums`) | Enumeration values extracted |
| `BOOLEAN`, `BIT` | XdBoolean | `trues`/`falses` populated |
| `INTEGER`, `BIGINT`, `SMALLINT` | XdCount | Requires units mapping |
| `DECIMAL`, `NUMERIC` | XdQuantity | `fraction_digits` from scale; requires units |
| `FLOAT`, `REAL` | XdFloat | Requires units |
| `DOUBLE PRECISION` | XdDouble | Requires units |
| `DATE` | XdTemporal | `allow_date = True` |
| `TIME` | XdTemporal | `allow_time = True` |
| `TIMESTAMP`, `DATETIME` | XdTemporal | `allow_datetime = True` |
| `INTERVAL` | XdInterval | `interval_type` from SQL interval qualifier |
| `JSON`, `JSONB` | (nested introspection) | Recursively introspect JSON structure |
| `BLOB`, `BYTEA` | XdFile | `content_mode = embed` |
| `UUID` | XdString | `str_fmt` set to UUID regex pattern |
| `URL` / `URI` columns | XdLink | Detected by name or sample values |

### JSON to SDC4

| JSON Type | SDC4 Component | Notes |
|---|---|---|
| `string` | XdString | Length constraints from sample analysis |
| `string` (ISO date) | XdTemporal | Detected by format pattern matching |
| `string` (URL) | XdLink | Detected by `http://` / `https://` prefix |
| `string` (email, UUID) | XdString | `str_fmt` set to detected pattern |
| `boolean` | XdBoolean | `trues: ["true"]`, `falses: ["false"]` |
| `integer` | XdCount | Requires units mapping |
| `number` | XdQuantity | `fraction_digits` from sample analysis; requires units |
| `array` (homogeneous) | Xd*List | List type matches element type |
| `object` (nested) | Cluster | Recursively maps to component group |
| `null` | (nullable flag) | Marks component as not required |

### CSV to SDC4

CSV columns are untyped strings. Types are inferred from sample values:

| Detected Pattern | SDC4 Component | Detection Method |
|---|---|---|
| `true`/`false`, `yes`/`no`, `0`/`1` | XdBoolean | Value set analysis |
| Integer values | XdCount | Regex `^-?\d+$` + range analysis |
| Decimal values | XdQuantity | Regex `^-?\d+\.\d+$` |
| ISO date (`YYYY-MM-DD`) | XdTemporal (`allow_date`) | Date format regex |
| ISO datetime | XdTemporal (`allow_datetime`) | DateTime format regex |
| Time (`HH:MM:SS`) | XdTemporal (`allow_time`) | Time format regex |
| Email address | XdString (`str_fmt`) | Email regex pattern |
| URL | XdLink | URL regex pattern |
| UUID | XdString (`str_fmt`) | UUID regex pattern |
| Free text | XdString | Default fallback |

---

## Configuration

Operator-controlled YAML configuration (`sdc-agents.yaml`):

```yaml
# SDCStudio connection (used by Catalog Agent and Validation Agent)
sdcstudio:
  base_url: "https://sdcstudio.com"
  api_key: "${SDC_API_KEY}"          # Validation Agent only; env var reference

# Cache and working directories
cache:
  directory: ".sdc-cache"
  catalog_list_ttl_hours: 24         # How often to re-fetch the schema list (new models)
  # Note: Individual schemas, schema-level RDF, and ontologies are immutable
  # once published — they are cached forever and never re-fetched.

# Audit log
audit:
  path: ".sdc-cache/audit.jsonl"
  log_level: "standard"              # "standard" or "verbose" (includes full outputs)

# Datasource definitions (used by Introspect Agent and Generator Agent)
# NOTE: Connection strings are ONLY read from this file, never from tool inputs.
datasources:
  patient_db:
    type: sql
    connection: "${PATIENT_DB_URL}"   # env var — never stored in plaintext
    default_query: "SELECT * FROM patients LIMIT 100"

  lab_results:
    type: csv
    path: "./data/lab_results.csv"
    delimiter: ","
    encoding: "utf-8"

  sensor_feed:
    type: json
    path: "./data/sensor_readings.json"
    jsonpath: "$.readings[*]"

# Output settings (used by Generator Agent and Validation Agent)
output:
  directory: "./sdc-output"
  naming: "{ct_id}_{row_index}.xml"
  include_schema_location: true

# Distribution destinations (used by Distribution Agent only)
destinations:
  triplestore:
    type: fuseki                          # or "graphdb"
    endpoint: "${FUSEKI_URL}"
    auth: "${FUSEKI_AUTH}"
    upload_method: "named_graph"
    graph_uri_from: "manifest"

  graph_database:
    type: neo4j                           # or "memgraph", "neptune"
    endpoint: "${NEO4J_BOLT_URL}"
    auth: "${NEO4J_AUTH}"
    database: "sdc4"

  document_store:
    type: rest_api
    endpoint: "${DATA_API_URL}"
    method: POST
    headers:
      Authorization: "Bearer ${DATA_API_TOKEN}"
      Content-Type: "application/json"

  linked_data:
    type: rest_api
    endpoint: "${JSONLD_ENDPOINT_URL}"
    method: PUT
    headers:
      Content-Type: "application/ld+json"

  archive:
    type: filesystem
    path: "./archive/{ct_id}/{instance_id}/"
    create_directories: true
```

### Credential Isolation

| Credential | Available To | Stored In |
|---|---|---|
| Datasource connection strings | Introspect Agent, Generator Agent | `sdc-agents.yaml` (env var refs) |
| VaaS API token | Validation Agent only | `sdc-agents.yaml` (env var ref) |
| SDCStudio base URL | Catalog Agent, Validation Agent | `sdc-agents.yaml` |
| Triplestore credentials | Distribution Agent only | `sdc-agents.yaml` (env var refs) |
| Graph DB credentials | Distribution Agent only | `sdc-agents.yaml` (env var refs) |
| REST API tokens | Distribution Agent only | `sdc-agents.yaml` (env var refs) |

No agent receives credentials it does not need. The Mapping Agent has no credentials at all.

---

## Audit Log

Every tool invocation across all agents writes a structured JSON record to an append-only audit log:

```json
{
  "timestamp": "2026-02-22T14:30:00.000Z",
  "agent": "introspect",
  "tool": "introspect_sql",
  "inputs": {
    "datasource": "patient_db",
    "query": null
  },
  "outputs": {
    "datasource": "patient_db",
    "column_count": 12,
    "row_count": 1847
  },
  "duration_ms": 342,
  "status": "success",
  "error": null
}
```

**Audit guarantees**:
- Log is append-only — agents cannot modify or delete prior entries
- Sensitive values (connection strings, API tokens) are never logged; only datasource names and result summaries
- Outputs are logged at summary level (column count, row count) not full data
- The log path is configurable; defaults to `.sdc-cache/audit.jsonl`
- Log rotation and retention are the operator's responsibility

---

## Data Residency and VaaS Transit

Four of six agents (Catalog, Introspect, Mapping, Generator) operate entirely on the customer's infrastructure. The exception is the **Validation Agent**, which transmits XML instance documents to SDCStudio's VaaS API over HTTPS for validation and signing.

### What leaves the customer's infrastructure

When the Validation Agent calls `validate_instance` or `sign_instance`, the **full XML instance document** is sent to SDCStudio over HTTPS. This document may contain sensitive data — the customer must understand this before enabling VaaS validation.

### What SDCStudio retains

SDCStudio creates a `ValidationRecord` audit row for every VaaS request. This record contains hashes (SHA-256) of the document and API token, the schema `ct_id`, validation mode, pass/fail status, and error counts. **It does not contain the XML instance content.**

### What SDCStudio does NOT retain

- **The XML instance content** — held in server memory during processing, then discarded
- **The signed XML content** — constructed in memory, returned in the response, not persisted
- **The API token** — only a SHA-256 hash is stored

### Customer guidance

Customers handling sensitive data should:
1. **Review XML content** before enabling VaaS validation — use `generate_preview` to inspect instances
2. **Use `validate` mode (not `sign`)** for initial testing
3. **Evaluate whether local-only validation is sufficient** — the FOSS `sdcvalidator` package on PyPI performs structural validation without any network calls
4. **Understand the audit trail** — SDCStudio logs the SHA-256 hash of every document submitted

---

## Resolved Decisions

### D1: No orchestration — SDC provides primitives only

**Decision**: Do not build an orchestrator. SDC Agents provides purpose-scoped MCP tools. Customers bring their own orchestration layer — LangChain, Microsoft Copilot, Synalinks, or plain scripts.

**Rationale**: Staying out of the workflow/UI business avoids competing with partners and keeps the project focused on what only SDC can do — trusted schema-aware data transformation.

---

## Implementation Phases

### Phase 1: Core Agents

**Goal**: Three working agents covering discovery, introspection, and mapping.

**Deliverables**:
- Project scaffolding (Python package, per-agent MCP server entry points)
- Shared audit log library (append-only JSON lines)
- **Catalog Agent**: `catalog_list_schemas`, `catalog_get_schema`, `catalog_download_skeleton`, `catalog_download_schema_rdf`, `catalog_download_ontologies`
- **Introspect Agent**: `introspect_sql` (SQLAlchemy-based), `introspect_csv`
- **Mapping Agent**: `mapping_suggest`, `mapping_confirm`, `mapping_list`
- YAML configuration loader with env var substitution
- Unit tests for all tools
- Security tests: verify agents cannot access out-of-scope resources

**SDCStudio dependency**: Phase 1 requires SDCStudio to implement the skeleton endpoint, individual artifact serving (ttl/shacl/gql), ontology endpoint, and enhanced catalog detail serializer. See the [SDCStudio enhancement spec](https://github.com/Axius-SDC/SDCStudio/blob/main/docs/dev/agentic-registry/SDCStudio_API_Agents_PRD.md).

### Phase 2: Generation and Validation

**Goal**: End-to-end flow from datasource to validated XML.

**Deliverables**:
- **Generator Agent**: `generate_instance`, `generate_batch`, `generate_preview`
- **Validation Agent**: `validate_instance`, `sign_instance`, `validate_batch`
- `introspect_json` tool added to Introspect Agent
- Improved type inference using string format inference patterns
- Confidence scoring for mapping suggestions
- Integration tests against SDCStudio staging environment
- CLI wrapper for non-MCP usage

### Phase 3: Artifact Package and Distribution

**Goal**: VaaS returns multi-format artifact packages; Distribution Agent delivers them.

**Deliverables**:
- **Distribution Agent**: `distribute_package`, `distribute_batch`, `list_destinations`, `inspect_package`, `bootstrap_triplestore`
- Fuseki/GraphDB triplestore connector (named graph upload via SPARQL Graph Store Protocol)
- Neo4j/Memgraph graph DB connector (GQL CREATE statement execution)
- REST API connector (POST/PUT JSON payloads)
- Filesystem connector (write artifacts to directory structure)
- Triplestore bootstrap: load SDC4 ontologies and schema-level RDF into named graphs
- Destination health checks
- Integration tests with local Fuseki and Neo4j

**SDCStudio dependency**: Phase 3 requires SDCStudio to implement `?package=true` on VaaS endpoints. See the [SDCStudio enhancement spec](https://github.com/Axius-SDC/SDCStudio/blob/main/docs/dev/agentic-registry/SDCStudio_API_Agents_PRD.md).

### Phase 4: Production Hardening

**Goal**: Community-ready release with documentation and packaging.

**Deliverables**:
- Comprehensive documentation (README, per-agent guides, security model)
- PyPI packaging (`pip install sdc-agents`)
- MCP registry listings (one per agent, for granular discoverability)
- Docker images (one per agent, for containerized deployment with network isolation)
- GitHub Actions CI/CD (lint, test, security scan, publish)
- Example configurations for common use cases (healthcare, IoT, financial)
- Contribution guidelines and issue templates
- Audit log viewer CLI (`sdc-agents audit show --agent distribution --last 24h`)

---

## Scope Boundaries

### In Scope

- Discovering and downloading published SDC4 schemas (Catalog Agent)
- Read-only introspection of SQL, JSON, and CSV datasources (Introspect Agent)
- Suggesting and persisting column-to-component mappings (Mapping Agent)
- Generating SDC4 XML instance documents (Generator Agent)
- Validating, signing, and requesting artifact packages via VaaS (Validation Agent)
- Routing artifact packages to customer-local destinations (Distribution Agent)
- Structured audit logging of all tool invocations
- YAML-based operator-controlled configuration
- Per-agent MCP server interfaces

### Out of Scope

- **Creating new SDC4 schemas** — agents map to existing published models only
- **Modifying customer data** — all datasource access is strictly read-only
- **Modifying SDCStudio data** — all API calls are read-only (Catalog) or validation/packaging (VaaS)
- **Agent-to-agent direct communication** — agents share files, not messages
- **Real-time streaming** — batch processing only; streaming is future work
- **Schema evolution/migration** — operator selects the target `ct_id` explicitly
- **GUI** — CLI and MCP tools only; a web UI is a possible community contribution
- **Orchestration logic** — the suite provides agents; orchestration is the customer's choice
- **VaaS artifact package generation** — server-side transformation is an SDCStudio enhancement (see [SDCStudio enhancement spec](https://github.com/Axius-SDC/SDCStudio/blob/main/docs/dev/agentic-registry/SDCStudio_API_Agents_PRD.md))
- **Destination-specific query/read-back** — the Distribution Agent writes to destinations but does not query them

---

## Open Questions

1. **Units defaulting**: Quantified types (XdCount, XdQuantity, XdFloat, XdDouble) require a `units` component. Should the Mapping Agent prompt for units during suggestion, or flag unmapped units as a validation error in `mapping_confirm`?

2. **Cluster nesting**: SDC4 schemas use Cluster-based hierarchies. How deeply should the Introspect Agent represent nested structures (JSON objects, SQL JOINs) in introspection results?

3. **Ordinal detection**: XdOrdinal has ordered enumeration values with specific ranks. Should the Mapping Agent detect ordered categoricals and suggest XdOrdinal, or treat all categoricals as XdString with enums?

4. **ExceptionalValue handling**: When the Generator Agent encounters null/missing datasource values, should it insert EV placeholder elements, omit the element, or flag the row as an error?

5. **Agent containerization**: Should Phase 4 Docker images enforce network policy (e.g., Introspect Agent container has no external network access), or is documentation sufficient?

6. **Multi-schema mapping**: Some datasources may map to multiple SDC4 schemas (e.g., a patient table producing both vitals and demographics instances). Deferred to Phase 2 or later?

---

## Success Criteria

SDC Agents is successful when:

1. Each agent can be deployed and used independently — a customer who only needs schema discovery uses only the Catalog Agent
2. No agent can access resources outside its defined scope, verified by security tests
3. The audit log captures every tool invocation with sufficient detail for compliance review
4. A user with a published SDC4 schema and a SQL/CSV datasource can produce validated, multi-format artifact packages by composing the agents — without writing any XML, RDF, or GQL by hand
5. The Distribution Agent can deliver artifacts to a triplestore, graph database, REST API, and file system from a single artifact package
6. The MCP tool interfaces are compatible with major agent frameworks (Claude, LangChain, OpenAI Agents)
7. Generated XML instances pass VaaS validation without structural errors
8. The Apache 2.0 license and standalone repository enable community contributions without SDCStudio coupling
9. End-to-end latency from datasource record to distributed artifacts is under 5 seconds per instance (excluding network latency to customer destinations)
