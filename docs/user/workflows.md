# Common Workflows

Step-by-step guides for the most common SDC Agents operations. SDC Agents are **design-time** tools: Workflow 1, building a model, is the primary use. They are not an operational ingest path; in production, data reaches Governed Data Records through the app stack or Supabase kit SDCStudio generates from a published model (see the [README](../../README.md#what-is-sdc-agents)).

The snippets call toolset methods directly to show the data flow; in practice an ADK agent or an MCP client calls the same tools.

---

## Workflow 1: Build a Model from a Datasource

Introspect a customer datasource, find reusable published components, and assemble and publish a data model in SDCStudio.

**Prerequisites:** a datasource configured in `sdc-agents.yaml`; `sdcstudio.api_key` set (the Assembly API needs token auth); and a **Default Project** set for that user in SDCStudio (**Settings > Preferences**), where the Assembly API creates new components and the data model. `select_contextual_components` also needs `sdcstudio.default_library_project`.

### Step 1: Introspect the datasource

```python
structure = await introspect.introspect_csv(datasource_name="patient_csv")
# or introspect_sql_schema / introspect_json / introspect_mongodb / introspect_bigquery
# Returns columns with inferred types; the cached copy in
# .sdc-cache/introspections/patient_csv.json holds structure only.
```

### Step 2 (optional): Index customer context

```python
await knowledge.ingest_knowledge_source(source_name="data_dictionary")
hits = await knowledge.query_knowledge(query_text="what does result_flag mean?")
```

Knowledge results inform naming and component choices in the conversation; no tool passes them into assembly automatically.

### Step 3: Discover reusable components

```python
found = await assembly.discover_components(datasource_name="patient_csv")
# {"datasource": "patient_csv", "matches": [{"column", "ct_id", "label", "type", "score"}, ...],
#  "unmatched": [{"name", "data_type", ...}, ...], "catalog_matches": 7}
```

Searches the published catalog first (scoped to the user's default project unless you pass `project_ct_id`), then matches against cached schemas by type. To rank the components of one specific published model instead, cache it with `catalog_get_schema` and use `mapping_suggest`.

### Step 4: Propose a Cluster hierarchy

```python
proposal = await assembly.propose_cluster_hierarchy(
    datasource_name="patient_csv",
    component_matches=found["matches"],
    unmatched_columns=found["unmatched"],   # omit to leave them out
)
# {"hierarchy": {...}, "cluster_count": 3, "new_component_count": 2, "reuse_component_count": 7}
```

Matched columns become reuse refs (`{"ct_id": ...}`); unmatched columns become refs for components SDCStudio will create (`{"label", "data_type"}`), which are charged. Review and edit the hierarchy before assembling.

### Step 5: Assemble and publish

```python
contextual = await assembly.select_contextual_components()
model = await assembly.assemble_model(
    title="Patient Lab Results",
    description="Lab results from the patient export",
    assembly_tree=proposal["hierarchy"],
    contextual=contextual["contextual"],
)
```

SDCStudio **publishes** the model. With only reused components the call returns it at once: `{"mode": "sync", "status": "published", "dm_ct_id": ..., "artifact_urls": {...}}`. When components must be created, SDCStudio answers HTTP 202 and finishes in the background: `{"mode": "async", "status": "processing", "task_id": ..., "estimated_cost": ...}`. An insufficient wallet raises `InsufficientFundsError`.

---

## Workflow 2: Test a Published Model with Sample Records

Generate a few XML records from sample rows and validate them against the published schema, to check that a model fits the data.

**Prerequisites:** a published model, and a **CSV or JSON** datasource holding sample rows. The generator does not read SQL, MongoDB or BigQuery, and it re-reads the whole file for every record, so keep the sample small.

### Step 1: Cache the model and its skeleton

```python
schema = await catalog.catalog_get_schema(ct_id="abc123")
skeleton = await catalog.catalog_download_skeleton(ct_id="abc123")
```

The schema is cached at `.sdc-cache/schemas/dm-abc123.json` and the skeleton at `.sdc-cache/skeletons/dm-abc123.xml`.

### Step 2: Map columns to the model's components

```python
for col in structure["columns"]:
    suggestions = await mapping.mapping_suggest(
        column_name=col["name"],
        column_type=col["inferred_type"],
        schema_ct_id="abc123",
    )

await mapping.mapping_confirm(
    mapping_name="patient_mapping",
    schema_ct_id="abc123",
    datasource="patient_csv",
    mappings=[
        {"column_name": "patient_id", "component_ct_id": "comp_1", "component_type": "XdString"},
        {"column_name": "result_value", "component_ct_id": "comp_2", "component_type": "XdQuantity"},
    ],
)
```

### Step 3: Generate sample records

```python
preview = await generator.generate_preview(mapping_name="patient_mapping", row_index=0)
batch = await generator.generate_batch(mapping_name="patient_mapping", limit=10)
# {"count": 10, "files": ["./output/abc123_0.xml", ...], "errors": []}
```

### Step 4: Validate them

```python
results = await validation.validate_batch()                 # strict
results = await validation.validate_batch(mode="recover")   # also writes *.recovered.xml
# {"count": 10, "failed": 0, "results": [...]}
```

Validation is local with `sdcvalidator` against the model's published XSD (fetched once from the public catalog) and costs nothing. Errors point at fields whose components or mappings need another look.

---

## Workflow 3: Audit and Troubleshooting

### Validate your configuration

```bash
sdc-agents validate-config
# Output: Config OK: sdc-agents.yaml

# Or with a specific config path
sdc-agents validate-config --config /path/to/config.yaml
```

If validation fails, the error message identifies the problem:

```
Error: missing environment variable: 'SDC_API_KEY'
Error: config validation failed:
  1 validation error for SDCAgentsConfig
  datasources -> my_db -> type
    Input should be 'sql', 'csv', 'json' or 'mongodb' [...]
```

### View configuration summary

```bash
sdc-agents info
```

Output:

```
Config      : sdc-agents.yaml
Cache root  : .sdc-cache
Output dir  : ./output
Audit path  : .sdc-cache/audit.jsonl

Agents (9):
  assembly         4 tools
  catalog          7 tools
  distribution     5 tools
  generator        3 tools
  introspect       6 tools
  knowledge        3 tools
  mapping          3 tools
  validation       3 tools
  semantic_discovery 1 tools  (ADK-only)

Datasources (2):
  patient_csv          type=csv
  lab_db               type=sql

Destinations (1):
  dev_triplestore      type=fuseki  endpoint=http://localhost:3030/sdc4/data
```

### Inspect the audit log

```bash
# Show last 50 records
sdc-agents audit show

# Filter by agent
sdc-agents audit show --agent catalog

# Filter by tool
sdc-agents audit show --tool introspect_csv

# Show records from the last 2 hours
sdc-agents audit show --last 2h

# Combine filters
sdc-agents audit show --agent validation --last 24h --limit 10
```

Each audit record shows:

```
---
  timestamp : 2026-02-23T14:30:00+00:00
  agent     : catalog
  tool      : catalog_get_schema
  duration  : 142 ms
  inputs    : ct_id
```

### Check destination connectivity

```python
destinations = await distribution.list_destinations()
for d in destinations:
    print(f"{d['name']}: {d['status']}")
# dev_triplestore: reachable
```

---

## Workflow 4: Bootstrapping a Development Triplestore

Load SDC4 ontologies and a model's schema RDF into a Fuseki or GraphDB instance, to explore the model's semantics while you build it. (A generated Lightweight or Enterprise app stack loads these itself at startup.)

**Prerequisites:** a `fuseki` or `graphdb` destination configured in `sdc-agents.yaml`; `bootstrap_triplestore` uses the first one it finds.

### Step 1: Put the ontologies and schema RDF in the cache

`bootstrap_triplestore` loads every `*.rdf` and `*.ttl` in `.sdc-cache/ontologies/` and, given a `ct_id`, `.sdc-cache/schemas/dm-<ct_id>.ttl`. The catalog tools return this content but do not write those files, so save it:

```python
from pathlib import Path

ontologies = await catalog.catalog_download_ontologies()
Path(".sdc-cache/ontologies/sdc4.rdf").write_text(ontologies)

rdf = await catalog.catalog_download_schema_rdf(ct_id="abc123")   # Turtle
Path(".sdc-cache/schemas/dm-abc123.ttl").write_text(rdf)
```

### Step 2: Bootstrap the triplestore

```python
result = await distribution.bootstrap_triplestore(ct_id="abc123")
for graph in result["graphs_loaded"]:
    print(f"{graph['name']}: {graph['status']}")
```

Output:

```
sdc4.rdf: loaded
dm-abc123.ttl: loaded
```

The bootstrap operation is **idempotent** — graphs that already exist are skipped (verified via SPARQL ASK query). Safe to run repeatedly.

### Named graph URIs

| Content | Graph URI Pattern |
|---|---|
| Ontology files | `urn:sdc4:ontology:{filename_stem}` |
| Schema RDF | `urn:sdc4:schema:{ct_id}` |
| Package artifacts (deprecated `distribute_package`) | `urn:sdc4:{ct_id}:{instance_id}:{artifact_type}` |
