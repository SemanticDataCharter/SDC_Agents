# Data Platform Landscape Analysis

*February 2026*

How SDC Agents fits into the Databricks, Snowflake, and Google ADK ecosystem.

---

## The Lay of the Land

### Databricks: Framework-agnostic, MCP-native, Unity Catalog-governed

- **Agent Bricks** automates agent creation with auto-optimization (TAO, ALHF) — enterprises declare a task and connect data, Databricks builds the agent
- **MCP is their universal tool protocol** — managed MCP servers for Vector Search, Genie (NL-to-SQL), DBSQL, and Unity Catalog Functions
- **Framework-agnostic authoring**: wrap your LangGraph/OpenAI/LlamaIndex agent with `ResponsesAgent`, deploy on Databricks
- **Unity Catalog** is the governance backbone — tool registry, data access control, credential management, audit
- **No Google ADK integration** — but their `databricks-mcp` server means any MCP client can connect

### Snowflake: Platform-centric, data-never-leaves

- **Cortex Agents** is a managed server-side runtime — agents run inside Snowflake, not on your machine
- **Three built-in tool types**: Cortex Analyst (NL-to-SQL), Cortex Search (semantic/unstructured), Custom Tools (stored procedures/UDFs)
- **Managed MCP server** (GA) — five tool types exposing Snowflake data to any MCP client
- **OpenAI API compatibility** via Chat Completions API superset — broad SDK ecosystem access
- **Data governance inherited** from existing RBAC — agents execute with the invoking user's permissions
- **Hosts Claude natively** (3.5 Sonnet through 4.5 Sonnet on Cortex)

### Google ADK: Snowflake yes, Databricks gap

- **BigQuery** has the richest integration (7-tool native toolset)
- **MCP Toolbox for Databases** supports **Snowflake** natively (plus 25+ other databases) — but **not Databricks**
- **Application Integration Connectors** also cover Snowflake (100+ connectors) — again, no Databricks
- Databricks connectivity requires their community `databricks-mcp` server or commercial bridges (CData)

---

## Where Axius SDC Fits

### 1. SDC Agents is complementary, not competitive

Databricks and Snowflake are solving **"how do I query and transform my data with agents?"** SDC Agents solves **"how do I produce semantically rigorous, self-describing data artifacts from whatever data platform you use?"** These are different layers:

```
Databricks/Snowflake: data storage + query + governance
         ↓ (via MCP or direct connectors)
SDC Agents: semantic modeling + validation + distribution
         ↓
Triplestores, graph DBs, archives
```

Nobody else in this space is producing validated XSD/XML/RDF/SHACL/GQL from enterprise data stores. That is the unique value.

### 2. MCP is the universal integration point

All three ecosystems have converged on MCP. SDC Agents already speaks MCP. This means:

- A **Databricks user** can connect SDC Agents' MCP servers alongside Databricks' managed MCP servers in the same client (Claude Desktop, Cursor, etc.)
- A **Snowflake user** can do the same — Snowflake's managed MCP server provides the data, SDC Agents' MCP servers handle the semantic modeling
- No custom integration code needed for either platform

### 3. The Introspect Agent is the natural bridge

The Introspect Agent already handles SQL, CSV, JSON, and MongoDB. The strategic question is whether to add:

| Integration | Path | Effort |
|---|---|---|
| **Snowflake** | Already supported via MCP Toolbox for Databases (SQLAlchemy + Snowflake connector) | Low — just a `connection_string` pointing at Snowflake |
| **Databricks** | Via `databricks-mcp` as an external MCP server, or via SQLAlchemy + `databricks-sql-connector` | Medium — could work today with SQL datasource type if user provides a Databricks SQL connection string |
| **BigQuery** | Via MCP Toolbox or SQLAlchemy + `google-cloud-bigquery` | Medium — same pattern |

In practice, any platform that exposes a SQLAlchemy-compatible connection string **already works** with `introspect_sql` today. The gap is documentation and tested examples, not code.

### 4. The real moat is the SDC4 specification itself

Databricks has Agent Bricks for auto-building agents. Snowflake has Cortex Agents for server-side orchestration. Neither of them knows what an SDC4 schema is. Neither produces self-describing XML instances, validated SHACL constraints, or property graph CREATE statements.

SDC Agents is the only path from "enterprise data" to "SDC4-compliant semantic artifacts." The more platforms it connects to, the wider the funnel.

