# SDC Agents — Semantic Data Governance for ADK

**Build SDC4 data models from the data sources you already have.**

SDC Agents bridges ADK data tools (BigQuery, SQL, CSV) and the
[SDCStudio](https://sdcstudio.com) platform at **design time**: introspect a
source's structure, find reusable published components, and assemble and
publish a data model through SDCStudio's Assembly API. The generator and
validator produce sample records for testing a model. They are not an
operational ingest path: live data reaches Governed Data Records through the
app stack or Supabase kit SDCStudio generates from the published model.

## Available Toolsets

| Toolset | Description |
|---------|-------------|
| **IntrospectToolset** | Analyze datasource structure — infer column types and constraints from SQL, CSV, JSON, MongoDB, or BigQuery |
| **CatalogToolset** | Discover published SDC4 schemas, download artifacts (XSD, RDF, JSON-LD), check wallet balance |
| **MappingToolset** | Match datasource columns to schema components by type compatibility and name similarity |
| **AssemblyToolset** | Compose and publish data models from catalog components — reuse existing or mint new, with wallet billing |
| **GeneratorToolset** | Sample XML records for testing a model, from CSV or JSON files (re-reads the file for each row) |
| **ValidationToolset** | Validate sample records locally against their published schemas; settle an exchange on the Verifiable Settlement Layer |
| **DistributionToolset** | Load SDC4 ontologies and schema RDF into a development Fuseki or GraphDB triplestore (package delivery tools deprecated) |
| **KnowledgeToolset** | Index domain documentation (JSON, CSV, TTL, Markdown, PDF, DOCX) for semantic search |

## Quick Example

Introspect a BigQuery table, discover matching schemas, and map its columns
to schema components:

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

Requires Python 3.11+ and `google-adk >= 1.28.1` (the floor set by CVE-2026-4810).

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

## What SDC Agents Add at Design Time

| Without SDC Agents | With SDC Agents |
|---|---|
| Hand-studying source schemas | Introspected structure, types and constraints, cached without row values |
| Ad-hoc column names | Columns matched to published, immutable components (CUID2-identified) |
| Building every model from scratch | Reusable catalog components found first; only the rest are minted |
| Manual model assembly | A Cluster hierarchy proposed and published through the Assembly API |
| Guessing whether a model fits | Sample records generated and validated locally against the published XSD |

Once published, a model's XSD, RDF, JSON-LD, SHACL and GQL artifacts come from SDCStudio, and so do the generated app stacks and Supabase kits that carry operational data.

## Resources

- [SDC Agents on PyPI](https://pypi.org/project/sdc-agents/)
- [SDC Agents GitHub](https://github.com/SemanticDataCharter/SDC_Agents)
- [SDCStudio](https://sdcstudio.com)
- [SDC4 Reference Model](https://semanticdatacharter.org)
