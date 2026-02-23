# Component Assembly Design Decisions

**Date**: 2026-02-23
**Status**: Draft
**Context**: Discussion between Tim Cook and Claude Code on Phase 5+ architecture for SDC_Agents

---

## Settled Decisions

### D3: Reference, never copy

Components are referenced by their existing `ct_id` — never copied into the target project. A component's identity is permanent and shared across models and domains. This is a core SDC principle.

The assembly endpoint creates only:
- **New Clusters** (when a needed grouping doesn't already exist)
- **The DM itself** (wiring together referenced components and Clusters)

Everything below the Cluster level already exists in the catalog.

### D4: Fully autonomous — no human-in-the-loop

The assembly pipeline produces a **published, generated data model** — not an unpublished draft for review. The output is immediately available in the SDCStudio catalog, ready for consumption by Phases 1–4 agents.

The workflow: analyze data source → discover matching components → assemble Clusters as needed → create DM → publish → generate all artifacts (XSD, XML, JSON, RDF, SHACL, GQL, HTML).

Domain experts and data stewards unleash the agents on repositories. Axius maintains standards-compliant component libraries. The agents do the assembly work that previously required ontology and graph database specialists.

### D5: Assembly API authentication

API key auth (same pattern as VaaS). The API key maps to a **Modeler user** who has a **default project** selected in their SDCStudio settings. The assembly endpoint creates the DM in that project.

### D6: Cluster naming by SDC_Agents

The Component Assembly Agent proposes Cluster labels based on its analysis of the data source structure. SDCStudio accepts the labels as provided.

### D7: Contextual component discovery via Default project

SDCStudio already maintains a **Default project** with standards-compliant contextual components (Audit, Attestation, Party, Protocol, Workflow, ACS). The assembly agent discovers these via the catalog API filtered to the Default project.

The Default project name is available in config (`sdc-agents.yaml`) so customers can supplement with their own contextual libraries if needed.

### D8: Arbitrarily complex data trees

The assembly system supports nested Cluster hierarchies of arbitrary depth — Clusters within Clusters — reflecting the actual structure of the data source. This is not limited to flat "pick components and group them."

Contextual components (Audit, Attestation, Party, etc.) from the Default project are attached to the DM's contextual slots, just like data components.

### D9: Intelligence on both sides

- **SDC_Agents**: Analysis intelligence — understand data sources, discover matching components, propose hierarchical structure, name Clusters
- **SDCStudio**: Assembly intelligence — validate references, create Clusters, wire component references, publish, run full generation pipeline

Both sides are intelligent. The API boundary between them carries a structured tree spec, not raw data.

---

## Settled: Knowledge Agent for Customer Context (Phase 5+)

The Component Assembly Agent needs to understand not just the *structure* of data sources but their *meaning*. Customer-side contextual resources provide this:

- **Data dictionaries** (CSV, JSON, database metadata)
- **Documentation** (PDFs via Form2SDCTemplate, Markdown, Word docs)
- **Metadata repositories** (data catalogs, glossaries)
- **Existing ontologies/vocabularies** the customer uses

This requires a **Knowledge Agent** (or expanded Introspect Agent) that:

1. Ingests customer contextual resources
2. Builds a local knowledge index in `.sdc-cache/knowledge/`
3. Provides semantic context to the Component Assembly Agent for better matching, naming, and contextual component selection

Configuration via `sdc-agents.yaml`:

```yaml
knowledge:
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
```

**Security**: The Knowledge Agent has read-only access to customer-provided files (like the Introspect Agent) and no network access. Knowledge stays local.

---

## Impact on SDC_Agents Architecture

### Agent count expands

Phases 1–4 define 6 agents. Phase 5+ adds:

| Agent | Purpose |
|---|---|
| **Knowledge Agent** | Ingest customer contextual resources (data dictionaries, PDFs, ontologies) into local knowledge index |
| **Component Assembly Agent** | Analyze data sources, discover matching catalog components, propose Cluster hierarchy, call SDCStudio assembly API |

Total: 8 agents (6 existing + 2 new).

### New SDCStudio API endpoints needed

| Endpoint | Method | Purpose |
|---|---|---|
| `POST /api/v1/dmgen/assemble/` | POST | Accept assembly tree spec, create Clusters + DM, publish, generate, return published DM |

**Assembly tree spec** (input to the endpoint):

```json
{
  "title": "Patient Vitals Record",
  "description": "Vital signs data model assembled from catalog components",
  "data": {
    "label": "Vitals Cluster",
    "components": [
      {"ct_id": "existing-component-cuid2"},
      {"ct_id": "another-component-cuid2"}
    ],
    "clusters": [
      {
        "label": "Blood Pressure Readings",
        "components": [
          {"ct_id": "systolic-component-cuid2"},
          {"ct_id": "diastolic-component-cuid2"}
        ]
      }
    ]
  },
  "contextual": {
    "audit": {"ct_id": "default-audit-cuid2"},
    "attestation": {"ct_id": "default-attestation-cuid2"},
    "party": {"ct_id": "default-party-cuid2"}
  }
}
```

SDCStudio validates all references, creates new Clusters, creates the DM, publishes, runs the full generation pipeline, and returns the published DM with all artifact URLs.

---

## Open Questions

### O7: Knowledge Agent scope

Should the Knowledge Agent be a separate agent or an expansion of the Introspect Agent? The Introspect Agent already reads customer data sources — adding knowledge resource ingestion is a natural extension. But the security model may differ (knowledge resources are documentation, not live data).

### O8: Assembly validation failures

If the assembly endpoint finds an invalid reference (unpublished component, incompatible type in a Cluster slot), does it reject the entire request or return a partial result with errors? Fail-closed (reject) is consistent with the existing security principles.

### O9: Component matching intelligence

How much semantic matching intelligence should live in the Component Assembly Agent vs. SDCStudio? The agent has the customer's knowledge context; SDCStudio has the component metadata and type system. The matching logic likely needs both.

### O10: Multi-source assembly

Can a single DM be assembled from components discovered across multiple data sources? E.g., patient demographics from a SQL database + lab results from CSV files → single Patient Record DM. This seems natural but adds complexity to the Cluster hierarchy design.

---

## Cross-References

- **SDC_Agents PRD Phase 5**: `docs/dev/SDC_AGENTS_PRD.md` — placeholder for Component Assembly Agent
- **SDCStudio API PRD**: `SDCStudio/docs/dev/agentic-registry/SDCStudio_API_Agents_PRD.md` — will need a Phase 4 addition for the assembly endpoint
- **Component Lookup Service**: `SDCStudio/src/agentic/services/component_lookup_service.py` — existing `@Project:Label` resolution logic
- **Default Project**: SDCStudio's `is_default_library` project flag for standards-compliant contextual components
