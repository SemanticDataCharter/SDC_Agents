# SDC Agents: Purpose-Scoped ADK Agents for SDC4 Data Operations

**Date**: 2026-02-23
**Status**: Active (Phase 3 complete, Phase 4 planned)
**Author**: Timothy W. Cook / Claude Code
**Repository**: `SemanticDataCharter/SDC_Agents` (Apache 2.0 License)
**Related**: SDCStudio `docs/dev/agentic-registry/SDCStudio_API_Agents_PRD.md` (SDCStudio-side enhancement spec)

---

## Executive Summary

### Problem

Organizations with existing datastores (SQL databases, JSON files, CSV exports) need to produce SDC4-compliant XML instances from their data. Today this requires manual schema study, hand-written mapping code, and bespoke validation scripts — a barrier to SDC4 adoption.

A single monolithic agent with broad access to datasources, file systems, and remote APIs creates an unacceptable trust surface. Customers handling sensitive data (healthcare, finance, government) need to know exactly what each agent can do, what it cannot do, and have a complete audit trail of every action.

### Solution

**SDC Agents** is an open-source suite of **purpose-scoped ADK agents**, each implemented as an `LlmAgent` with a narrowly scoped `BaseToolset` and auditable activity:

| Agent | Scope | Can Access | Cannot Access |
|---|---|---|---|
| **Catalog Agent** | Schema discovery + artifacts | SDCStudio Catalog API (read-only, no auth) | Datasources, file system, VaaS API |
| **Introspect Agent** | Datasource structure extraction | Customer datasources (read-only): SQL (30+ via MCP Toolbox), MongoDB, CSV, JSON | SDCStudio APIs, file system writes |
| **Mapping Agent** | Column-to-component mapping | Cached schemas + introspection results | Datasources directly, SDCStudio APIs |
| **Generator Agent** | XML instance generation | Mapping configs, datasource (read-only) | SDCStudio APIs, schema downloads |
| **Validation Agent** | Instance validation and signing | VaaS API (token auth), local XML files | Datasources, schema management |
| **Distribution Agent** | Artifact package routing | Unpacked artifact files, configured destinations | SDCStudio APIs, datasources |
| **Knowledge Agent** *(Phase 5)* | Customer context ingestion | Customer-provided files (read-only) | SDCStudio APIs, datasources, network |
| **Component Assembly Agent** *(Phase 5)* | Autonomous model assembly | Catalog API, Assembly API (token auth), cached knowledge | Datasources directly, VaaS API |

Each agent is an ADK `LlmAgent` with its own `BaseToolset` implementation. Tools are Python functions wrapped in `FunctionTool` — ADK derives input/output schemas from type hints and docstrings. An orchestrating agent, customer pipeline, or human operator composes them via `ToolContext.actions.transfer_to_agent` for sequential handoff — but no single agent can reach across boundaries. A compromised or misbehaving agent has blast radius limited to its scope.

Customers can also consume SDC tools via **MCP** as a secondary interface — each `BaseToolset` can be exported as an MCP server using ADK's `adk_to_mcp_tool_type` conversion utility (see [MCP Export](#mcp-export-secondary-interface)).

### Value Proposition

