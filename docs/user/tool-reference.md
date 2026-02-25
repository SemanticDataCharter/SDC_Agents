# Agent & Tool Reference

SDC Agents provides 31 tools across 8 agents. Each agent is an ADK `LlmAgent` with a scoped `BaseToolset`.

---

## Summary

| Agent | Tools | Network Access | Datasource Access |
|---|---|---|---|
| **Assembly** | 4 | HTTPS (Assembly API) | None |
| **Catalog** | 5 | HTTPS (SDCStudio API) | None |
| **Distribution** | 5 | Customer destinations | None |
| **Generator** | 3 | None | Read-only (CSV/JSON) |
| **Introspect** | 5 | None | Read-only |
| **Knowledge** | 3 | None | Read-only (files) |
| **Mapping** | 3 | None | None (cache only) |
| **Validation** | 3 | HTTPS (VaaS API, token auth) | None |

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

Download ontology definitions associated with a schema.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `ct_id` | str | Yes | — | CUID2 identifier of the schema |

**Returns:** `str` — RDF/XML ontology content.

---

## Introspect Agent

Examines customer datasources and extracts structure. Read-only access only. SQL queries are restricted to SELECT statements — INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, REPLACE, and MERGE are rejected.

### `introspect_sql`

Execute a read-only SQL query against a configured SQL datasource.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `datasource_name` | str | Yes | — | Name of a configured SQL datasource |
| `query` | str | Yes | — | SQL SELECT query to execute |

**Returns:** `list[dict]` — row dictionaries with column names as keys.

**Security:** Write operations are rejected with `PermissionError`.

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

Produces SDC4 XML instances by substituting datasource values into skeleton XML templates using field mappings.

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

Validates and signs XML instances via the SDCStudio VaaS API. Requires an API token (`sdcstudio.api_key`). File paths are confined to the configured output directory.

### `validate_instance`

Validate an XML instance against its schema via the VaaS API.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml_path` | str | Yes | — | Path to XML file (must be within output directory) |
| `mode` | str | No | `recover` | Validation mode: `strict` or `recover` |
| `package` | bool | No | `false` | Request an artifact package (.pkg.zip) alongside validation |

**Returns:**

```json
{
  "valid": true,
  "mode": "recover",
  "schema": {"ct_id": "abc123", "title": "Lab Results"},
  "structural_errors": 0,
  "semantic_errors": 0,
  "recovered": false,
  "errors": []
}
```

May include `recovered_path` and/or `package_path`.

### `sign_instance`

Sign a validated XML instance via the VaaS API.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml_path` | str | Yes | — | Path to XML file (must be within output directory) |
| `recover` | bool | No | `true` | Attempt recovery before signing |
| `package` | bool | No | `false` | Request an artifact package |

**Returns:**

```json
{
  "valid": true,
  "signed": true,
  "signature": {"algorithm": "...", "value": "..."},
  "verification": {"verified": true}
}
```

May include `signed_path` and/or `package_path`.

### `validate_batch`

Validate (and optionally sign) all XML instances in a directory.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `xml_dir` | str | No | output directory | Directory containing XML files |
| `sign` | bool | No | `false` | Sign valid instances after validation |
| `package` | bool | No | `true` | Request artifact packages |

**Returns:**

```json
{
  "count": 10,
  "results": [
    {"xml_path": "...", "valid": true, "signed": false, "errors": []}
  ],
  "failed": 0
}
```

---

## Distribution Agent

Routes artifact packages (`.pkg.zip`) to configured destinations: triplestores (Fuseki/GraphDB), graph databases (Neo4j HTTP API), REST APIs, and filesystem paths.

### `inspect_package`

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
  "manifest": {"..."}
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

### `distribute_package`

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
  ]
}
```

### `distribute_batch`

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
  "failed": 0
}
```

### `bootstrap_triplestore`

Bootstrap a triplestore with SDC4 ontologies and schema RDF. Idempotent — checks for existing named graphs before uploading.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `ct_id` | str | No | `null` | Schema `ct_id` to load as a named graph |
| `include_third_party` | bool | No | `true` | Load third-party ontologies from cache |

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

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `title` | str | Yes | — | Title for the new data model |
| `description` | str | Yes | — | Description of the data model |
| `assembly_tree` | dict | Yes | — | Complete assembly tree with hierarchy and components |

**Returns:**

```json
{
  "dm_ct_id": "cldm00assembly01",
  "title": "Lab Results Model",
  "status": "published",
  "artifact_urls": {
    "xsd": "/api/catalog/schemas/cldm00assembly01/artifacts/xsd/",
    "rdf": "/api/catalog/schemas/cldm00assembly01/artifacts/rdf/"
  }
}
```
