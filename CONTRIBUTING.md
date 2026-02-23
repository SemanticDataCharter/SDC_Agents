# Contributing to SDC Agents

Thank you for your interest in contributing to SDC Agents! This document provides guidelines for contributing to the project.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Getting Started](#getting-started)
- [Contribution Workflow](#contribution-workflow)
- [Development Guidelines](#development-guidelines)
- [Quality Standards](#quality-standards)
- [Review Process](#review-process)

---

## Code of Conduct

This project adheres to a Code of Conduct that all contributors are expected to follow. Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before contributing.

---

## How Can I Contribute?

### Encouraged Contributions

- **Agent improvements**: Enhance existing agent tools with better type inference, error handling, or performance
- **New datasource connectors**: Add support for additional datasource types in the Introspect Agent (e.g., Parquet, Avro, MongoDB)
- **New distribution connectors**: Add destination types to the Distribution Agent (e.g., Elasticsearch, S3, MQTT)
- **Documentation**: Clarify agent specifications, fix typos, add usage examples
- **Bug reports**: Report issues with agent behavior, tool output, or configuration handling
- **Security improvements**: Strengthen agent isolation, audit logging, or credential handling
- **Tests**: Expand test coverage, add integration tests, improve security tests

### Contributions Requiring Discussion

- **New agents**: Adding agents beyond the defined six requires architectural discussion
- **Breaking changes**: Modifications to MCP tool schemas, configuration format, or file conventions
- **Credential handling**: Any changes to how agents access or store credentials
- **Network access changes**: Modifying which agents can make network calls

For these contributions, please open an issue first to discuss your proposal.

---

## Getting Started

### Prerequisites

- Python 3.11+
- Git
- A running SDCStudio instance (for integration tests)
- Familiarity with the [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) specification

### Development Setup

1. **Fork the Repository**
   ```bash
   # Visit https://github.com/SemanticDataCharter/SDC_Agents
   # Click "Fork" to create your own copy
   ```

2. **Clone Your Fork**
   ```bash
   git clone git@github.com:YOUR_USERNAME/SDC_Agents.git
   cd SDC_Agents
   ```

3. **Create a Virtual Environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   ```

4. **Install in Development Mode**
   ```bash
   pip install -e ".[dev]"
   ```

5. **Add Upstream Remote**
   ```bash
   git remote add upstream git@github.com:SemanticDataCharter/SDC_Agents.git
   ```

6. **Stay Updated**
   ```bash
   git fetch upstream
   git checkout main
   git merge upstream/main
   ```

---

## Contribution Workflow

### 1. Create an Issue

For significant changes, create an issue first:
- Describe the problem or enhancement
- Identify which agent(s) are affected
- Explain your proposed solution
- Wait for maintainer feedback

### 2. Create a Branch

```bash
git checkout main
git pull upstream main
git checkout -b feature/your-feature-name
```

Branch naming conventions:
- `feature/description` - New functionality or agent enhancements
- `fix/description` - Bug fixes
- `docs/description` - Documentation updates
- `security/description` - Security improvements

### 3. Make Your Changes

- Follow the [Development Guidelines](#development-guidelines) below
- Run tests locally before pushing
- Keep commits focused and atomic

### 4. Commit Your Changes

```bash
git add .
git commit -m "Brief description of changes"
```

### 5. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub.

---

## Development Guidelines

### Project Structure

```
sdc_agents/
├── agents/
│   ├── catalog/          # Catalog Agent (schema discovery)
│   ├── introspect/       # Introspect Agent (datasource structure)
│   ├── mapping/          # Mapping Agent (column-to-component)
│   ├── generator/        # Generator Agent (XML instance production)
│   ├── validation/       # Validation Agent (VaaS API)
│   └── distribution/     # Distribution Agent (artifact routing)
├── common/
│   ├── audit.py          # Shared audit log library
│   ├── config.py         # YAML configuration loader
│   └── cache.py          # .sdc-cache management
└── tests/
```

### Python Style

- Follow **PEP 8** for all Python code
- Use **Google style docstrings**
- Type hints are required for all public functions
- Maximum line length: 88 characters (Black formatter)

### Agent Isolation Rules

When contributing agent code, respect these invariants:

1. **No agent imports another agent's code** — agents are independent MCP servers
2. **Tool inputs come from MCP schema only** — never accept raw file paths or connection strings as tool input; use named references from configuration
3. **Network access is explicit** — only the Catalog Agent and Validation Agent may make HTTP calls
4. **File writes are scoped** — each agent writes only to its designated directory
5. **Credentials come from config** — never hardcode or accept credentials in tool parameters

### MCP Tool Schema

Each tool must have:
- A clear, descriptive name following the `{agent}_{action}` convention
- Input parameters with types, descriptions, and required/optional flags
- Output schema documenting the return structure
- Side effects documented (file writes, API calls)

### Testing

```bash
# Run all tests
pytest

# Run tests for a specific agent
pytest tests/agents/catalog/

# Run security tests (verify isolation)
pytest tests/security/

# Run with coverage
coverage run -m pytest
coverage report
```

**Required test categories**:
- **Unit tests**: Every tool function
- **Security tests**: Verify agents cannot access out-of-scope resources
- **Integration tests**: Against a running SDCStudio instance (marked with `@pytest.mark.integration`)

### Audit Log

All tool invocations must write to the structured audit log. Use the shared `audit.log_tool_call()` function — do not implement custom logging.

---

## Quality Standards

### Pull Request Requirements

1. All tests pass
2. Security tests pass (no isolation violations)
3. New tools have complete MCP schema definitions
4. New functionality has tests
5. Documentation updated if behavior changes
6. No new credentials exposed in tool parameters

### Commit Messages

- Use imperative mood: "Add CSV introspection" not "Added CSV introspection"
- Reference issues where applicable: "Fix #42: Handle nullable columns in SQL introspection"

---

## Review Process

### What Reviewers Look For

1. **Security**: Does it maintain agent isolation boundaries?
2. **Correctness**: Do tools produce valid outputs matching their MCP schema?
3. **Tests**: Are unit and security tests comprehensive?
4. **Documentation**: Are tool schemas and side effects documented?

### Timeline

- Initial Review: Within 5 business days
- Follow-up Reviews: Within 3 business days

---

## License

By contributing to SDC Agents, you agree that your contributions will be licensed under the Apache License 2.0.

---

## Questions?

- Open a [GitHub Discussion](https://github.com/SemanticDataCharter/SDC_Agents/discussions)
- Review the [SDC Agents PRD](docs/dev/SDC_AGENTS_PRD.md) for architecture details

Thank you for contributing to SDC Agents!
