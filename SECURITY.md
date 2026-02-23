# Security Policy

## Overview

SDC Agents is a suite of runtime Python agents that interact with customer datasources, file systems, and remote APIs. Security is foundational to the project's architecture — every design decision prioritizes least-privilege access, agent isolation, and auditability.

---

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 4.0.x   | :white_check_mark: |
| < 4.0   | :x:                |

Only the current major version (4.x.x) aligned with SDC Generation 4 receives updates.

---

## Security Model

### Agent Isolation

SDC Agents enforces strict isolation between its six agents. Each agent is an ADK `LlmAgent` with a narrowly scoped `BaseToolset`:

| Agent | Network Access | Datasource Access | File Writes |
|---|---|---|---|
| Catalog | HTTPS to SDCStudio (no auth) | None | `.sdc-cache/schemas/`, `.sdc-cache/ontologies/` |
| Introspect | None | Read-only (from config) | `.sdc-cache/introspections/` |
| Mapping | None | None | `.sdc-cache/mappings/` |
| Generator | None | Read-only (from config) | Output directory |
| Validation | HTTPS to SDCStudio VaaS (token auth) | None | Output directory |
| Distribution | Customer-local endpoints only | None | Configured destinations |

**Critical invariant**: No agent has both datasource access and network access. The Introspect Agent reads customer data but cannot make network calls. The Validation Agent makes API calls but cannot read customer datasources.

### Credential Scoping

| Credential | Available To | Not Available To |
|---|---|---|
| Datasource connection strings | Introspect Agent, Generator Agent | Catalog, Mapping, Validation, Distribution |
| VaaS API token | Validation Agent | All others |
| Triplestore/Graph DB credentials | Distribution Agent | All others |
| SDCStudio base URL | Catalog Agent, Validation Agent | Introspect, Mapping, Generator, Distribution |

The Mapping Agent has **no credentials at all** — it works entirely on cached files.

### Input Validation

Agents accept **named references** (datasource names, mapping profile names) as tool inputs, not raw file paths or connection strings. All connection details come from the operator-controlled `sdc-agents.yaml` configuration file. This prevents prompt injection attacks from tricking agents into connecting to unintended resources.

### Audit Trail

Every tool invocation writes a structured JSON record to an append-only audit log:
- Agent name, tool name, inputs (sanitized), outputs (summarized), timestamp, duration
- Sensitive values (connection strings, API tokens) are never logged
- The log is append-only — agents cannot modify or delete prior entries

---

## Data Residency

Four agents (Catalog, Introspect, Mapping, Generator) operate entirely on the customer's infrastructure with no outbound network calls (except Catalog Agent fetching public schema metadata).

The **Validation Agent** transmits XML instance documents to SDCStudio's VaaS API over HTTPS. See the [SDC Agents PRD](docs/dev/SDC_AGENTS_PRD.md#data-residency-and-vaas-transit) for the full data handling model, including what SDCStudio retains (hashes only) and what it discards (XML content).

---

## Reporting a Vulnerability

### When to Report

Please report security vulnerabilities if you discover:

- **Agent isolation bypass**: An agent accessing resources outside its defined scope
- **Credential leakage**: Credentials appearing in logs, tool outputs, or agent responses
- **Input injection**: Tool inputs that can be manipulated to access unintended resources
- **Audit log tampering**: Any way to modify or delete audit log entries
- **Network policy violation**: An agent making unauthorized network calls
- **Privilege escalation**: An agent gaining capabilities beyond its defined tools

### How to Report

**Do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report via email or private message to the repository maintainer.

### What to Include

1. **Description**: Clear description of the vulnerability
2. **Affected Agent(s)**: Which agent(s) are involved
3. **Impact**: What an attacker could achieve (data access, credential theft, scope bypass)
4. **Reproduction**: Steps to reproduce the issue
5. **Suggested Fix**: If you have a proposed solution (optional)

---

## Response Process

### Timeline

1. **Acknowledgment**: Within 48 hours of report
2. **Initial Assessment**: Within 5 business days
3. **Status Update**: Every 7 days until resolved

### Severity Levels

- **Critical**: Agent isolation bypass, credential leakage, unauthorized data access (24-hour response target)
- **High**: Audit log tampering, input injection vectors (1 week resolution target)
- **Medium**: Information disclosure, configuration weaknesses (2-4 weeks resolution target)
- **Low**: Documentation gaps, minor hardening improvements (addressed in next release)

---

## Disclosure Policy

We follow coordinated disclosure practices:

1. **Private Resolution**: Work privately to understand and fix the issue
2. **Patch Development**: Create and test a fix with security tests
3. **Public Disclosure**: Publish advisory after patch is available

---

## Security Updates

Security updates are announced through:

1. **CHANGELOG.md**: Documented in version history
2. **Release Notes**: Highlighted in GitHub releases
3. **Security Advisories**: Published via GitHub Security Advisories

---

## Security Testing

The test suite includes dedicated security tests that verify:

- Agents cannot access out-of-scope file paths
- Agents cannot make unauthorized network calls
- Tool inputs cannot override configuration-defined resources
- Audit log entries are written for every tool invocation
- Credentials are not present in audit log output

Contributors are expected to add security tests for any new tools or agent capabilities.

---

## Related Security Resources

### SDC4 Ecosystem

- [SDCStudio](https://github.com/Axius-SDC/SDCStudio) — Catalog and VaaS API provider
- [SDCRM](https://github.com/SemanticDataCharter/SDCRM) — SDC4 Reference Model

---

*Last Updated: 2026-02-23*
