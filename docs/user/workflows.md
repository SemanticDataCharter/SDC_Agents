# Common Workflows

Step-by-step guides for the most common SDC Agents operations.

---

## Workflow 1: CSV to Validated XML

Transform a CSV file into validated, signed SDC4 XML instances with artifact packages.

**Prerequisites:** A published SDC4 schema in SDCStudio, a CSV datasource configured in `sdc-agents.yaml`.

### Step 1: Discover the target schema

```python
# Using ADK
results = await catalog_agent.catalog_list_schemas(query="lab results")
# Returns: [{"ct_id": "abc123", "title": "Lab Results Schema", ...}]
```

```bash
# Using MCP (via any connected client)
# Call tool: catalog_list_schemas with query="lab results"
```

### Step 2: Cache the schema and skeleton

```python
schema = await catalog_agent.catalog_get_schema(ct_id="abc123")
skeleton = await catalog_agent.catalog_download_skeleton(ct_id="abc123")
```

The schema is now cached at `.sdc-cache/schemas/dm-abc123.json` and the skeleton at `.sdc-cache/skeletons/dm-abc123.xml`.

### Step 3: Introspect the CSV datasource

```python
structure = await introspect_agent.introspect_csv(datasource_name="patient_csv")
# Returns: {"columns": [{"name": "patient_id", "inferred_type": "integer", ...}, ...]}
```

### Step 4: Map columns to schema components

```python
# Get suggestions for each column
for col in structure["columns"]:
    suggestions = await mapping_agent.mapping_suggest(
        column_name=col["name"],
        column_type=col["inferred_type"],
        schema_ct_id="abc123",
    )
    # Review suggestions and select the best match

# Confirm the mapping
result = await mapping_agent.mapping_confirm(
    mapping_name="patient_mapping",
    mappings=[
        {"column_name": "patient_id", "component_ct_id": "comp_1", "component_type": "XdString"},
        {"column_name": "result_value", "component_ct_id": "comp_2", "component_type": "XdQuantity"},
        # ... more mappings
    ],
)
```

### Step 5: Generate XML instances

```python
# Preview first
preview = await generator_agent.generate_preview(mapping_name="patient_mapping", row_index=0)
print(preview["xml"])

# Generate a batch
batch = await generator_agent.generate_batch(mapping_name="patient_mapping", limit=50)
# Output: {"count": 50, "files": ["./output/abc123_0.xml", ...]}
```

### Step 6: Validate and sign

```python
results = await validation_agent.validate_batch(sign=True, package=True)
# Output: {"count": 50, "failed": 0, "results": [...]}
```

### Step 7: Distribute artifact packages

```python
results = await distribution_agent.distribute_batch()
# Output: {"count": 50, "failed": 0, "results": [...]}
```

Each `.pkg.zip` is delivered to its configured destinations (triplestore, filesystem archive, etc.).

---

## Workflow 2: Audit and Troubleshooting

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
  catalog          5 tools
  distribution     5 tools
  generator        3 tools
  introspect       5 tools
  knowledge        3 tools
  mapping          3 tools
  validation       3 tools
  semantic_discovery 1 tools  (ADK-only)

Datasources (2):
  patient_csv          type=csv
  lab_db               type=sql

Destinations (2):
  triplestore          type=fuseki  endpoint=http://localhost:3030/sdc4/data
  archive              type=filesystem  endpoint=./archive/{ct_id}/{instance_id}/
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
destinations = await distribution_agent.list_destinations()
for d in destinations:
    print(f"{d['name']}: {d['status']}")
# triplestore: reachable
# archive: reachable
```

---

## Workflow 3: Bootstrapping a Triplestore

Load SDC4 ontologies and schema RDF into a Fuseki or GraphDB triplestore.

**Prerequisites:** A triplestore destination configured in `sdc-agents.yaml`, the target schema cached.

### Step 1: Download ontologies

```python
ontologies = await catalog_agent.catalog_download_ontologies(ct_id="abc123")
```

Ontology files are saved to `.sdc-cache/ontologies/`.

### Step 2: Download schema RDF

```python
rdf = await catalog_agent.catalog_download_schema_rdf(ct_id="abc123")
```

### Step 3: Bootstrap the triplestore

```python
result = await distribution_agent.bootstrap_triplestore(
    ct_id="abc123",
    include_third_party=True,
)
for graph in result["graphs_loaded"]:
    print(f"{graph['name']}: {graph['status']}")
```

Output:

```
sdc4.rdf: loaded
dc.ttl: loaded
skos.ttl: already_exists
dm-abc123.ttl: loaded
```

The bootstrap operation is **idempotent** — graphs that already exist are skipped (verified via SPARQL ASK query). Safe to run repeatedly.

### Named graph URIs

| Content | Graph URI Pattern |
|---|---|
| Ontology files | `urn:sdc4:ontology:{filename_stem}` |
| Schema RDF | `urn:sdc4:schema:{ct_id}` |
| Instance artifacts | `urn:sdc4:{ct_id}:{instance_id}:{artifact_type}` |
