# Configuration Reference

SDC Agents uses a single YAML configuration file. For a quick overview, see the [README configuration section](../../README.md#configuration).

---

## Full Annotated Example

```yaml
# SDCStudio API connection
sdcstudio:
  base_url: "https://sdcstudio.example.com"   # Required. Catalog + VaaS API base URL.
  api_key: "${SDC_API_KEY}"                    # Optional. VaaS token (Validation Agent only).
  toolbox_url: "http://localhost:5000"         # Optional. MCP Toolbox server for SQL adapters.

# Local cache settings
cache:
  root: ".sdc-cache"    # Cache directory path (default: .sdc-cache)
  ttl_hours: 24          # Cache TTL in hours (default: 24). Schemas are immutable — TTL applies to introspections.

# Audit logging
audit:
  path: ".sdc-cache/audit.jsonl"   # Audit log file path
  log_level: "standard"            # "standard" summarizes outputs; "verbose" logs full payloads

# Datasources — named datasource definitions
datasources:
  lab_db:
    type: "sql"
    connection_string: "${LAB_DB_CONNECTION}"   # SQLAlchemy async connection string
  patient_csv:
    type: "csv"
    path: "/data/exports/patients.csv"          # Absolute or relative file path
  records_json:
    type: "json"
    path: "/data/exports/records.json"
    jsonpath: "$.results[*]"                    # Optional JSONPath to extract records
  clinical_db:
    type: "mongodb"
    connection_string: "${MONGO_CONNECTION}"     # MongoDB connection URI
    database: "clinical"                        # MongoDB database name
    collection: "lab_results"                   # MongoDB collection name

  # BigQuery — dedicated type (no async SQLAlchemy support); uses ADC for auth
  analytics_bq:
    type: "bigquery"
    project: "my-gcp-project"                    # GCP project ID
    dataset: "clinical_data"                      # BigQuery dataset name

  # Cloud data platforms — use type: sql with the platform's SQLAlchemy driver
  snowflake_warehouse:
    type: "sql"
    connection_string: "snowflake://${SNOWFLAKE_USER}:${SNOWFLAKE_PASSWORD}@${SNOWFLAKE_ACCOUNT}/${SNOWFLAKE_DATABASE}/${SNOWFLAKE_SCHEMA}?warehouse=${SNOWFLAKE_WAREHOUSE}"
  databricks_warehouse:
    type: "sql"
    connection_string: "databricks://token:${DATABRICKS_TOKEN}@${DATABRICKS_HOST}:443/${DATABRICKS_CATALOG}.${DATABRICKS_SCHEMA}?http_path=${DATABRICKS_HTTP_PATH}"

# Output settings
output:
  directory: "./output"    # Directory for generated XML instances and packages
  formats:
    - "xml"                # Output formats list

# Destinations — named delivery targets for artifact packages
destinations:
  triplestore:
    type: "fuseki"
    endpoint: "${FUSEKI_URL}"               # SPARQL Graph Store Protocol endpoint
    auth: "${FUSEKI_AUTH}"                  # Authorization header value
    upload_method: "named_graph"            # Upload method (default: named_graph)
    graph_uri_from: "manifest"              # Graph URI source (default: manifest)
  graph_database:
    type: "neo4j"
    endpoint: "${NEO4J_URL}"               # Neo4j HTTP transactional endpoint
    auth: "${NEO4J_AUTH}"
    database: "sdc4"                       # Neo4j database name
  document_store:
    type: "rest_api"
    endpoint: "${DATA_API_URL}"
    method: "POST"                          # HTTP method: POST or PUT
    headers:                                # Custom request headers
      Authorization: "Bearer ${DATA_API_TOKEN}"
      Content-Type: "application/json"
  archive:
    type: "filesystem"
    path: "./archive/{ct_id}/{instance_id}/"   # Path pattern with {ct_id}, {instance_id} substitution
    create_directories: true                    # Create directories if missing (default: false)
```

---

## Section Reference

### `sdcstudio`

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `base_url` | str | Yes | `https://sdcstudio.example.com` | SDCStudio Catalog and VaaS API base URL |
| `api_key` | str | No | `null` | VaaS API token. Only needed by the Validation Agent. |
| `toolbox_url` | str | No | `null` | MCP Toolbox server URL for extended SQL adapters (optional) |

### `cache`

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `root` | str | No | `.sdc-cache` | Root directory for all cached data |
| `ttl_hours` | int | No | `24` | Cache time-to-live in hours |

### `audit`

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `path` | str | No | `.sdc-cache/audit.jsonl` | Path to the append-only JSONL audit log |
| `log_level` | str | No | `standard` | `standard` summarizes outputs; `verbose` logs full payloads |

### `datasources`

A named dictionary. Each entry defines a datasource the Introspect Agent can read.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | str | Yes | — | Datasource type: `sql`, `csv`, `json`, `mongodb`, or `bigquery` |
| `connection_string` | str | No | `null` | SQLAlchemy async URI (for `sql`) or MongoDB URI (for `mongodb`) |
| `path` | str | No | `null` | File path (for `csv` or `json` types) |
| `jsonpath` | str | No | `null` | JSONPath expression to extract records from JSON files |
| `database` | str | No | `null` | MongoDB database name |
| `collection` | str | No | `null` | MongoDB collection name |
| `project` | str | No | `null` | GCP project ID (for `bigquery` type) |
| `dataset` | str | No | `null` | BigQuery dataset name |

**Required fields by type:**

| Type | Required Fields |
|---|---|
| `sql` | `connection_string` |
| `csv` | `path` |
| `json` | `path` |
| `mongodb` | `connection_string`, `database`, `collection` |
| `bigquery` | `project` |

### `output`

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `directory` | str | No | `./output` | Directory for generated XML instances and artifact packages |
| `formats` | list[str] | No | `["xml"]` | Output format list |

### `destinations`

A named dictionary. Each entry defines a delivery target for the Distribution Agent.

**Common fields:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | str | Yes | — | Destination type: `fuseki`, `graphdb`, `neo4j`, `rest_api`, or `filesystem` |
| `endpoint` | str | No | `null` | HTTP endpoint URL (all types except `filesystem`) |
| `auth` | str | No | `null` | Authorization header value |

**Type-specific fields:**

| Type | Field | Default | Description |
|---|---|---|---|
| `fuseki` / `graphdb` | `upload_method` | `named_graph` | Upload method for SPARQL Graph Store Protocol |
| `fuseki` / `graphdb` | `graph_uri_from` | `manifest` | Source of graph URI |
| `neo4j` | `database` | `null` | Neo4j database name |
| `rest_api` | `method` | `null` | HTTP method (`POST` or `PUT`) |
| `rest_api` | `headers` | `null` | Custom request headers (dict) |
| `filesystem` | `path` | `null` | Path pattern. Supports `{ct_id}` and `{instance_id}` substitution. |
| `filesystem` | `create_directories` | `false` | Create parent directories if they don't exist |

---

## Environment Variable Substitution

Use `${VAR_NAME}` syntax anywhere in the YAML file:

```yaml
sdcstudio:
  api_key: "${SDC_API_KEY}"
datasources:
  my_db:
    type: sql
    connection_string: "${DB_CONNECTION}"
```

**Behavior:** Fail-closed. If a referenced environment variable is not set, configuration loading raises a `KeyError` immediately. No silent fallback to empty strings.

---

## Minimal Examples

### CSV-only (no network destinations)

```yaml
sdcstudio:
  base_url: "https://sdcstudio.example.com"

datasources:
  my_csv:
    type: csv
    path: "./data/records.csv"
```

This is enough to run the Introspect Agent (CSV introspection), Mapping Agent (suggestions from cached schemas), and Generator Agent (XML output to `./output/`).

### Full Pipeline

```yaml
sdcstudio:
  base_url: "https://sdcstudio.example.com"
  api_key: "${SDC_API_KEY}"

datasources:
  patients:
    type: csv
    path: "./data/patients.csv"
  lab_results:
    type: sql
    connection_string: "${LAB_DB_URL}"

output:
  directory: "./output"

destinations:
  triplestore:
    type: fuseki
    endpoint: "http://localhost:3030/sdc4/data"
  archive:
    type: filesystem
    path: "./archive/{ct_id}/{instance_id}/"
    create_directories: true
```

This enables all 6 agents: Catalog discovery, Introspect from CSV + SQL, Mapping, Generation, Validation + signing via VaaS, and Distribution to Fuseki + filesystem archive.

---

## Cloud Data Platforms

The `sql` datasource type uses SQLAlchemy, so any platform with a SQLAlchemy-compatible driver works with `introspect_sql` out of the box. Install the driver, set the connection string, and the Introspect Agent can read your data.

### BigQuery

BigQuery uses a dedicated `bigquery` datasource type (not `sql`) because `sqlalchemy-bigquery` does not support async engines. Authentication uses [Application Default Credentials (ADC)](https://cloud.google.com/docs/authentication/application-default-credentials).

```bash
pip install sdc-agents[bigquery]
```

```yaml
datasources:
  analytics_bq:
    type: "bigquery"
    project: "my-gcp-project"
    dataset: "clinical_data"
```

Set up ADC for authentication:

```bash
gcloud auth application-default login
# or set GOOGLE_APPLICATION_CREDENTIALS to a service account key file
```

### Snowflake

```bash
pip install snowflake-sqlalchemy
```

```yaml
datasources:
  snowflake_warehouse:
    type: sql
    connection_string: "snowflake://${SNOWFLAKE_USER}:${SNOWFLAKE_PASSWORD}@${SNOWFLAKE_ACCOUNT}/${SNOWFLAKE_DATABASE}/${SNOWFLAKE_SCHEMA}?warehouse=${SNOWFLAKE_WAREHOUSE}"
```

**Connection string format:** `snowflake://<user>:<password>@<account>/<database>/<schema>?warehouse=<warehouse>`

Set the environment variables:

```bash
export SNOWFLAKE_USER="my_user"
export SNOWFLAKE_PASSWORD="my_password"
export SNOWFLAKE_ACCOUNT="xy12345.us-east-1"    # Account identifier
export SNOWFLAKE_DATABASE="ANALYTICS"
export SNOWFLAKE_SCHEMA="PUBLIC"
export SNOWFLAKE_WAREHOUSE="COMPUTE_WH"
```

### Databricks

```bash
pip install databricks-sql-connector sqlalchemy-databricks
```

```yaml
datasources:
  databricks_warehouse:
    type: sql
    connection_string: "databricks://token:${DATABRICKS_TOKEN}@${DATABRICKS_HOST}:443/${DATABRICKS_CATALOG}.${DATABRICKS_SCHEMA}?http_path=${DATABRICKS_HTTP_PATH}"
```

**Connection string format:** `databricks://token:<token>@<host>:443/<catalog>.<schema>?http_path=<http_path>`

Set the environment variables:

```bash
export DATABRICKS_TOKEN="dapi..."                              # Personal access token
export DATABRICKS_HOST="adb-1234567890.12.azuredatabricks.net" # Workspace URL (no https://)
export DATABRICKS_CATALOG="main"
export DATABRICKS_SCHEMA="default"
export DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/abc123"       # SQL warehouse HTTP path
```

### Driver Reference

| Platform | Driver Package | Connection Prefix |
|---|---|---|
| PostgreSQL | `asyncpg` (included) | `postgresql+asyncpg://` |
| MySQL | `aiomysql` | `mysql+aiomysql://` |
| SQL Server | `aioodbc` | `mssql+aioodbc://` |
| SQLite | (built-in) | `sqlite+aiosqlite://` |
| Snowflake | `snowflake-sqlalchemy` | `snowflake://` |
| Databricks | `databricks-sql-connector`, `sqlalchemy-databricks` | `databricks://` |

Any SQLAlchemy-compatible driver works. The Introspect Agent enforces read-only access regardless of the underlying platform — only SELECT queries are permitted.

---

## Config File Location

By default, `sdc-agents` looks for `sdc-agents.yaml` in the current directory. Override with:

```bash
# CLI flag
sdc-agents --config /path/to/config.yaml info

# Environment variable
export SDC_AGENTS_CONFIG=/path/to/config.yaml
sdc-agents info
```

To validate your config before running agents:

```bash
sdc-agents validate-config
```