- **Least-privilege by design** — each agent has the minimum tools for its job
- **Auditable** — every tool invocation is logged with inputs, outputs, and timestamps via a shared `AuditLogger`
- **Data residency by default** — four of six agents run entirely locally with no network access. Only the Catalog Agent (public schema reads) and Validation Agent (VaaS API) make outbound calls. See [Data Residency and VaaS Transit](#data-residency-and-vaas-transit) for the precise data handling model.
- **ADK-native** — built within Google's Agent Development Kit ecosystem as `LlmAgent` + `BaseToolset` + `FunctionTool`, composable with any ADK-based orchestration
- **MCP-compatible** — secondary MCP export enables framework-agnostic integration for non-ADK clients
- **Composable** — use one agent, some agents, or all agents depending on need
- **Open source (Apache 2.0)** — customers can audit every line of code

### Security Principles

1. **No agent has both datasource access and network access** — the Introspect Agent reads data but cannot call APIs; the Validation Agent calls APIs but cannot read datasources
2. **Read-only datasource access** — no agent can write to, modify, or delete customer data
3. **Tools are declarative Python functions** — ADK derives schemas from type hints and docstrings; agents cannot run arbitrary code
4. **Structured audit log** — every tool call writes a JSON audit record (agent, tool, inputs, outputs, timestamp, duration) via a shared `AuditLogger` to append-only `.sdc-cache/audit.jsonl`
5. **No credential sharing** — each `BaseToolset` constructor receives only its own credential scope; the Catalog Agent has no credentials; the Validation Agent has the VaaS API token; the Introspect Agent has datasource credentials
6. **Fail closed** — if an agent encounters an error, it returns the error; it does not retry, escalate privileges, or fall back to broader access

---

## Architecture

### ADK Agent Hierarchy

Each SDC Agent is an ADK `LlmAgent` with a scoped `BaseToolset`. The `BaseToolset.get_tools()` method returns only the `FunctionTool` instances that agent is permitted to use. Credentials are injected at `BaseToolset` construction time from the operator-controlled YAML configuration — agents never receive credentials they don't need.

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
│  │  LlmAgent   │   │  LlmAgent   │   │     LlmAgent             │      │
│  │             │   │             │   │                          │      │
│  │  toolset: 4 │   │  toolset: 3 │   │  reads: mapping configs  │      │
│  │  network: ✗ │   │  network: ✗ │   │  reads: datasource       │      │
│  │  writes: ✗  │   │  writes: ✓  │   │  writes: XML files       │      │
│  └──────┬──────┘   │  (configs   │   │  network: ✗              │      │
│         │          │   only)     │   │  toolset: 3              │      │
│         │          └─────────────┘   └────────────┬─────────────┘      │
│         │                                         │                      │
│  ┌──────▼──────────────────────────────────────────▼───────────────────┐ │
│  │              Shared AuditLogger (append-only)                       │ │
│  │   .sdc-cache/audit.jsonl                                           │ │
│  │   {agent, tool, inputs, outputs, timestamp, duration_ms}           │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌─────────────┐                          ┌──────────────────────────┐  │
│  │   Catalog   │──── HTTPS (no auth) ────▶│  SDCStudio               │  │
│  │  LlmAgent   │    OpenAPIToolset +      │  Catalog API             │  │
│  │  toolset: 5 │    caching wrappers      └──────────────────────────┘  │
│  │  network: ✓ │                                                        │
│  │  datasrc: ✗ │                          ┌──────────────────────────┐  │
│  └─────────────┘                          │  SDCStudio               │  │
│  ┌─────────────┐──── HTTPS (token) ──────▶│  VaaS API                │  │
│  │ Validation  │    AuthCredential        │                          │  │
│  │  LlmAgent   │                          │  ?package=true returns   │  │
│  │  toolset: 3 │◀── artifact package ─────│  .zip with all formats   │  │
│  │  network: ✓ │    (.zip)                └──────────────────────────┘  │
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
│  │  LlmAgent   │                                                        │
│  │  toolset: 4 │                                                        │
│  │  network: ✓ │  (customer-local endpoints: triplestore, graph DB)     │
│  │  datasrc: ✗ │                                                        │
│  └─────────────┘                                                        │
└──────────────────────────────────────────────────────────────────────────┘
```

### Agent Instantiation

Each agent is instantiated as an ADK `LlmAgent` with a scoped toolset:

```python
from google.adk.agents import LlmAgent
from sdc_agents.toolsets.catalog import CatalogToolset
from sdc_agents.config import load_config

config = load_config("sdc-agents.yaml")

catalog_agent = LlmAgent(
    name="catalog",
    model="gemini-2.0-flash",
    instruction="You are the SDC Catalog Agent. You discover published SDC4 "
                "schemas and download schema-level artifacts from SDCStudio.",
    tools=CatalogToolset(config=config).get_tools(),
)
```

### Agent-to-Agent Handoff

Sequential pipeline steps use ADK's `ToolContext.actions.transfer_to_agent` for handoff:

```python
from google.adk.tools import FunctionTool, ToolContext

async def transfer_to_mapping(
    tool_context: ToolContext,
) -> str:
    """Transfer control to the Mapping Agent after catalog and introspection are complete."""
    tool_context.actions.transfer_to_agent = "mapping"
    return "Handing off to Mapping Agent."
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

#### OpenAPIToolset for Catalog API

SDCStudio already serves an OpenAPI specification at `/api/docs/` via `drf-yasg`. The Catalog Agent leverages ADK's `OpenAPIToolset` to auto-generate tools from this spec:

```python
from google.adk.tools.openapi_tool.openapi_spec_parser.openapi_toolset import OpenAPIToolset
import httpx

# Fetch the OpenAPI spec (must be OpenAPI 3.x, not Swagger 2.0)
spec_response = httpx.get(f"{config.sdcstudio.base_url}/api/docs/?format=openapi")
catalog_api_tools = OpenAPIToolset(
    spec_str=spec_response.text,
    spec_str_type="json",
)
```

> **Important**: `OpenAPIToolset` requires **OpenAPI 3.x** specs. SDCStudio currently uses `drf-yasg` which generates OpenAPI 2.0 (Swagger) by default. SDCStudio must either migrate to `drf-spectacular` (native OpenAPI 3.x) or configure `drf-yasg` to output 3.x. This is a Phase 1 prerequisite — see the [SDCStudio enhancement spec](https://github.com/Axius-SDC/SDCStudio/blob/main/docs/dev/agentic-registry/SDCStudio_API_Agents_PRD.md).

The auto-generated tools cover list/detail/download endpoints. Custom `FunctionTool` wrappers add `.sdc-cache/` file persistence and immutable-schema caching on top:

```python
from google.adk.tools import FunctionTool

async def catalog_get_schema(ct_id: str) -> dict:
    """Get detailed metadata and component tree for a published model.

    Checks .sdc-cache/schemas/ first. If cached, returns immediately.
    Otherwise calls the Catalog API and caches the response.
    """
    ...
```

This approach auto-generates the API bindings while custom wrappers handle caching, file persistence, and audit logging.

### Validation Agent (token authentication)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/vaas/validate/` | POST | Validate XML instance (modes: `report`, `recover`) |
| `/api/v1/vaas/validate/sign/` | POST | Validate + sign with XML-Sig (ECDSA P-256) |

Both endpoints accept an optional `?package=true` query parameter. When set, VaaS returns a zip artifact package instead of a single XML response.

The Validation Agent authenticates using the VaaS API token from configuration. Each tool function in the `ValidationToolset` attaches the token as an `Authorization: Token {key}` header on outbound HTTP requests. The token is injected at `ValidationToolset` construction time from the operator-controlled YAML config and never exposed to the LLM.

For customers using `OpenAPIToolset` to consume VaaS endpoints (alternative to custom `FunctionTool` wrappers), ADK's `AuthCredential` pattern applies:

```python
from google.adk.auth import AuthCredential, AuthCredentialTypes, ApiKeyCredentialConfig

vaas_credential = AuthCredential(
    auth_type=AuthCredentialTypes.API_KEY,
    api_key=ApiKeyCredentialConfig(
        name="Authorization",
        value=f"Token {config.sdcstudio.api_key}",
        location="header",
    ),
)
```

No other endpoints are permitted. The agents have no general HTTP capability.

---

## Agent Specifications

### BaseToolset Pattern

Every agent's tools are grouped in a `BaseToolset` subclass. The toolset constructor receives configuration (including credentials for that scope only), and `get_tools()` returns the scoped `FunctionTool` list:

```python
from google.adk.tools import BaseToolset, FunctionTool
from sdc_agents.audit import AuditLogger

class CatalogToolset(BaseToolset):
    """Tools for discovering and downloading published SDC4 schemas."""

    def __init__(self, config: SDCAgentsConfig):
        self._base_url = config.sdcstudio.base_url
        self._cache_dir = config.cache.directory
        self._audit = AuditLogger(config.audit)

    def get_tools(self) -> list[FunctionTool]:
        return [
            FunctionTool(catalog_list_schemas),
            FunctionTool(catalog_get_schema),
            FunctionTool(catalog_download_schema_rdf),
            FunctionTool(catalog_download_skeleton),
            FunctionTool(catalog_download_ontologies),
        ]
```

### Audit Logging

Every tool function calls the shared `AuditLogger` at entry and exit. The audit log is an append-only `.sdc-cache/audit.jsonl` file — not `ToolContext.state` (which is LLM-visible and mutable).

`ToolContext` is used only for flow control: `skip_summarization` and `transfer_to_agent`.

```python
class AuditLogger:
    """Append-only structured audit logger for all SDC Agent tool invocations."""

    def __init__(self, config: AuditConfig):
        self._path = config.path  # .sdc-cache/audit.jsonl
        self._log_level = config.log_level

    def log(self, agent: str, tool: str, inputs: dict,
            outputs: dict, duration_ms: int, status: str,
            error: str | None = None) -> None:
        """Append a JSON audit record. Never modifies prior entries."""
        ...
```

---

### Agent 1: Catalog Agent

**Purpose**: Discover published SDC4 models and download schema-level RDF and reference ontologies from SDCStudio.

**Credential scope**: None (Catalog API is public). Config-injected: `base_url` only.

**Network access**: HTTPS to configured SDCStudio base URL only.

**File access**: Write to `.sdc-cache/schemas/` and `.sdc-cache/ontologies/` only.

#### Tools

##### `catalog_list_schemas`

List published SDC4 data models.

```python
async def catalog_list_schemas(
    project: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """List published SDC4 data models from the SDCStudio Catalog API.

    Args:
        project: Filter by project name.
        search: Text search across model titles and descriptions.

    Returns:
        List of dicts with keys: ct_id, title, description, project, artifact_urls.

    API Call:
        GET /api/v1/catalog/dms/?project={project}&search={search}
    """
```

##### `catalog_get_schema`

Get detailed metadata and component tree for a published model. The component tree tells the Mapping Agent what components exist, what SDC4 types they are, and how they're organized in Clusters.

```python
async def catalog_get_schema(
    ct_id: str,
) -> dict:
    """Get detailed metadata and component tree for a published model.

    Args:
        ct_id: CUID2 identifier of the published model.

    Returns:
        Dict with keys: ct_id, title, description, project,
        components (list of {name, type, ct_id, parent_cluster}), artifact_urls.

    Side Effect:
        Caches response to .sdc-cache/schemas/{ct_id}_detail.json.

    API Call:
        GET /api/v1/catalog/dm/{ct_id}/
    """
```

##### `catalog_download_schema_rdf`

Download and cache the schema-level RDF triples, SHACL shapes, and GQL for a published model. SDC4 schemas are immutable once published — the agent fetches them once and caches forever.

```python
async def catalog_download_schema_rdf(
    ct_id: str,
    formats: list[str] | None = None,
) -> dict:
    """Download and cache schema-level RDF triples, SHACL shapes, and GQL.

    Args:
        ct_id: CUID2 identifier of the published model.
        formats: List of formats to download ('ttl', 'shacl', 'gql').
            Defaults to all three.

    Returns:
        Dict with keys: ct_id, files (list of {format, path, cached: bool}).

    Side Effect:
        Saves to .sdc-cache/schemas/dm-{ct_id}.ttl,
        .sdc-cache/schemas/dm-{ct_id}_shacl.ttl,
        .sdc-cache/schemas/dm-{ct_id}.gql (only uncached files).

    API Calls:
        GET /api/v1/catalog/dm/{ct_id}/ttl/
        GET /api/v1/catalog/dm/{ct_id}/shacl/
        GET /api/v1/catalog/dm/{ct_id}/gql/
        (only for uncached files)
    """
```

##### `catalog_download_skeleton`

Download the pre-generated **maximal** XML skeleton template and field mapping for a published model. SDCStudio runs a variant of `SkeletonGenerator` against the published XSD to produce:

1. **XML skeleton** — a complete XML instance template with `__PLACEHOLDER__` tokens for **every** element defined in the schema, including all optional metadata elements (`act`, `vtb`, `vte`, `tr`, `modified`, `latitude`, `longitude`, `ExceptionalValue`, `ReferenceRange`). The skeleton preserves exact XSD sequence order, namespace declarations, fixed values, and Cluster/Adapter hierarchy. The Generator Agent fills in placeholders it has data for and prunes the rest.
2. **Field mapping** — a JSON dict mapping each data-bearing element to `{placeholder, ct_id, element_name, type, label, adapter_ctid, required: bool}`. The `required` flag tells the Generator Agent which placeholders **must** be filled (schema author set `minOccurs="1"`) versus which can be pruned if unmapped.

The skeleton is **immutable** for a given `ct_id` (same schema = same skeleton). The agent fetches it once and caches forever.

```python
async def catalog_download_skeleton(
    ct_id: str,
) -> dict:
    """Download the XML skeleton template and field mapping for a published model.

    Args:
        ct_id: CUID2 identifier of the published model.

    Returns:
        Dict with keys: ct_id, skeleton_path, field_mapping_path, cached (bool).

    Side Effect:
        Saves to .sdc-cache/schemas/{ct_id}_skeleton.xml and
        .sdc-cache/schemas/{ct_id}_field_mapping.json (only if not cached).

    API Call:
        GET /api/v1/catalog/dm/{ct_id}/skeleton/
        (returns JSON with skeleton_xml and field_mapping keys, only if not cached)
    """
```

##### `catalog_download_ontologies`

Download the SDC4 reference model ontologies and commonly-used third-party ontologies. This is a **one-time operation** — the ontologies are immutable for the lifetime of a major SDC version (currently SDC4).

```python
async def catalog_download_ontologies(
    ontologies: list[str] | None = None,
) -> dict:
    """Download SDC4 reference ontologies and third-party ontologies.

    Args:
        ontologies: Specific ontology names to download. If omitted,
            downloads all SDC4 core ontologies.

    Returns:
        Dict with keys: files (list of {name, path, cached: bool, description}).

    Side Effect:
        Saves to .sdc-cache/ontologies/ (only uncached files).

    API Calls:
        GET /api/v1/catalog/ontologies/ (list)
        GET /api/v1/catalog/ontologies/{name}/ (download, only if not cached)
    """
```

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

**Credential scope**: Datasource credentials (connection strings) from configuration, injected at `IntrospectToolset` construction.

**Network access**: None (no outbound HTTP). Database connections are to customer-local infrastructure only.

**File access**: Read from datasource paths (CSV, JSON). Write to `.sdc-cache/introspections/` only.

#### Connector Layer: MCP Toolbox for Databases

The Introspect Agent uses Google's **[MCP Toolbox for Databases](https://google.github.io/adk-docs/integrations/mcp-toolbox-for-databases/)** as its connector layer for SQL datasources. MCP Toolbox provides production-hardened drivers for 30+ data sources (PostgreSQL, MySQL, SQLite, MSSQL, Oracle, Cloud SQL, AlloyDB, Spanner, BigQuery) with connection pooling and IAM authentication support.

The `introspect_sql` tool is a thin wrapper that delegates connection management to MCP Toolbox and adds `.sdc-cache/` persistence on top. This avoids building custom SQLAlchemy connectors for each database type and gives customers immediate access to the full range of supported databases.

For **BigQuery** and **Spanner**, customers can alternatively use the dedicated ADK integrations ([BigQuery Tools](https://google.github.io/adk-docs/integrations/bigquery/), [Spanner Tools](https://google.github.io/adk-docs/integrations/spanner/)) for GCP-native authentication and query optimization. The `introspect_sql` tool auto-detects BigQuery and Spanner datasource types from config and delegates to the appropriate integration.

For **MongoDB**, the Introspect Agent uses the dedicated [ADK MongoDB integration](https://google.github.io/adk-docs/integrations/mongodb/) for schema analysis and document sampling via a separate `introspect_mongodb` tool.

#### Tools

##### `introspect_sql`

Examine a SQL datasource and extract column structure. Uses MCP Toolbox for Databases as the connector layer, with automatic delegation to dedicated BigQuery or Spanner integrations when those datasource types are configured.

```python
async def introspect_sql(
    datasource: str,
    query: str | None = None,
) -> dict:
    """Examine a SQL datasource and extract column structure.

    Uses MCP Toolbox for Databases for connection management (30+ databases).
    BigQuery and Spanner datasources auto-delegate to dedicated ADK integrations.

    Args:
        datasource: Named datasource from config (not a raw connection string).
        query: Override SQL query. Defaults to datasource's configured query.

    Returns:
        Dict with keys: datasource, columns (list of {name, sql_type, nullable,
        sample_values, unique_count}), row_count.

    Side Effect:
        Writes result to .sdc-cache/introspections/{datasource}.json.

    Constraints:
        Read-only queries enforced (SELECT only, no DDL/DML).
        Connection string from config, not from tool input.
    """
```

##### `introspect_csv`

Examine a CSV file and infer column types from sample values.

```python
async def introspect_csv(
    datasource: str,
) -> dict:
    """Examine a CSV file and infer column types from sample values.

    Args:
        datasource: Named datasource from config (not a raw file path).

    Returns:
        Dict with keys: datasource, columns (list of {name, detected_type,
        nullable, sample_values, unique_count}), row_count.

    Side Effect:
        Writes result to .sdc-cache/introspections/{datasource}.json.

    Constraints:
        File path from config, not from tool input. Read-only file access.
    """
```

##### `introspect_json`

Examine a JSON file or structure and extract field types.

```python
async def introspect_json(
    datasource: str,
    jsonpath: str | None = None,
) -> dict:
    """Examine a JSON file and extract field types.

    Args:
        datasource: Named datasource from config (not a raw file path).
        jsonpath: JSONPath expression for nested extraction.
            Defaults to datasource's configured jsonpath.

    Returns:
        Dict with keys: datasource, columns (list of {name, json_type, nullable,
        sample_values, unique_count}), row_count.

    Side Effect:
        Writes result to .sdc-cache/introspections/{datasource}.json.

    Constraints:
        File path from config, not from tool input. Read-only file access.
    """
```

##### `introspect_mongodb`

Examine a MongoDB collection and extract document structure. Uses the ADK MongoDB integration for schema analysis and document sampling.

```python
async def introspect_mongodb(
    datasource: str,
    collection: str | None = None,
    sample_size: int = 100,
) -> dict:
    """Examine a MongoDB collection and extract document structure.

    Uses the ADK MongoDB integration for connection management and
    document sampling. Analyzes document structure across the sample
    to infer a consistent schema.

    Args:
        datasource: Named datasource from config (not a raw connection string).
        collection: Override collection name. Defaults to datasource's configured collection.
        sample_size: Number of documents to sample for schema inference.

    Returns:
        Dict with keys: datasource, collection, fields (list of {name, bson_type,
        nullable, sample_values, unique_count, nested_fields}), document_count.

    Side Effect:
        Writes result to .sdc-cache/introspections/{datasource}.json.

    Constraints:
        Read-only access (find only, no insert/update/delete).
        Connection string from config, not from tool input.
    """
```

**Security note**: The Introspect Agent accepts datasource names (not raw connection strings or file paths) as tool input. All connection details come from the operator-controlled configuration file. This prevents prompt injection attacks from tricking the agent into connecting to unintended datasources.

---

### Agent 3: Mapping Agent

**Purpose**: Suggest and manage column-to-component mappings between introspection results and downloaded schemas.

**Credential scope**: None. Config-injected: cache directory path only.

**Network access**: None.

**File access**: Read from `.sdc-cache/schemas/` and `.sdc-cache/introspections/`. Write to `.sdc-cache/mappings/`.

#### Tools

##### `mapping_suggest`

Suggest column-to-component mappings by comparing an introspection result against the cached catalog detail (component tree with SDC4 types).

```python
async def mapping_suggest(
    ct_id: str,
    datasource: str,
) -> dict:
    """Suggest column-to-component mappings for a schema and datasource.

    Args:
        ct_id: Target schema CUID2 identifier.
        datasource: Introspection result name.

    Returns:
        Dict with keys: mappings (list of {source_column, target_component,
        target_type, confidence, reason}), unmapped_columns, unmapped_components.

    Reads:
        .sdc-cache/schemas/{ct_id}_detail.json (catalog detail with component tree)
        .sdc-cache/introspections/{datasource}.json

    Logic:
        Type compatibility (see Type Mapping Tables) + name similarity scoring.
        Fine-grained constraints enforced server-side by VaaS at validation time.
    """
```

##### `mapping_confirm`

Accept, adjust, and persist a mapping configuration.

```python
async def mapping_confirm(
    ct_id: str,
    datasource: str,
    mappings: list[dict],
    name: str,
) -> dict:
    """Accept, adjust, and persist a mapping configuration.

    Args:
        ct_id: Target schema CUID2 identifier.
        datasource: Introspection result name.
        mappings: List of {source_column, target_component} dicts.
        name: Mapping profile name.

    Returns:
        Dict with keys: mapping_name, ct_id, datasource, column_count,
        valid (bool), errors (list).

    Side Effect:
        Writes to .sdc-cache/mappings/{name}.json.

    Validation:
        Type compatibility, required components covered, constraint feasibility.
    """
```

##### `mapping_list`

List saved mapping profiles.

```python
async def mapping_list(
    ct_id: str | None = None,
) -> list[dict]:
    """List saved mapping profiles.

    Args:
        ct_id: Filter by schema CUID2 identifier.

    Returns:
        List of dicts with keys: name, ct_id, datasource, column_count, created_at.

    Reads:
        .sdc-cache/mappings/ directory listing.
    """
```

---

### Agent 4: Generator Agent

**Purpose**: Produce SDC4 XML instance documents from mapped datasource records.

**Credential scope**: Datasource credentials (read-only, for fetching record data), injected at `GeneratorToolset` construction.

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

```python
async def generate_instance(
    mapping_name: str,
    row_index: int | None = None,
    record: dict | None = None,
) -> dict:
    """Generate a single SDC4 XML instance from one datasource record.

    Args:
        mapping_name: Name of the mapping profile.
        row_index: Row index from datasource.
        record: Explicit key-value data (alternative to row_index).

    Returns:
        Dict with keys: xml_path, ct_id, root_element, row_index.

    Side Effect:
        Writes XML to output directory.

    Reads:
        Mapping config, skeleton XML template, field mapping JSON, datasource record.
    """
```

##### `generate_batch`

Generate XML instances for multiple records. Wrapped as `LongRunningFunctionTool` to avoid blocking the agent during large batch operations — the tool returns an operation ID, and the agent polls for completion.

```python
async def generate_batch(
    mapping_name: str,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Generate XML instances for multiple datasource records.

    Args:
        mapping_name: Name of the mapping profile.
        limit: Maximum number of records to process.
        offset: Starting record index.

    Returns:
        Dict with keys: count, output_dir, files (list of str),
        errors (list of {row, error}).

    Side Effect:
        Writes XML files to output directory.
    """
```

##### `generate_preview`

Generate XML for a single record without writing to disk — for review before committing to a batch.

```python
async def generate_preview(
    mapping_name: str,
    row_index: int = 0,
) -> dict:
    """Generate XML for a single record without writing to disk.

    Args:
        mapping_name: Name of the mapping profile.
        row_index: Row index from datasource.

    Returns:
        Dict with keys: xml (str), ct_id, root_element.

    Side Effect:
        None — preview only.
    """
```

---

### Agent 5: Validation Agent

**Purpose**: Validate and optionally sign generated XML instances via the VaaS API. Optionally request a full artifact package for downstream distribution.

**Credential scope**: VaaS API token, injected at `ValidationToolset` construction via ADK's `AuthCredential`.

**Network access**: HTTPS to configured SDCStudio base URL only (VaaS endpoints).

**File access**: Read from output directory. Write validated/signed files and artifact packages back to output directory.

#### Tools

##### `validate_instance`

Validate an XML instance against its schema via VaaS.

```python
async def validate_instance(
    xml_path: str,
    mode: str = "recover",
    package: bool = False,
) -> dict:
    """Validate an XML instance against its schema via VaaS.

    Args:
        xml_path: Path to XML file in output directory.
        mode: Validation mode ('report' or 'recover').
        package: Request artifact package (.zip) from VaaS.

    Returns:
        Dict with keys: valid, mode, schema ({ct_id, title}),
        structural_errors, semantic_errors, recovered, errors (list),
        package_path (str or None).

    Side Effect:
        If recovered, writes .recovered.xml alongside original.
        If package=True, writes .pkg.zip alongside original.

    API Call:
        POST /api/v1/vaas/validate/?mode={mode}&package={package}

    Constraints:
        File must be in configured output directory. No arbitrary path access.
    """
```

##### `sign_instance`

Validate and cryptographically sign an XML instance via VaaS.

```python
async def sign_instance(
    xml_path: str,
    recover: bool = True,
    package: bool = False,
) -> dict:
    """Validate and cryptographically sign an XML instance via VaaS.

    Args:
        xml_path: Path to XML file.
        recover: Attempt recovery before signing.
        package: Request artifact package (.zip) from VaaS.

    Returns:
        Dict with keys: valid, signed, signature ({algorithm, issuer, timestamp,
        schema_ct_id, ev_count}), verification ({public_key_url, verify_command}),
        package_path (str or None).

    Side Effect:
        Writes .signed.xml alongside original.
        If package=True, writes .pkg.zip alongside original.

    API Call:
        POST /api/v1/vaas/validate/sign/?recover={recover}&package={package}
    """
```

##### `validate_batch`

Validate (and optionally sign) multiple XML instances, requesting artifact packages for all. Wrapped as `LongRunningFunctionTool` for large batches.

```python
async def validate_batch(
    xml_dir: str | None = None,
    sign: bool = False,
    package: bool = True,
) -> dict:
    """Validate and optionally sign multiple XML instances.

    Args:
        xml_dir: Directory containing XML files. Defaults to output directory.
        sign: Also sign each valid instance.
        package: Request artifact packages.

    Returns:
        Dict with keys: count, results (list of {xml_path, valid, signed,
        package_path, errors}), failed (int).

    Side Effect:
        Writes .pkg.zip files alongside each XML file.

    Constraints:
        Processes files sequentially to respect VaaS rate limits.
    """
```

---

### Agent 6: Distribution Agent

**Purpose**: Unpack VaaS artifact packages and route each artifact to its configured destination on the customer's infrastructure.

**Credential scope**: Customer-local service credentials (triplestore, graph DB, REST APIs) from configuration, injected at `DistributionToolset` construction.

**Network access**: Customer-local endpoints only (Fuseki, GraphDB, Neo4j, REST APIs). No access to SDCStudio APIs.

**File access**: Read from artifact packages in output directory. Write to configured destination paths.

#### Tools

##### `distribute_package`

Unpack an artifact package and route all artifacts to their configured destinations.

```python
async def distribute_package(
    package_path: str,
) -> dict:
    """Unpack an artifact package and route artifacts to configured destinations.

    Args:
        package_path: Path to .pkg.zip file.

    Returns:
        Dict with keys: package_path, ct_id, artifacts_distributed (int),
        results (list of {artifact, destination, status}).

    Logic:
        Reads manifest.json from the zip. For each artifact, looks up the
        destination in config. Delivers the artifact. Reports per-artifact
        success/failure.

    Side Effect:
        Writes artifacts to configured destinations (triplestore, graph DB,
        file system, REST APIs).
    """
```

##### `distribute_batch`

Distribute all artifact packages in a directory. Wrapped as `LongRunningFunctionTool` for large batches.

```python
async def distribute_batch(
    package_dir: str | None = None,
) -> dict:
    """Distribute all artifact packages in a directory.

    Args:
        package_dir: Directory containing .pkg.zip files.
            Defaults to output directory.

    Returns:
        Dict with keys: count, results (list of {package_path,
        artifacts_distributed, errors}), failed (int).
    """
```

##### `list_destinations`

List configured distribution destinations and their status.

```python
async def list_destinations() -> list[dict]:
    """List configured distribution destinations and their connectivity status.

    Returns:
        List of dicts with keys: name, type, endpoint,
        status ('reachable' or 'unreachable').

    Logic:
        Reads destinations from config. Performs a connectivity check for each.
    """
```

##### `inspect_package`

Inspect the contents of an artifact package without distributing it.

```python
async def inspect_package(
    package_path: str,
) -> dict:
    """Inspect the contents of an artifact package without distributing it.

    Args:
        package_path: Path to .pkg.zip file.

    Returns:
        Dict with keys: ct_id, instance_id, artifacts (list of {type, filename,
        size_bytes}), manifest (dict).

    Side Effect:
        None — inspection only.
    """
```

##### `bootstrap_triplestore`

Load SDC4 reference ontologies and schema-level RDF into the customer's triplestore. The agent checks for existing named graphs before uploading — idempotent and safe to call repeatedly.

```python
async def bootstrap_triplestore(
    ct_id: str | None = None,
    include_third_party: bool = True,
) -> dict:
    """Load SDC4 reference ontologies and schema-level RDF into the triplestore.

    Args:
        ct_id: Also load schema-level RDF for a specific model.
        include_third_party: Load third-party ontologies (om-2, sio, etc.).

    Returns:
        Dict with keys: graphs_loaded (list of {name, graph_uri, triple_count,
        status ('loaded' or 'already_exists')}).

    Reads:
        .sdc-cache/ontologies/
        .sdc-cache/schemas/dm-{ct_id}.ttl (if ct_id provided)

    Side Effect:
        Uploads ontology files to triplestore as named graphs
        (only if not already present).

    Named Graphs:
        urn:sdc4:ontology:sdc4, urn:sdc4:ontology:sdc4-meta,
        urn:sdc4:schema:dm-{ct_id}, etc.
    """
```

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

### MongoDB BSON to SDC4

| BSON Type | SDC4 Component | Notes |
|---|---|---|
| `string` | XdString | Length constraints from sample analysis |
| `bool` | XdBoolean | `trues: ["true"]`, `falses: ["false"]` |
| `int` / `long` | XdCount | Requires units mapping |
| `double` / `decimal128` | XdQuantity | `fraction_digits` from sample analysis; requires units |
| `date` | XdTemporal | `allow_datetime = True` |
| `objectId` | XdString | `str_fmt` set to ObjectId pattern |
| `array` (homogeneous) | Xd*List | List type matches element type |
| `object` (embedded) | Cluster | Recursively maps to component group |
| `null` | (nullable flag) | Marks component as not required |
| `binData` | XdFile | `content_mode = embed` |

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
# SDCStudio connection (used by Catalog, Validation, and Assembly Agents)
sdcstudio:
  base_url: "https://sdcstudio.com"
  api_key: "${SDC_API_KEY}"          # Validation + Assembly Agents; env var reference
  default_library_project: "SDC4-Core"  # Default project for contextual components (D7)

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
# SQL datasources use MCP Toolbox for Databases (30+ databases supported).
# BigQuery and Spanner auto-delegate to dedicated ADK integrations.
datasources:
  patient_db:
    type: sql                         # Uses MCP Toolbox for Databases
    connection: "${PATIENT_DB_URL}"   # env var — never stored in plaintext
    default_query: "SELECT * FROM patients LIMIT 100"

  analytics_warehouse:
    type: bigquery                    # Uses dedicated ADK BigQuery integration
    project: "${GCP_PROJECT_ID}"
    dataset: "clinical_data"
    default_query: "SELECT * FROM patients LIMIT 100"

  document_store:
    type: mongodb                     # Uses dedicated ADK MongoDB integration
    connection: "${MONGO_URL}"
    database: "patient_records"
    collection: "encounters"

  lab_results:
    type: csv
    path: "./data/lab_results.csv"
    delimiter: ","
    encoding: "utf-8"

  sensor_feed:
    type: json
    path: "./data/sensor_readings.json"
    jsonpath: "$.readings[*]"

# Knowledge resources (used by Knowledge Agent, Phase 5)
# Customer-side contextual resources for semantic understanding.
# NOTE: Read-only access to source files. Knowledge index stays local (or managed via GCP).
knowledge:
  # Vector store backend for the knowledge index
  # Options: "chroma" (local, default), "vertex-ai-rag" (GCP managed),
  #          "qdrant", "pinecone" (requires API key)
  vector_store: "chroma"
  vector_store_path: ".sdc-cache/knowledge/"  # For local backends (chroma, qdrant)
  # vertex_ai_project: "${GCP_PROJECT_ID}"    # For vertex-ai-rag backend
  # vertex_ai_corpus: "sdc-knowledge"         # For vertex-ai-rag backend

  # Customer-side contextual resources to ingest
  sources:
    data_dictionary:
      type: csv
      path: "./docs/data_dictionary.csv"

    policies:
      type: pdf
      path: "./docs/data_governance_policy.pdf"

    domain_glossary:
      type: json
      path: "./docs/glossary.json"

    existing_ontology:
      type: ttl
      path: "./docs/customer_vocab.ttl"

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

### ADK Runner Configuration

Instantiate all agents and compose them in an ADK runner:

```python
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, DatabaseSessionService

from sdc_agents.config import load_config
from sdc_agents.toolsets.catalog import CatalogToolset
from sdc_agents.toolsets.introspect import IntrospectToolset
from sdc_agents.toolsets.mapping import MappingToolset
from sdc_agents.toolsets.generator import GeneratorToolset
from sdc_agents.toolsets.validation import ValidationToolset
from sdc_agents.toolsets.distribution import DistributionToolset

config = load_config("sdc-agents.yaml")

# Each toolset receives only the credentials it needs
catalog_agent = LlmAgent(
    name="catalog",
    model="gemini-2.0-flash",
    description="Discovers published SDC4 schemas and downloads artifacts from SDCStudio.",
    instruction="Discover published SDC4 schemas and download artifacts.",
    tools=CatalogToolset(config=config).get_tools(),
)

introspect_agent = LlmAgent(
    name="introspect",
    model="gemini-2.0-flash",
    description="Examines customer datasources and extracts column structure (read-only).",
    instruction="Examine customer datasources and extract structure (read-only).",
    tools=IntrospectToolset(config=config).get_tools(),
)

mapping_agent = LlmAgent(
    name="mapping",
    model="gemini-2.0-flash",
    description="Suggests and manages column-to-component mappings between datasources and schemas.",
    instruction="Suggest and manage column-to-component mappings.",
    tools=MappingToolset(config=config).get_tools(),
)

generator_agent = LlmAgent(
    name="generator",
    model="gemini-2.0-flash",
    description="Produces SDC4 XML instance documents from mapped datasource records.",
    instruction="Produce SDC4 XML instances from mapped datasource records.",
    tools=GeneratorToolset(config=config).get_tools(),
)

validation_agent = LlmAgent(
    name="validation",
    model="gemini-2.0-flash",
    description="Validates and signs XML instances via the VaaS API.",
    instruction="Validate and sign XML instances via the VaaS API.",
    tools=ValidationToolset(config=config).get_tools(),
)

distribution_agent = LlmAgent(
    name="distribution",
    model="gemini-2.0-flash",
    description="Routes artifact packages to customer-local destinations (triplestore, graph DB, REST API, filesystem).",
    instruction="Route artifact packages to customer-local destinations.",
    tools=DistributionToolset(config=config).get_tools(),
)

# Compose as sub-agents of a root orchestrator (optional)
# Note: description on each sub-agent is required for transfer_to_agent routing
root_agent = LlmAgent(
    name="sdc_pipeline",
    model="gemini-2.0-flash",
    instruction="Orchestrate the SDC4 data transformation pipeline.",
    sub_agents=[
        catalog_agent, introspect_agent, mapping_agent,
        generator_agent, validation_agent, distribution_agent,
    ],
)

# Run with ADK runner
# Development: InMemorySessionService (no persistence, state lost on restart)
# Production:  DatabaseSessionService (SQL-backed, crash recovery, resume from record N)
runner = Runner(
    agent=root_agent,
    app_name="sdc-agents",
    session_service=InMemorySessionService(),  # Use DatabaseSessionService for production
)
```

### Credential Isolation

| Credential | Available To | Injected Via |
|---|---|---|
| Datasource connection strings | Introspect Agent, Generator Agent | `IntrospectToolset(config=...)`, `GeneratorToolset(config=...)` |
| VaaS API token | Validation Agent only | `ValidationToolset(config=...)` with `AuthCredential` |
| Assembly API key | Component Assembly Agent only *(Phase 5)* | `AssemblyToolset(config=...)` with `AuthCredential` |
| SDCStudio base URL | Catalog Agent, Validation Agent, Component Assembly Agent | `CatalogToolset(config=...)`, `ValidationToolset(config=...)`, `AssemblyToolset(config=...)` |
| Triplestore credentials | Distribution Agent only | `DistributionToolset(config=...)` |
| Graph DB credentials | Distribution Agent only | `DistributionToolset(config=...)` |
| REST API tokens | Distribution Agent only | `DistributionToolset(config=...)` |

No agent receives credentials it does not need. The Mapping Agent's `MappingToolset` and Knowledge Agent's `KnowledgeToolset` constructors receive only the cache directory path and knowledge resource paths — no network credentials.

---

## Audit Log

Every tool invocation across all agents writes a structured JSON record to an append-only audit log via the shared `AuditLogger`:

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
- `ToolContext.state` is **not** used for audit logging (it is LLM-visible and mutable); `ToolContext` is used only for `skip_summarization` and `transfer_to_agent` flow control

---

## MCP Export (Secondary Interface)

Each `BaseToolset` can be exported as an MCP server using ADK's `adk_to_mcp_tool_type` conversion utility. This enables customers using non-ADK MCP clients (Claude Desktop, LangChain MCP, or any MCP-compatible framework) to consume SDC tools without adopting ADK.

```python
from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type
from sdc_agents.toolsets.catalog import CatalogToolset

config = load_config("sdc-agents.yaml")
toolset = CatalogToolset(config=config)

# Convert ADK FunctionTools to MCP tool definitions
mcp_tools = [adk_to_mcp_tool_type(tool) for tool in toolset.get_tools()]
```

A CLI convenience command wraps this for standalone MCP server operation:

```bash
# Start the Catalog Agent as an MCP server
sdc-agents serve --mcp catalog

# Start the Introspect Agent as an MCP server
sdc-agents serve --mcp introspect
```

**MCP is documented but not the primary development path.** The primary architecture is ADK-native — `LlmAgent` + `BaseToolset` + `FunctionTool`. MCP export is a compatibility layer for framework-agnostic integration.

> **Note**: MCP establishes stateful persistent connections, which can challenge distributed/scaled deployments. Customers running multiple concurrent MCP server instances should implement connection management accordingly.

---

## Observability (Phase 4)

The audit log (`.sdc-cache/audit.jsonl`) captures every tool invocation for compliance. For production monitoring — latency dashboards, error rate tracking, LLM token usage, tool call distributions — SDC Agents integrates with ADK's observability ecosystem:

| Backend | Use Case | ADK Integration |
|---|---|---|
| [Google Cloud Trace](https://google.github.io/adk-docs/integrations/google-cloud-trace/) | GCP-native production monitoring | Built-in ADK support |
| OpenTelemetry export | Self-hosted monitoring (Grafana, Jaeger) | Via ADK's OTEL support |
| [Phoenix](https://google.github.io/adk-docs/integrations/phoenix/) | Self-hosted LLM observability | ADK integration |
| [MLflow](https://google.github.io/adk-docs/integrations/mlflow/) | Experiment tracking, trace ingestion | ADK integration |

Observability is complementary to the audit log — the audit log is the compliance record (what happened), while observability provides operational metrics (how well it's working). Both are configured independently.

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

### D1: ADK-native orchestration with MCP compatibility

**Decision**: SDC Agents provides scoped agents composable within the ADK framework. Customers can also use MCP for framework-agnostic integration. SDC does not impose a specific orchestration pattern — customers bring their own pipeline logic using ADK sub-agents, `transfer_to_agent`, or plain scripts.

**Rationale**: ADK provides the native agent composition primitives (sub-agents, tool context, handoff) that SDC Agents leverages. MCP export ensures compatibility with non-ADK ecosystems. Staying out of the workflow/UI business avoids competing with partners and keeps the project focused on what only SDC can do — trusted schema-aware data transformation.

### D3: Reference, never copy

**Decision**: Components are referenced by their existing `ct_id` — never copied into the target project. A component's identity is permanent and shared across models and domains. This is a core SDC principle.

The assembly endpoint creates only new Clusters (when a needed grouping doesn't already exist) and the DM itself (wiring together referenced components and Clusters). Everything below the Cluster level already exists in the catalog.

### D4: Fully autonomous — no human-in-the-loop

**Decision**: The assembly pipeline produces a **published, generated data model** — not an unpublished draft for review. The output is immediately available in the SDCStudio catalog, ready for consumption by Phases 1–4 agents.

**Rationale**: Domain experts and data stewards unleash the agents on repositories. Axius maintains standards-compliant component libraries. The agents do the assembly work that previously required ontology and graph database specialists.

### D5: Assembly API authentication

**Decision**: API key auth (same pattern as VaaS). The API key maps to a **Modeler user** who has a **default project** selected in their SDCStudio settings. The assembly endpoint creates the DM in that project.

### D6: Cluster naming by SDC_Agents

**Decision**: The Component Assembly Agent proposes Cluster labels based on its analysis of the data source structure. SDCStudio accepts the labels as provided.

### D7: Contextual component discovery via Default project

**Decision**: SDCStudio maintains a **Default project** with standards-compliant contextual components (Audit, Attestation, Party, Protocol, Workflow, ACS). The assembly agent discovers these via the catalog API filtered to the Default project.

The Default project name is available in config (`sdc-agents.yaml`) so customers can supplement with their own contextual libraries if needed.

### D8: Arbitrarily complex data trees

**Decision**: The assembly system supports nested Cluster hierarchies of arbitrary depth — Clusters within Clusters — reflecting the actual structure of the data source. Contextual components (Audit, Attestation, Party, etc.) from the Default project are attached to the DM's contextual slots.

### D9: Intelligence on both sides

**Decision**: SDC_Agents handles analysis intelligence (understand data sources, discover matching components, propose hierarchical structure, name Clusters). SDCStudio handles assembly intelligence (validate references, create Clusters, wire component references, publish, run full generation pipeline). The API boundary carries a structured tree spec, not raw data.

---

## Development Sequencing

**Consumer-first, provider-second.** SDC_Agents (the consumer) is developed and tested first against the documented SDCStudio API contract using mocked responses. SDCStudio (the provider) implements the endpoints afterward to match what the agents actually need. This avoids building both sides in parallel, discovering mismatches at integration time, and reworking both.

The sequence for each phase:

1. **Build agents against the documented API contract** — mock SDCStudio responses during development
2. **Test thoroughly with mocks** — the agent code crystallizes exactly what request/response shapes are needed
3. **Implement SDCStudio endpoints** — build to match the verified consumer contract, not speculative predictions
4. **Integration test** — final step, not a discovery step

This means SDC_Agents Phases 1–4 are developed to completion before SDCStudio begins implementing its corresponding enhancements. The SDCStudio PRD becomes a *verified* spec, not a *predicted* one.

---

## Implementation Phases

### Phase 1: Core Agents — COMPLETE

**Goal**: Three working agents covering discovery, introspection, and mapping.

**Status**: Complete (2026-02-23). 68 tests passing, 92% coverage.

**Delivered**:
- `pyproject.toml` — hatchling build with google-adk>=1.25, pydantic>=2, pyyaml>=6, httpx>=0.27, sqlalchemy>=2
- `sdc_agents.common.config` — Pydantic models (`SDCAgentsConfig`, `SDCStudioConfig`, `CacheConfig`, `AuditConfig`, `DatasourceConfig`, `OutputConfig`) with YAML loader and `${VAR}` regex substitution (fail-closed: `KeyError` on missing env var)
- `sdc_agents.common.audit` — `AuditLogger` with append-only JSONL, `_sanitize()` redacts keys containing connection/token/key/password/secret, `_summarize()` reduces outputs to counts at standard log level
- `sdc_agents.common.cache` — `CacheManager` with path helpers for schemas/ontologies/introspections/mappings, `ensure_dirs()`, `is_cached()`
- **Catalog Agent**: `CatalogToolset(BaseToolset)` with 5 tools (`catalog_list_schemas`, `catalog_get_schema`, `catalog_download_schema_rdf`, `catalog_download_skeleton`, `catalog_download_ontologies`), httpx async client, cache-first for immutable schemas
- **Introspect Agent**: `IntrospectToolset(BaseToolset)` with 2 tools (`introspect_sql`, `introspect_csv`), SELECT-only regex enforcement, CSV type inference for 10 types (boolean > integer > decimal > date > datetime > time > email > URL > UUID > string)
- **Mapping Agent**: `MappingToolset(BaseToolset)` with 3 tools (`mapping_suggest`, `mapping_confirm`, `mapping_list`), `TYPE_COMPATIBILITY` matrix + `SequenceMatcher` name similarity, JSON persist/list in `.sdc-cache/mappings/`
- Agent factories: `create_catalog_agent()`, `create_introspect_agent()`, `create_mapping_agent()` — each returns `LlmAgent(tools=[Toolset(config)])`
- Mock fixtures: `httpx.MockTransport` for Catalog API, `aiosqlite` for SQL introspection — zero live SDCStudio dependency
- Security tests: tool scope isolation (each toolset exposes only its own tools, no cross-scope leakage), SQL write rejection (9 patterns: DROP/INSERT/UPDATE/DELETE/ALTER/CREATE/TRUNCATE/REPLACE/MERGE), datasource name enforcement

**Implementation notes**:
- Phase 1 uses SQLAlchemy directly for SQL introspection (testable with aiosqlite). MCP Toolbox for Databases integration deferred to Phase 2 — same tool function signatures, transparent swap.
- Bound methods used as tools (not standalone functions). `FunctionTool` wraps bound methods; `inspect.signature` of a bound method excludes `self`, so ADK schema derivation works correctly.
- Toolsets passed directly to `LlmAgent.tools` list (not `get_tools()` results). ADK calls `get_tools()` internally.

**SDCStudio dependency**: Phase 1 defines the contract that SDCStudio must fulfill — skeleton endpoint, individual artifact serving (ttl/shacl/gql), ontology endpoint, and enhanced catalog detail serializer. SDCStudio implements these **after** the agent contract is stable. See the [SDCStudio enhancement spec](https://github.com/Axius-SDC/SDCStudio/blob/main/docs/dev/agentic-registry/SDCStudio_API_Agents_PRD.md).

### Phase 2: Generation and Validation — COMPLETE

**Goal**: End-to-end flow from datasource to validated XML.

**Status**: Complete (2026-02-23). 115 tests passing (47 new), 79% coverage.

**Delivered**:
- **Generator Agent**: `GeneratorToolset(BaseToolset)` with 3 tools (`generate_instance`, `generate_batch`, `generate_preview`), skeleton-based XML generation using `{ct_id}_skeleton.xml` + `{ct_id}_field_mapping.json` from cache, placeholder substitution, optional element pruning
- **Validation Agent**: `ValidationToolset(BaseToolset)` with 3 tools (`validate_instance`, `sign_instance`, `validate_batch`), VaaS API integration with path confinement + token auth, artifact package (.pkg.zip) support
- **Introspect Agent extensions**: 2→5 tools (`introspect_json` with JSONPath extraction, `introspect_mongodb` with BSON-to-SDC4 type mapping, `introspect_bigquery` with BigQuery schema extraction via `asyncio.to_thread`)
- Config additions: `api_key` (VaaS token), `toolbox_url` (MCP Toolbox), `jsonpath` (JSON datasource), `database`/`collection` (MongoDB datasource)
- Cache additions: `skeleton_path()`, `field_mapping_path()` helpers
- Dependencies: motor>=3.6, jsonpath-ng>=1.6, mongomock (dev), toolbox-adk (optional)
- Security tests: 5 toolsets with disjoint tool name sets (5+5+3+3+3 = 19 total tools), Validation path confinement, Generator read-only datasource access, VaaS token redacted in audit log

**Implementation notes**:
- Batch tools (`generate_batch`, `validate_batch`) use regular `FunctionTool` (not `LongRunningFunctionTool`). ADK's `LongRunningFunctionTool` requires polling infrastructure; deferred until needed.
- VaaS API mocked via `httpx.MockTransport` in tests — zero live SDCStudio dependency.
- MongoDB introspection tested via `mongomock`; live MongoDB integration deferred.

### Phase 3: Artifact Package and Distribution — COMPLETE

**Goal**: Distribution Agent delivers multi-format artifact packages to customer destinations.

**Status**: Complete (2026-02-23). 143 tests passing (28 new), 82% coverage.

**Delivered**:
- **Distribution Agent**: `DistributionToolset(BaseToolset)` with 5 tools (`inspect_package`, `list_destinations`, `distribute_package`, `distribute_batch`, `bootstrap_triplestore`)
- `DestinationConfig` Pydantic model with 5 destination types (`fuseki`, `graphdb`, `neo4j`, `rest_api`, `filesystem`) + `destinations: Dict[str, DestinationConfig]` on `SDCAgentsConfig`
- Fuseki/GraphDB triplestore connector — SPARQL Graph Store Protocol PUT for named graph upload, idempotent bootstrap via ASK query before upload
- Neo4j HTTP API connector — POST to `/db/{database}/tx/commit` transactional endpoint
- REST API connector — configurable POST/PUT with custom headers
- Filesystem connector — path pattern substitution (`{ct_id}`, `{instance_id}`) with optional directory creation
- Destination health checks — `list_destinations` probes each endpoint (GET/HEAD with timeout), reports `reachable`/`unreachable`
- Security tests: 6 toolsets with disjoint tool name sets (5+5+3+3+3+5 = 24 total tools), Distribution path confinement, destination credential redaction in audit log

**Implementation notes**:
- All connectors use httpx — no neo4j-driver or other driver-specific dependencies.
- Per-artifact failure isolation: if one delivery fails, remaining artifacts still processed. Per-artifact status reported.
- Manifest `destination` values looked up in config; unknown destinations skipped gracefully (not an error).
- `bootstrap_triplestore` checks for existing named graphs via SPARQL ASK before uploading (idempotent).
- `distribute_batch` uses regular `FunctionTool` (not `LongRunningFunctionTool`).
- All tests use `httpx.MockTransport` — zero live Fuseki/Neo4j dependency. Integration tests deferred to Phase 4.

**SDCStudio dependency**: Phase 3 defines the artifact package contract (`manifest.json` structure, zip contents, `?package=true` behavior). SDCStudio implements the VaaS package support **after** the Distribution Agent's expectations are stable.

### Phase 4: Production Hardening and Integration Testing

**Goal**: Community-ready release with documentation, packaging, ecosystem integration, and **end-to-end integration testing against live SDCStudio**.

**Deliverables**:
- **Integration tests against live SDCStudio** — validate mocked contracts match real API behavior
- Comprehensive documentation (README, per-agent guides, security model)
- PyPI packaging (`pip install sdc-agents`)
- MCP export adapters (per-agent MCP server mode via `adk_to_mcp_tool_type`)
- ADK Integration Page contribution (`docs/integrations/sdc-agents.md` to `google/adk-docs` repo — see [ADK Integration Page](#adk-integration-page-phase-4))
- **ADK Ecosystem Contribution** — generalize Phase 3 SPARQL connector and contribute to `google/adk-docs` integrations directory (see [ADK Ecosystem Contributions](#adk-ecosystem-contributions-phase-4)):
  - `adk-sparql-tools` — SPARQL 1.1 / Fuseki / GraphDB integration (fills a gap: no triplestore integrations exist in the current ADK ecosystem)
  - ~~`adk-neo4j-tools`~~ — superseded by [MCP Toolbox for Databases](https://google.github.io/adk-docs/integrations/mcp-toolbox-for-databases/#graph-databases) (Neo4j + Dgraph support)
- Docker images (one per agent, for containerized deployment with network isolation)
- GitHub Actions CI/CD (lint, test, security scan, publish)
- Example configurations for common use cases (healthcare, IoT, financial)
- Contribution guidelines and issue templates
- Observability integration — Google Cloud Trace for GCP, OpenTelemetry export for self-hosted (see [Observability](#observability-phase-4))
- Audit log viewer CLI (`sdc-agents audit show --agent distribution --last 24h`)

**This is when SDCStudio enhancements are built and validated.** By Phase 4, every API contract has been battle-tested by the agent code. SDCStudio implements its Phases 1–3 (Catalog enhancements, VaaS packages, retention) to match the verified consumer contracts. Integration tests confirm both sides agree.

### Phase 5: Component Assembly and Knowledge Agents (Future)

**Goal**: Shift from consume-only to create-and-consume — agents analyze data sources, discover matching catalog components, and assemble published SDC4 data models autonomously.

Phase 5 adds two agents:

- **Knowledge Agent**: Ingests customer-side contextual resources (data dictionaries, PDFs, metadata repositories, existing ontologies) into a semantic knowledge index. Provides context to the Component Assembly Agent for better component matching, Cluster naming, and contextual component selection. Read-only, no network access (for local deployments). The knowledge index backend is configurable:
  - **Local**: [Chroma](https://google.github.io/adk-docs/integrations/chroma/) vector store in `.sdc-cache/knowledge/` — zero infrastructure, embedded in the agent process
  - **GCP**: [Vertex AI RAG Engine](https://google.github.io/adk-docs/integrations/vertex-ai-rag-engine/) — managed retrieval with Google Cloud auth, for customers already on GCP
  - Other ADK-compatible vector stores ([Qdrant](https://google.github.io/adk-docs/integrations/qdrant/), [Pinecone](https://google.github.io/adk-docs/integrations/pinecone/)) can be substituted via configuration

- **Component Assembly Agent**: Analyzes data sources (using Introspect Agent results + Knowledge Agent context), discovers matching published components from the SDCStudio catalog, proposes arbitrarily deep Cluster hierarchies reflecting the data source structure, selects contextual components (Audit, Attestation, Party, etc.) from SDCStudio's Default project library, and calls the SDCStudio assembly API. The output is a **fully published, generated data model** — immediately available in the catalog for Phases 1–4 consumption. No human-in-the-loop.

**Key principles** (see `docs/dev/COMPONENT_ASSEMBLY_DESIGN.md` for full design decisions):
- Components are **referenced by `ct_id`**, never copied — reuse across models and domains is a core SDC feature
- Only **new Clusters and the DM** are created; all component-level artifacts already exist
- Assembly API authentication via API key → Modeler user → default project (same pattern as VaaS)
- Intelligence on both sides: SDC_Agents handles analysis and discovery; SDCStudio handles assembly, validation, publication, and artifact generation
- Component discovery may leverage [Vertex AI Search](https://google.github.io/adk-docs/integrations/vertex-ai-search/) for semantic matching (e.g., agent queries "blood pressure measurement" and Vertex AI Search finds the matching `ct_id` from the catalog) — evaluated during Phase 5 implementation

**Development sequence**: Same consumer-first pattern. Build and test both agents with mocked Assembly API responses. SDCStudio implements `POST /api/v1/dmgen/assemble/` afterward to match the verified contract.

---

## ADK Integration Page (Phase 4)

Phase 4 includes contributing an integration page to the `google/adk-docs` repository to get SDC Agents listed on the [ADK Integrations directory](https://google.github.io/adk-docs/integrations/) alongside GitHub, BigQuery, MongoDB, etc.

**Required structure** (per `google/adk-docs` CONTRIBUTING.md):

- **File**: `docs/integrations/sdc-agents.md`
- **Frontmatter**: `catalog_title`, `catalog_description`, `catalog_icon`
- **Sections**: Use cases, Prerequisites, Installation, "Use with agent" code example, Available tools table, Resources
- **Logo asset**: `docs/integrations/assets/sdc-agents.png`

**Prerequisites**:
- Sign the Google CLA
- Working PyPI package (`pip install sdc-agents`)
- Complete integration documentation with testable code examples

**PR acceptance criteria** (from ADK docs): completeness/testability, value for developers, publishability.

---

## ADK Ecosystem Contributions (Phase 4)

Phase 3 builds triplestore and property graph connectors for the Distribution Agent. Phase 4 generalizes the triplestore connector into a standalone ADK integration and contributes it to the `google/adk-docs` integrations directory. **No triplestore integration currently exists** in the ADK ecosystem — `adk-sparql-tools` fills this gap. Property graph support (Neo4j, Dgraph) is already available via [MCP Toolbox for Databases](https://google.github.io/adk-docs/integrations/mcp-toolbox-for-databases/#graph-databases), so `adk-neo4j-tools` is no longer needed as an ecosystem contribution.

### `adk-sparql-tools` — SPARQL / Triplestore Integration

| Field | Value |
|---|---|
| **Supported backends** | Apache Jena Fuseki, Ontotext GraphDB, Stardog, Blazegraph, any SPARQL 1.1 endpoint |
| **Tools** | `sparql_query` (SELECT/CONSTRUCT/ASK), `sparql_update` (INSERT/DELETE), `upload_named_graph` (Graph Store Protocol), `list_named_graphs`, `describe_resource` |
| **Auth** | Basic auth, Bearer token, or no auth (configurable) |
| **Value to ADK community** | Enables any ADK agent to work with RDF/linked data — relevant to knowledge graphs, ontology management, semantic search, and any domain using W3C standards |

### ~~`adk-neo4j-tools` — Neo4j / Property Graph Integration~~ (Superseded)

Neo4j and Dgraph property graph support is now available via [MCP Toolbox for Databases](https://google.github.io/adk-docs/integrations/mcp-toolbox-for-databases/#graph-databases) with Cypher query and schema inspection tools. This contribution is no longer needed. SDC Agents' Distribution Agent uses its own httpx-based Neo4j HTTP connector for GQL statement delivery, which is sufficient for the artifact distribution use case.

### Contribution Strategy

1. **Phase 3**: Build connectors for SDC Distribution Agent use case (complete)
2. **Phase 4**: Extract SPARQL module as generic integration, write docs and tests, submit PRs to `google/adk-docs`
3. **Same CLA** — the Google CLA signing for the SDC Agents integration page covers these contributions
4. **Two PRs total**: SDC Agents integration page + SPARQL integration

This establishes SDC as a credible ADK ecosystem contributor — the project that brought triplestore/semantic web infrastructure into the ADK integrations directory.

---

## ADK Ecosystem Integrations Used

SDC Agents leverages existing ADK ecosystem integrations rather than building custom connectors. This table lists the integrations referenced across the agent specifications:

| ADK Integration | Used By | Purpose |
|---|---|---|
| [MCP Toolbox for Databases](https://google.github.io/adk-docs/integrations/mcp-toolbox-for-databases/) | Introspect Agent | SQL connector layer — 30+ databases (PostgreSQL, MySQL, SQLite, MSSQL, Oracle, Cloud SQL, AlloyDB, Spanner, BigQuery); also provides [graph database support](https://google.github.io/adk-docs/integrations/mcp-toolbox-for-databases/#graph-databases) (Neo4j, Dgraph) |
| [BigQuery Tools](https://google.github.io/adk-docs/integrations/bigquery/) | Introspect Agent | GCP-native BigQuery introspection with IAM auth |
| [Spanner Tools](https://google.github.io/adk-docs/integrations/spanner/) | Introspect Agent | GCP-native Spanner introspection with IAM auth |
| [MongoDB](https://google.github.io/adk-docs/integrations/mongodb/) | Introspect Agent | Document database schema analysis and sampling |
| [OpenAPIToolset](https://google.github.io/adk-docs/tools/openapi-tools/) | Catalog Agent | Auto-generated API bindings from SDCStudio's drf-yasg OpenAPI spec |
| [Chroma](https://google.github.io/adk-docs/integrations/chroma/) | Knowledge Agent *(Phase 5)* | Local vector store for customer knowledge index |
| [Vertex AI RAG Engine](https://google.github.io/adk-docs/integrations/vertex-ai-rag-engine/) | Knowledge Agent *(Phase 5)* | Managed retrieval for GCP-native deployments |
| [Vertex AI Search](https://google.github.io/adk-docs/integrations/vertex-ai-search/) | Component Assembly Agent *(Phase 5)* | Semantic component discovery from catalog |
| [Google Cloud Trace](https://google.github.io/adk-docs/integrations/google-cloud-trace/) | All agents *(Phase 4)* | Production observability — latency, error rates, token usage |

---

## Scope Boundaries

### In Scope

- Discovering and downloading published SDC4 schemas (Catalog Agent)
- Read-only introspection of SQL (30+ databases via MCP Toolbox), MongoDB, BigQuery, Spanner, JSON, and CSV datasources (Introspect Agent)
- Suggesting and persisting column-to-component mappings (Mapping Agent)
- Generating SDC4 XML instance documents (Generator Agent)
- Validating, signing, and requesting artifact packages via VaaS (Validation Agent)
- Routing artifact packages to customer-local destinations (Distribution Agent)
- Structured audit logging of all tool invocations
- YAML-based operator-controlled configuration
- Per-agent ADK `BaseToolset` + `LlmAgent` definitions
- MCP export as secondary compatibility interface

### Out of Scope

- **Modifying customer data** — all datasource access is strictly read-only
- **Modifying existing SDCStudio data** — API calls are read-only (Catalog), validation/packaging (VaaS), or create-only (Assembly). No agent can edit or delete existing models or components.
- **Real-time streaming** — batch processing only; streaming is future work
- **Schema evolution/migration** — operator selects the target `ct_id` explicitly
- **GUI** — CLI and ADK/MCP tools only; a web UI is a possible community contribution
- **VaaS artifact package generation** — server-side transformation is an SDCStudio enhancement (see [SDCStudio enhancement spec](https://github.com/Axius-SDC/SDCStudio/blob/main/docs/dev/agentic-registry/SDCStudio_API_Agents_PRD.md))
- **Destination-specific query/read-back** — the Distribution Agent writes to destinations but does not query them

### Future: Component Assembly and Knowledge (Phase 5)

**Creating new SDC4 schemas** is not in scope for Phases 1–4 — agents map to existing published models only. Phase 5 adds the **Knowledge Agent** (customer context ingestion) and **Component Assembly Agent** (autonomous model assembly from catalog components). Components are referenced by `ct_id`, never copied. Only new Clusters and the DM are created. The output is a fully published, generated data model — no human-in-the-loop. See [Phase 5](#phase-5-component-assembly-and-knowledge-agents-future) and [Component Assembly Design](docs/dev/COMPONENT_ASSEMBLY_DESIGN.md) for decisions D3–D9.

---

## Open Questions

1. **Units defaulting**: Quantified types (XdCount, XdQuantity, XdFloat, XdDouble) require a `units` component. Should the Mapping Agent prompt for units during suggestion, or flag unmapped units as a validation error in `mapping_confirm`?

2. **Cluster nesting**: SDC4 schemas use Cluster-based hierarchies. How deeply should the Introspect Agent represent nested structures (JSON objects, SQL JOINs) in introspection results?

3. **Ordinal detection**: XdOrdinal has ordered enumeration values with specific ranks. Should the Mapping Agent detect ordered categoricals and suggest XdOrdinal, or treat all categoricals as XdString with enums?

4. **ExceptionalValue handling**: When the Generator Agent encounters null/missing datasource values, should it insert EV placeholder elements, omit the element, or flag the row as an error?

5. **Agent containerization**: Should Phase 4 Docker images enforce network policy (e.g., Introspect Agent container has no external network access), or is documentation sufficient?

6. **Multi-schema mapping**: Some datasources may map to multiple SDC4 schemas (e.g., a patient table producing both vitals and demographics instances). Deferred to Phase 2 or later?

7. **Knowledge Agent scope**: Should the Knowledge Agent be a separate agent or an expansion of the Introspect Agent? The Introspect Agent already reads customer data sources — adding knowledge resource ingestion is a natural extension. But the security model may differ (knowledge resources are documentation, not live data).

8. **Assembly validation failures**: If the assembly endpoint finds an invalid reference (unpublished component, incompatible type in a Cluster slot), does it reject the entire request or return a partial result with errors? Fail-closed (reject) is consistent with the existing security principles.

9. **Component matching intelligence**: How much semantic matching intelligence should live in the Component Assembly Agent vs. SDCStudio? The agent has the customer's knowledge context; SDCStudio has the component metadata and type system. The matching logic likely needs both.

10. **Multi-source assembly**: Can a single DM be assembled from components discovered across multiple data sources? E.g., patient demographics from a SQL database + lab results from CSV files → single Patient Record DM. This seems natural but adds complexity to the Cluster hierarchy design.

---

## Success Criteria

SDC Agents is successful when:

1. Each agent can be deployed and used independently — a customer who only needs schema discovery uses only the Catalog Agent
2. No agent can access resources outside its defined scope, verified by security tests
3. The audit log captures every tool invocation with sufficient detail for compliance review
4. A user with a published SDC4 schema and a SQL/CSV datasource can produce validated, multi-format artifact packages by composing the agents — without writing any XML, RDF, or GQL by hand
5. The Distribution Agent can deliver artifacts to a triplestore, graph database, REST API, and file system from a single artifact package
6. The ADK-native agent definitions are composable within the ADK framework, with MCP compatibility layer for framework-agnostic integration
7. Generated XML instances pass VaaS validation without structural errors
8. The Apache 2.0 license and standalone repository enable community contributions without SDCStudio coupling
9. End-to-end latency from datasource record to distributed artifacts is under 5 seconds per instance (excluding network latency to customer destinations)
10. (Phase 5) The Component Assembly Agent can analyze a data source, discover matching catalog components, assemble a published data model via the Assembly API, and immediately consume it with Phases 1–4 agents — fully autonomously