### 5. Potential big-picture positioning

> Wherever your data lives — Databricks, Snowflake, BigQuery, PostgreSQL,
> MongoDB, CSV files — SDC Agents reads it and produces validated,
> self-describing SDC4 artifacts. No XML expertise required.

---

## Concrete Next Steps to Consider

1. **Add Snowflake + Databricks connection examples** to `sdc-agents.example.yaml` and docs — show that `introspect_sql` works with their SQLAlchemy connectors today
2. **Document MCP coexistence** — show how a user configures SDC Agents MCP servers alongside Databricks/Snowflake MCP servers in Claude Desktop
3. **Consider a `bigquery` datasource type** in Phase 5+ — BigQuery doesn't use SQLAlchemy natively, so it would need a dedicated tool (or leverage MCP Toolbox's `ToolboxToolset`)
4. **Databricks Unity Catalog as a schema source** — future: could the Catalog Agent discover schemas not just from SDCStudio but from a Unity Catalog?

The core insight: SDC Agents doesn't compete with these platforms. It **consumes** data from them and **produces** something none of them can — validated semantic artifacts. MCP makes that consumption frictionless.

---

## Detailed Platform Research

### Databricks AI Agents Ecosystem

#### Agent Frameworks and SDKs

Databricks offers a **framework-agnostic** approach under the umbrella of **Mosaic AI Agent Framework**:

- **Supported authoring frameworks**: LangGraph/LangChain, OpenAI Agents SDK, LlamaIndex, and custom/pure Python
- **ResponsesAgent wrapper**: Author your agent in any supported framework, then wrap it with `ResponsesAgent` for automatic compatibility with Databricks AI Playground, Agent Evaluation, and Databricks Apps deployment
- **MLflow AgentServer**: Async FastAPI-based server providing built-in tracing, observability, request routing, logging, and error handling
- **Agent Bricks** (GA): Automated agent-building system that generates high-quality agents from a declared use case and connected data sources, using:
  - **TAO (Test-Adaptive Optimization)**: Model tuning using only unlabeled usage data via test-time compute and reinforcement learning
  - **ALHF (Agent Learning from Human Feedback)**: Translates natural language guidance into technical optimizations
- **MLflow 3.0** (GA): Redesigned for GenAI — cross-platform agent monitoring, tracing, prompt management, quality metrics

**Four pre-built Agent Bricks types**:
1. Information Extraction Agent — unstructured docs to structured fields
2. Knowledge Assistant Agent — cited answers grounded in enterprise data
3. Multi-Agent Supervisor — coordinates multiple sub-agents across Genie spaces and MCP
4. Custom LLM Agent — text transformation with domain-specific rules

#### Tool Integration (MCP)

Three MCP server categories:
- **Managed MCP Servers** (Databricks-hosted): Vector Search, Genie Space, DBSQL, Unity Catalog Functions
- **External MCP Servers**: Secure connections to third-party MCP servers outside Databricks
- **Custom MCP Servers**: User-built MCP servers deployed as Databricks Apps

Unity Catalog Functions as tools (legacy but still supported) for structured data retrieval when the query is known ahead of time.

#### Data Governance and Security

- **On-Behalf-Of (OBO) Authentication**: Supervisor Agent acts as a transparent proxy for the human user — every data fetch or tool execution validated against UC permissions
- **Mosaic AI Gateway**: Central control hub enforcing governance across all foundation models and agents
- **AI Guardrails**: Prevent unwanted and unsafe data in both requests and responses
- **Attribute-Based Access Control (ABAC)**: Fine-grained governance at scale via Unity Catalog
- Full audit logging of all API access through UC Connections

#### Partnerships

LangChain/LangGraph, OpenAI Agents SDK, LlamaIndex, CrewAI, Anthropic (UC-AI library), MLflow 3.0 (cross-platform). No specific Google ADK partnership.

---

### Snowflake AI Agent Ecosystem

#### Cortex Agents (GA since November 2025)

A fully managed REST API service — not a client-side SDK, but a server-side orchestration engine running inside Snowflake.

**Four-phase agentic loop:**
1. **Planning** — parses user requests, splits complex tasks into subtasks, routes to tools
2. **Tool Use** — executes via Cortex Analyst (structured/SQL) or Cortex Search (unstructured/semantic)
3. **Reflection** — evaluates tool results, decides whether to iterate
4. **Monitor & Iterate** — collects feedback, supports continuous refinement

