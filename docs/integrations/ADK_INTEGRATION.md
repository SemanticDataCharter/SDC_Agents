# SDC Agents — Semantic Data Governance for ADK

**Turn raw data access into semantically validated, self-describing data.**

SDC Agents bridges ADK data tools (BigQuery, SQL, CSV) and the
[SDCStudio](https://sdcstudio.com) platform — adding schema governance,
validation, and knowledge graph generation to your agent pipelines.

## Available Toolsets

| Toolset | Description |
|---------|-------------|
| **IntrospectToolset** | Analyze datasource structure — infer column types and constraints from SQL, CSV, JSON, MongoDB, or BigQuery |
| **CatalogToolset** | Discover published SDC4 schemas, download artifacts (XSD, RDF, JSON-LD), check wallet balance |
| **MappingToolset** | Match datasource columns to schema components by type compatibility and name similarity |
| **AssemblyToolset** | Compose data models from catalog components — reuse existing or mint new, with wallet billing |
| **GeneratorToolset** | Generate validated XML instances, batch processing, and preview |
| **ValidationToolset** | Validate XML instances against schemas, digitally sign via VaaS API |
| **DistributionToolset** | Deliver RDF triples to Fuseki, Neo4j, GraphDB, or REST endpoints |
| **KnowledgeToolset** | Index domain documentation (JSON, CSV, TTL, Markdown, PDF, DOCX) for semantic search |

## Quick Example

Introspect a BigQuery table, discover matching schemas, and generate
validated instances — all in one agent:

```python
from google.adk.agents import LlmAgent
from google.adk.tools import BigQueryToolset

from sdc_agents.common.config import load_config
from sdc_agents.toolsets.introspect import IntrospectToolset
from sdc_agents.toolsets.catalog import CatalogToolset
from sdc_agents.toolsets.mapping import MappingToolset

# Load SDC Agents config (datasources, cache, SDCStudio connection)
config = load_config("sdc-agents.yaml")

# Compose an agent with both data access and governance toolsets
agent = LlmAgent(
    name="data_governance_agent",
    model="gemini-2.0-flash",
    description="Introspects data sources and maps them to SDC4 schemas.",
    instruction=(
        "You help data engineers govern their data. When given a datasource:\n"
        "1. Introspect the structure to discover columns and types\n"
        "2. Search the SDC4 catalog for matching published schemas\n"
        "3. Map columns to schema components by type and name similarity\n"
        "4. Report the mapping with confidence scores"
    ),
    tools=[
        BigQueryToolset(),
        IntrospectToolset(config=config),
        CatalogToolset(config=config),
        MappingToolset(config=config),
    ],
)
```

## Installation

```bash
pip install sdc-agents
```

Requires Python 3.11+ and `google-adk >= 1.25`.

## Configuration

SDC Agents uses a YAML config file with environment variable substitution:

```yaml
sdcstudio:
  base_url: "https://sdcstudio.com"
  api_key: "${SDC_API_KEY}"

datasources:
  warehouse:
    type: bigquery
    project: "${GCP_PROJECT_ID}"

cache:
  root: ".sdc-cache"

audit:
  path: ".sdc-cache/audit.jsonl"
```

Load it with:

```python
from sdc_agents.common.config import load_config
config = load_config("sdc-agents.yaml")
```

## MCP Server Mode

Each toolset can be served as an MCP tool server for use with any
MCP-compatible client:

```bash
sdc-agents serve --mcp catalog
sdc-agents serve --mcp introspect
sdc-agents serve --mcp validation
```

## What SDC4 Adds to Your Pipeline

| Without SDC4 | With SDC Agents |
|---|---|
| Raw query results | Self-describing XML instances with embedded schema references |
| Ad-hoc column names | Components mapped to published, immutable schemas (CUID2-identified) |
| No validation | Structural + semantic validation via VaaS |
| Siloed datasets | RDF triples in a knowledge graph with cross-domain type bridging |
| Manual documentation | Auto-generated XSD, HTML, JSON-LD, SHACL, GQL artifacts |

## Resources

- [SDC Agents on PyPI](https://pypi.org/project/sdc-agents/)
- [SDC Agents GitHub](https://github.com/SemanticDataCharter/SDC_Agents)
- [SDCStudio](https://sdcstudio.com)
- [SDC4 Reference Model](https://semanticdatacharter.org)
