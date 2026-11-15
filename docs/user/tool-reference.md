# Agent & Tool Reference

SDC Agents provides 35 tools across 9 agents. Each agent is an ADK `LlmAgent` with a scoped `BaseToolset`.

The agents are **design-time** tools for building models in SDCStudio. Introspect, Knowledge, Semantic Discovery, Catalog, Mapping and Assembly do the design work. Generator and Validation produce and check **sample records for testing a model**. They are not an operational ingest path: in production, data reaches Governed Data Records through the app stack or Supabase kit SDCStudio generates from a published model (see the [README](../../README.md#what-is-sdc-agents)).

---

## Summary

| Agent | Tools | Network Access | Datasource Access |
|---|---|---|---|
| **Assembly** | 4 | HTTPS (Assembly API) | None |
| **Catalog** | 7 | HTTPS (SDCStudio API) | None |
| **Distribution** | 5 (3 deprecated) | Configured destinations | None |
| **Generator** | 3 | None | Read-only (CSV/JSON) |
| **Introspect** | 6 | None | Read-only |
| **Knowledge** | 3 | None | Read-only (files) |
| **Mapping** | 3 | None | None (cache only) |
| **Semantic Discovery** | 1 | GCP (Vertex AI Search) | None (ADK-only) |
| **Validation** | 3 | HTTPS (public catalog for schemas; settlement, token auth) | None |

---

## Catalog Agent

Discovers published SDC4 schemas and downloads artifacts from the SDCStudio Catalog API. All tools are read-only. Schemas are immutable and cached by `ct_id`.

### `catalog_list_schemas`

List available SDC4 schemas from the catalog.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | str | No | `""` | Search term to filter schemas by title or description |

**Returns:** `list[dict]` — each with `ct_id`, `title`, `description`, `project_name`.

### `catalog_get_schema`

Get full schema details including components tree and artifact URLs. Results are cached by `ct_id`.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `ct_id` | str | Yes | — | CUID2 identifier of the schema |

**Returns:** `dict` — `ct_id`, `title`, `description`, `components` (tree), `artifacts`.

### `catalog_download_schema_rdf`

Download the RDF representation of a schema.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `ct_id` | str | Yes | — | CUID2 identifier of the schema |

**Returns:** `str` — RDF/XML content.

### `catalog_download_skeleton`

Download an XML skeleton instance for a schema. The skeleton contains placeholder values for field substitution.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `ct_id` | str | Yes | — | CUID2 identifier of the schema |

**Returns:** `str` — XML skeleton content.

### `catalog_download_ontologies`

Download SDC4 ontology definitions. Ontologies are global (not per-schema) in the SDCStudio catalog.

**Parameters:** None.

**Returns:** `str` — RDF/XML ontology content.

---

## Introspect Agent

Examines customer datasources and extracts structure. Read-only access only. SQL queries are restricted to a single SELECT statement and run on a read-only connection (see `introspect_sql`).

Source values (`sample_values`) appear only in the tool's return value. The copy written to the introspection cache, and anything written to the audit log, holds structure only: names, types, counts and constraints. The cache is shared with the Assembly toolset, which makes network calls.

### `introspect_sql`

Execute a read-only SQL query against a configured SQL datasource.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `datasource_name` | str | Yes | — | Name of a configured SQL datasource |
| `query` | str | Yes | — | SQL SELECT query to execute |

**Returns:** `list[dict]` — row dictionaries with column names as keys.

**Security:** two layers, and the query is always rolled back.

1. **The statement is parsed.** Only one `SELECT` or `WITH ... SELECT` statement is accepted, with at most one trailing semicolon. Comments and quoted text are skipped, and the rest is checked. Stacked statements are rejected with `PermissionError`, as are data-modifying keywords anywhere (CTE writes, `SELECT ... INTO`, `FOR UPDATE`, `ATTACH`, `PRAGMA`) and side-effect functions (`nextval`, `pg_read_file`, `load_extension`, `load_file` and others). Text that databases read differently is refused rather than guessed at: a backslash before a closing quote, `--` without a following space, and MySQL `/*! */` comments.
2. **The connection is read-only.** SQLite runs with `PRAGMA query_only = ON`. PostgreSQL uses `SET TRANSACTION READ ONLY` and `statement_timeout`. MySQL and MariaDB use `SET SESSION TRANSACTION READ ONLY` and `max_execution_time`. Other dialects are refused unless the datasource sets `read_only_role: true`.

The timeout is `query_timeout_seconds` on the datasource (default 30). It isn't enforced on SQLite. The audit log records the query, row count and column names, never the rows.

Neither layer replaces a least-privilege database role: connect with a role that can only `SELECT` what the agents need.

### `introspect_csv`

Introspect a CSV datasource to discover column structure and inferred types.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `datasource_name` | str | Yes | — | Name of a configured CSV datasource |
| `max_rows` | int | No | `100` | Maximum rows to read for type inference |

**Returns:**

```json
{
  "datasource": "my_csv",
  "type": "csv",
  "columns": [
    {
      "name": "patient_id",
      "inferred_type": "integer",
      "sample_values": ["101", "102", "103", "104", "105"]
    }
  ],
  "row_count": 100
}
```

**Inferred types:** `boolean`, `integer`, `decimal`, `date`, `datetime`, `time`, `email`, `URL`, `UUID`, `string`.

### `introspect_json`

Introspect a JSON datasource to discover structure and types. Optionally extract records via JSONPath.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `datasource_name` | str | Yes | — | Name of a configured JSON datasource |
| `jsonpath` | str | No | config value | JSONPath expression to extract records (overrides config) |

**Returns:**

```json
{
  "datasource": "records_json",
  "type": "json",
  "columns": [
    {
      "name": "result_value",
      "inferred_type": "decimal",
      "sample_values": [1.5, 2.3, 0.8, 1.1, 3.7]
    }
  ],
  "row_count": 50
}
```

### `introspect_mongodb`

Introspect a MongoDB collection to discover document structure.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `datasource_name` | str | Yes | — | Name of a configured MongoDB datasource |
| `collection` | str | No | config value | Collection name (overrides config) |
| `sample_size` | int | No | `100` | Number of documents to sample |

**Returns:**

```json
{
  "datasource": "clinical_db",
  "collection": "lab_results",
  "fields": [
    {
      "name": "patient_id",
      "bson_type": "string",
      "nullable": false,
      "sample_values": ["P001", "P002", "P003"]
    }
  ],
  "document_count": 1500
}
```

**BSON type mapping:** `string` → string, `int`/`int32`/`int64`/`long` → integer, `double`/`decimal`/`decimal128` → decimal, `bool` → boolean, `date`/`timestamp` → datetime, `objectId` → objectId, `array` → array, `object` → object.

### `introspect_bigquery`

Introspect a BigQuery dataset or table to discover structure and types. Read-only: uses `list_rows` and schema access only. Requires `google-cloud-bigquery` (`pip install sdc-agents[bigquery]`).

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `datasource_name` | str | Yes | — | Name of a configured BigQuery datasource |
| `dataset` | str | No | config value | Dataset name (overrides config) |
| `table` | str | No | `null` | Table name. If omitted, lists all tables in the dataset. |
| `max_rows` | int | No | `100` | Maximum rows to sample for type inference |

**Returns** (single table):

```json
{
  "datasource": "analytics_bq",
  "type": "bigquery",
  "dataset": "clinical_data",
  "table": "lab_results",
  "columns": [
    {
      "name": "test_id",
      "inferred_type": "integer",
      "sample_values": ["1", "2", "3"]
    }
  ],
  "row_count": 1500
}
```

**Returns** (dataset listing, when `table` is omitted):

```json
{
  "datasource": "analytics_bq",
  "type": "bigquery",
  "dataset": "clinical_data",
  "tables": [
    {
      "table": "lab_results",
      "columns": [{"name": "test_id", "inferred_type": "integer", "sample_values": []}],
      "row_count": 1500
    }
  ]
}
```

**BigQuery type mapping:**

| BigQuery Type | Inferred Type |
|---|---|
| `STRING` | string |
| `INT64`, `INTEGER` | integer |
| `FLOAT64`, `FLOAT` | decimal |
| `NUMERIC`, `BIGNUMERIC` | decimal |
| `BOOL`, `BOOLEAN` | boolean |
| `DATE` | date |
| `DATETIME`, `TIMESTAMP` | datetime |
| `TIME` | time |
| `BYTES` | string |
| `JSON` | object |
| `STRUCT`, `RECORD` | object |
| `ARRAY` | array |
| `GEOGRAPHY` | string |

---

## Mapping Agent

Suggests and manages column-to-SDC4-component mappings. Operates on cached data only — no direct datasource or API access.

### `mapping_suggest`

Suggest SDC4 component mappings for a datasource column using type compatibility and name similarity.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `column_name` | str | Yes | — | Name of the datasource column |
| `column_type` | str | Yes | — | Inferred type (e.g. `string`, `integer`, `date`) |
| `schema_ct_id` | str | Yes | — | `ct_id` of the target schema (must be cached) |

**Returns:** `list[dict]` — sorted by score (descending):

```json
[
  {
    "component_ct_id": "abc123",
    "component_label": "Patient ID",
    "component_type": "XdString",
    "score": 0.857
  }
]
```

**Type compatibility matrix:**

| Source Type | Compatible SDC4 Components |
|---|---|
| `string`, `email`, `URL`, `UUID` | `XdString` |
| `integer` | `XdCount`, `XdQuantity`, `XdIntegerList` |
| `decimal` | `XdQuantity`, `XdDecimalList` |
| `boolean` | `XdBoolean`, `XdBooleanList` |
| `date`, `datetime`, `time` | `XdTemporal` |

### `mapping_confirm`

Confirm and persist a set of column-to-component mappings to cache.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `mapping_name` | str | Yes | — | Name for this mapping configuration |
| `mappings` | list[dict] | Yes | — | List of mapping entries (see below) |

Each mapping entry requires: `column_name` (str), `component_ct_id` (str), `component_type` (str).

**Returns:**

```json
{
  "mapping_name": "patient_mapping",
  "count": 5,
  "path": ".sdc-cache/mappings/patient_mapping.json"
}
```

### `mapping_list`

List all saved mapping configurations from cache.

**Parameters:** None.

**Returns:** `list[dict]` — each with `name`, `count`, `path`.

---

## Generator Agent

Produces **sample** SDC4 XML records for testing a published model, by substituting datasource values into the model's skeleton XML using field mappings.

**Limits.** Records come from a **CSV or JSON file** datasource, or from a `record` dict passed in directly; SQL, MongoDB and BigQuery datasources are refused. Each record re-reads and re-parses the whole file (a JSONPath, if configured, is re-evaluated each time), so `generate_batch` over *n* rows reads the file *n* times. Use it for a handful of test records, not for loading data.

**Security:** files are written only inside `output.directory`. Mapping names and the mapping's `schema_ct_id` must be single names, with no path separators, colons or leading `..`, or the call raises `PermissionError`. The output path must resolve inside the output directory after following symlinks. `generate_batch` stops at the first refusal rather than recording it once per row. The same name check applies to every name used to build a cache path.

### `generate_instance`

Generate a single SDC4 XML instance from a mapped datasource record.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `mapping_name` | str | Yes | — | Name of the mapping configuration (from cache) |
| `row_index` | int | No | `0` | Row index to fetch from the datasource |
| `record` | dict | No | `null` | Explicit record dict (skips datasource fetch if provided) |

**Returns:**

```json
{
  "xml_path": "./output/abc123_0.xml",
  "ct_id": "abc123",
  "root_element": "sdc4:dm-abc123",
  "row_index": 0
}
```

May include `errors` list if required fields are missing or unmapped.

### `generate_batch`

Generate multiple XML instances from sequential datasource records.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `mapping_name` | str | Yes | — | Name of the mapping configuration |
| `limit` | int | No | `100` | Maximum records to process |
| `offset` | int | No | `0` | Starting row index |

**Returns:**

```json
{
  "count": 50,
  "output_dir": "./output",
  "files": ["./output/abc123_0.xml", "..."],
  "errors": []
}
```

### `generate_preview`

Preview an XML instance without writing to disk.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `mapping_name` | str | Yes | — | Name of the mapping configuration |
| `row_index` | int | No | `0` | Row index to preview |

**Returns:**

```json
{
  "xml": "<?xml version=\"1.0\"?>...",
  "ct_id": "abc123",
  "root_element": "sdc4:dm-abc123"
}
```

---

## Validation Agent

Validates sample records **locally** with [sdcvalidator](https://pypi.org/project/sdcvalidator/) against the model's published XSD 1.1 schema. The instance's own `dm-<ct_id>` names the schema, which is read from the cache or fetched once from the public catalog; validation needs no API key and costs nothing. `settle_instance` is the one authenticated, charged call. File paths are confined to the configured output directory.

### `validate_instance`

Validate one XML instance against its published schema.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml_path` | str | Yes | — | Path to XML file (must be within output directory) |
| `schema_path` | str | No | `""` | XSD to use instead of the one the instance names |
| `mode` | str | No | `strict` | `strict` reports; `recover` also writes `<name>.recovered.xml`, flagging each invalid value with an ExceptionalValue |

**Returns:**

```json
{
  "valid": false,
  "mode": "strict",
  "schema": {"ct_id": "abc123", "path": ".sdc-cache/schemas/dm-abc123.xsd"},
  "structural_errors": 0,
  "semantic_errors": 1,
  "errors": [{"tier": "semantic", "path": "...", "reason": "..."}],
  "recovered": false
}
```

In `recover` mode, when there are semantic errors only, it adds `recovered_path` and `recovered_valid`.

### `settle_instance`

Settle one exchange on the Verifiable Settlement Layer (`POST /api/v1/vsl/settle`): the layer validates the record, decides the proposed workflow transition with the model's governance, and signs a Settlement Receipt, written beside the record as `<name>.receipt.json`. Needs `sdcstudio.api_key`; costs 1,000 credits.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml_path` | str | Yes | — | Path to XML file (must be within output directory) |
| `target_state` | str | Yes | — | Workflow state the exchange moves the record to |
| `condition` | dict | Yes | — | Release condition; hashed into the receipt, never stored |
| `parties` | list[str] | Yes | — | At least two key identifiers (`https://` or `did:web:`) |
| `previous_receipt_id` | str | No | `""` | Prior receipt in the chain |

**Returns:** `settled`, `receipt_id`, `receipt_path`, `receipt`, `governance`, `verification`, `charged_credits`. Raises `InsufficientFundsError` on HTTP 402.

### `validate_batch`

Validate every `*.xml` in a directory (skipping `*.recovered.xml`), locally.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml_dir` | str | No | output directory | Directory containing XML files |
| `schema_path` | str | No | `""` | XSD for every file; otherwise each instance names its own model |
| `mode` | str | No | `strict` | `strict` or `recover`, as for `validate_instance` |

**Returns:**

```json
{
  "count": 10,
  "results": [
    {"xml_path": "...", "valid": true, "errors": []}
  ],
  "failed": 0
}
```

---

## Distribution Agent

Loads the SDC4 reference ontologies and a model's schema RDF into a development triplestore (Fuseki or GraphDB) with `bootstrap_triplestore`, and checks configured destinations with `list_destinations`.

> **Deprecated, removal planned for 4.6.0:** `inspect_package`, `distribute_package` and `distribute_batch`. They route artifact packages (`.pkg.zip`) that the validation service (VaaS) used to build. SDCStudio retired that service, and 4.5.0 removed the code that called it, so nothing produces these packages any more. The tools still work on a package you already have; each call raises a `DeprecationWarning` and adds a `deprecated` notice to its result.

### `inspect_package` (deprecated)

Inspect a `.pkg.zip` artifact package without distributing it.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `package_path` | str | Yes | — | Path to `.pkg.zip` file (must be within output directory) |

**Returns:**

```json
{
  "ct_id": "abc123",
  "instance_id": "inst_001",
  "artifacts": [
    {"type": "rdf", "filename": "abc123.ttl", "destination": "triplestore", "size_bytes": 4096}
  ],
  "manifest": {"..."},
  "deprecated": "inspect_package is deprecated and will be removed in sdc-agents 4.6.0. ..."
}
```

### `list_destinations`

List configured destinations with connectivity status.

**Parameters:** None.

**Returns:**

```json
[
  {"name": "triplestore", "type": "fuseki", "endpoint": "http://localhost:3030/sdc4/data", "status": "reachable"},
  {"name": "archive", "type": "filesystem", "endpoint": "./archive/{ct_id}/{instance_id}/", "status": "reachable"}
]
```

### `distribute_package` (deprecated)

Distribute all artifacts from a `.pkg.zip` to their configured destinations.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `package_path` | str | Yes | — | Path to `.pkg.zip` file (must be within output directory) |

**Returns:**

```json
{
  "package_path": "./output/abc123_0.pkg.zip",
  "ct_id": "abc123",
  "artifacts_distributed": 3,
  "results": [
    {"artifact": "abc123.ttl", "destination": "triplestore", "status": "delivered"}
  ],
  "deprecated": "distribute_package is deprecated and will be removed in sdc-agents 4.6.0. ..."
}
```

### `distribute_batch` (deprecated)

Distribute all `.pkg.zip` packages in a directory.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `package_dir` | str | No | output directory | Directory containing `.pkg.zip` files |

**Returns:**

```json
{
  "count": 5,
  "results": [
    {"package_path": "...", "artifacts_distributed": 3, "errors": []}
  ],
  "failed": 0,
  "deprecated": "distribute_batch is deprecated and will be removed in sdc-agents 4.6.0. ..."
}
```

### `bootstrap_triplestore`

Bootstrap a triplestore with SDC4 ontologies and schema RDF. Idempotent — checks for existing named graphs before uploading. Uses the first `fuseki` or `graphdb` destination in the config. Loads every `*.rdf` and `*.ttl` in `.sdc-cache/ontologies/` and, with `ct_id`, `.sdc-cache/schemas/dm-<ct_id>.ttl`. `catalog_download_ontologies` and `catalog_download_schema_rdf` return that content but do not write these files, so save it there first.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `ct_id` | str | No | `null` | Schema `ct_id` to load as a named graph |
| `include_third_party` | bool | No | `true` | Recorded in the audit log; currently has no effect (every cached ontology is loaded) |

**Returns:**

```json
{
  "graphs_loaded": [
    {"name": "sdc4.rdf", "graph_uri": "urn:sdc4:ontology:sdc4", "status": "loaded"},
    {"name": "sdc4.rdf", "graph_uri": "urn:sdc4:ontology:sdc4", "status": "already_exists"}
  ]
}
```

---

## Knowledge Agent

Ingests customer contextual resources (data dictionaries, glossaries, ontologies) into a local Chroma vector store for semantic context matching. Operates on local files only — no network access. Requires `chromadb` (`pip install sdc-agents[knowledge]`).

**Supported source types**: CSV, JSON, TTL (Turtle), Markdown, plain text, PDF, and DOCX. PDF support requires `pymupdf`, DOCX support requires `python-docx` — both are included in the `[knowledge]` extra.

### `ingest_knowledge_source`

Ingest a configured knowledge source into the vector store.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `source_name` | str | Yes | — | Name of a source defined in `knowledge.sources` config |
| `force_refresh` | bool | No | `false` | Re-index even if already cached |

**Returns:**

```json
{
  "source_name": "glossary",
  "type": "json",
  "path": "/data/docs/glossary.json",
  "chunks_indexed": 25,
  "status": "ready"
}
```

### `query_knowledge`

Query the knowledge vector store for relevant context.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `query_text` | str | Yes | — | Natural language query to search for |
| `limit` | int | No | `5` | Maximum number of results to return |

**Returns:**

```json
{
  "query": "patient identifier",
  "results": [
    {"source": "glossary", "text": "patient_id: A unique identifier...", "score": 0.8721}
  ],
  "result_count": 3
}
```

### `list_indexed_sources`

List all indexed knowledge sources from cache metadata.

**Parameters:** None.

**Returns:** `list[dict]` — each with `source_name`, `type`, `chunks_indexed`, `status`.

---

## Assembly Agent

Discovers catalog components matching datasource structure, proposes Cluster hierarchies, selects contextual components, and assembles published data models via the SDCStudio Assembly API. Operates on cached introspection results — no direct datasource access.

### `discover_components`

Discover catalog components matching a datasource's introspected structure.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `datasource_name` | str | Yes | — | Name of a previously introspected datasource |
| `schema_ct_id` | str | No | `null` | Schema `ct_id` to match against (must be cached) |

**Returns:**

```json
{
  "datasource": "lab_results",
  "matches": [
    {"column": "test_name", "ct_id": "clxdstr001", "label": "test-name", "type": "XdString", "score": 0.9231}
  ],
  "unmatched": ["internal_id"]
}
```

### `propose_cluster_hierarchy`

Propose a Cluster hierarchy from datasource structure and component matches.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `datasource_name` | str | Yes | — | Name of the datasource |
| `component_matches` | list[dict] | Yes | — | Component matches from `discover_components` |

**Returns:**

```json
{
  "hierarchy": {
    "label": "lab-results",
    "components": [{"ct_id": "clxdstr001"}],
    "clusters": []
  },
  "cluster_count": 1
}
```

### `select_contextual_components`

Select contextual components (audit, attestation, party) from the default library project.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `context_description` | str | No | `null` | Optional description to guide component selection |

**Returns:**

```json
{
  "contextual": {
    "audit": {"ct_id": "clctx_audit_cluster", "label": "audit-trail"},
    "attestation": {"ct_id": "clctx_attest_cluster", "label": "attestation"},
    "party": {"ct_id": "clctx_party_cluster", "label": "party-identifier"}
  },
  "project": "SDC4-Core"
}
```

### `assemble_model`

Assemble a data model by calling the SDCStudio Assembly API. Fail-closed: the entire request is rejected if any referenced component is invalid.

**Important**: New components and data models are created in the authenticated user's **Default Project**, configured in SDCStudio at **Settings > Preferences**. The project is resolved server-side from the Modeler profile — it is not sent in the API request. If no default project is set, assembly will return an error.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `title` | str | Yes | — | Title for the new data model |
| `description` | str | Yes | — | Description of the data model |
| `assembly_tree` | dict | Yes | — | Complete assembly tree with hierarchy and components |
| `contextual` | dict | No | `null` | Contextual component refs (audit, attestation, party, ...) |

The Assembly API **publishes** the model (decision D4 in [COMPONENT_ASSEMBLY_DESIGN.md](../dev/COMPONENT_ASSEMBLY_DESIGN.md)); it is not a draft. When every component is reused by `ct_id`, the call returns the published model (`mode: "sync"`). When some components must be created (mint refs), SDCStudio answers HTTP 202 and finishes in the background: the result is `{mode: "async", status: "processing", task_id, data_source_ct_id, estimated_cost, new_components}`.

**Returns (sync):**

```json
{
  "dm_ct_id": "cldm00assembly01",
  "title": "Lab Results Model",
  "status": "published",
  "artifact_urls": {
    "xsd": "/api/v1/catalog/dm/cldm00assembly01/xsd/",
    "ttl": "/api/v1/catalog/dm/cldm00assembly01/ttl/"
  }
}
```

---

## Semantic Discovery Agent (ADK-only)

Searches a configured Vertex AI Search data store for semantically relevant SDC4 resources and catalog components. This agent is **ADK-native only** — it cannot be served via MCP because `VertexAiSearchTool` requires a non-None `ToolContext` for execution.

Requires `google-cloud-aiplatform` (`pip install sdc-agents[vertex-ai-search]`) and GCP Application Default Credentials.

### `vertex_ai_search`

Search the configured Vertex AI Search data store for relevant documents.

This tool is provided by ADK's built-in `VertexAiSearchTool`. The query is a natural language search string. Results include document metadata and relevance scores from the configured data store.

**Configuration**: Set `vertex_ai_search.enabled: true` and provide `data_store_id` or `search_engine_id` in `sdc-agents.yaml`. See [Configuration Reference](configuration.md#vertex_ai_search).