**Supported LLMs** (hosted within Snowflake Cortex): Claude family (3.5 Sonnet through 4.5 Sonnet), OpenAI (GPT-5, GPT-4-1), `auto` mode for automatic model selection.

#### Tool Types

| Tool Type | Purpose |
|---|---|
| Cortex Analyst | Natural language to SQL over structured data (requires semantic models) |
| Cortex Search Service | Semantic search over unstructured content |
| Custom Tools | Stored procedures or UDFs on warehouse compute |
| Web Search | Account-level opt-in |

#### Managed MCP Server (GA)

Five tool types: `CORTEX_SEARCH_SERVICE_QUERY`, `CORTEX_ANALYST_MESSAGE`, `SYSTEM_EXECUTE_SQL`, `CORTEX_AGENT_RUN` (agent-to-agent), `GENERIC` (UDFs/stored procedures). OAuth 2.0 authentication.

#### Snowpark

Serves as the compute execution layer — Python, Java, or Scala code executing within Snowflake's boundary. Custom tools for Cortex Agents are implemented as stored procedures or UDFs, which can be Snowpark-based. Data never leaves the platform.

#### Governance

- RBAC: agents execute with the invoking user's DEFAULT_ROLE permissions
- Dedicated roles: `SNOWFLAKE.CORTEX_USER` or `SNOWFLAKE.CORTEX_AGENT_USER`
- Authentication: Programmatic Access Tokens, JWT key pairs, or OAuth
- MCP server security: OAuth 2.0 with least-privilege roles

#### Partnerships

OpenAI (GPT-5 hosted natively), Anthropic (Claude hosted natively), Google (Gemini 3 announced), LangChain (`ChatSnowflakeCortex`), n8n, Accenture AI Refinery. No direct Google ADK integration — MCP is the bridge.

---

### Google ADK Data Integrations

#### BigQuery (richest first-party support)

`BigQueryToolset` provides 7 built-in tools: `list_dataset_ids`, `get_dataset_info`, `list_table_ids`, `get_table_info`, `execute_sql`, `forecast`, `ask_data_insights`. Write mode controls via `BigQueryToolConfig`.

#### MCP Toolbox for Databases (v0.27.0, 25+ databases)

| Category | Databases |
|---|---|
| GCP Native | BigQuery, AlloyDB, Cloud SQL (PG/MySQL/MSSQL), Spanner, Firestore, Bigtable, Dataplex |
| Relational | PostgreSQL, MySQL, SQL Server, SQLite, MariaDB, Firebird, OceanBase |
| Cloud-native SQL | ClickHouse, TiDB, YugabyteDB, CockroachDB |
| NoSQL / KV | MongoDB, Couchbase, Redis, Valkey, Cassandra |
| Graph | Neo4j, Dgraph |
| Analytics | Trino, Looker |
| Data Platforms | **Snowflake** (supported), MindsDB |

**Databricks is NOT supported** in MCP Toolbox or Application Integration Connectors.

#### Integration Summary

| Platform | First-Party ADK | MCP Toolbox | Integration Connectors | Third-Party |
|---|---|---|---|---|
| BigQuery | Native toolset (7 tools) | Yes | Yes | N/A |
| Snowflake | No native toolset | Yes | Yes | CData, Composio |
| Databricks | None | No | No | MCP server, CData |
| Redshift | No native toolset | No | Yes | — |
| MongoDB | Vector search integration | Yes | Yes | — |
| Neo4j | No native toolset | Yes | Yes | — |

---

## Sources

- [Databricks AI Agent Tools](https://docs.databricks.com/aws/en/generative-ai/agent-framework/agent-tool)
- [Databricks MCP](https://docs.databricks.com/aws/en/generative-ai/mcp/)
- [Databricks Agent Bricks](https://www.databricks.com/company/newsroom/press-releases/databricks-launches-agent-bricks-new-approach-building-ai-agents)
- [Snowflake Cortex Agents](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents)
- [Snowflake Managed MCP Server](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-mcp)
- [Google ADK BigQuery Integration](https://google.github.io/adk-docs/integrations/bigquery/)
- [MCP Toolbox for Databases](https://googleapis.github.io/genai-toolbox/getting-started/introduction/)
- [Google ADK Integrations](https://google.github.io/adk-docs/integrations/)
