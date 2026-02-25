"""Tests for the sdc-agents CLI."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from click.testing import CliRunner

from sdc_agents.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_CONFIG = str(FIXTURES / "sample_config.yaml")


def test_main_help():
    """Main --help exits 0 and lists all 4 subcommands."""
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in ("serve", "audit", "info", "validate-config"):
        assert cmd in result.output


def test_serve_help():
    """serve --help exits 0 and mentions --mcp option."""
    result = CliRunner().invoke(main, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--mcp" in result.output


def test_serve_invalid_agent():
    """serve --mcp nonexistent exits non-zero with error."""
    result = CliRunner().invoke(main, ["serve", "--mcp", "nonexistent"])
    assert result.exit_code != 0
    assert "nonexistent" in result.output


def test_serve_lists_valid_agents():
    """Error message for invalid agent includes valid agent names."""
    result = CliRunner().invoke(main, ["serve", "--mcp", "bogus"])
    assert result.exit_code != 0
    for name in (
        "assembly",
        "catalog",
        "distribution",
        "generator",
        "introspect",
        "knowledge",
        "mapping",
        "validation",
    ):
        assert name in result.output


def test_audit_show_empty(tmp_path):
    """audit show with missing log file gives graceful message."""
    result = CliRunner().invoke(
        main,
        ["audit", "show", "--audit-path", str(tmp_path / "nonexistent.jsonl")],
    )
    assert result.exit_code == 0
    assert "No audit log found" in result.output


def test_audit_show_with_records(tmp_path):
    """audit show with JSONL records displays formatted output."""
    log = tmp_path / "audit.jsonl"
    records = [
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": "catalog",
            "tool": "catalog_list_schemas",
            "inputs": {"query": "test"},
            "duration_ms": 42.5,
        },
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": "introspect",
            "tool": "introspect_sql",
            "inputs": {"datasource_name": "db", "query": "SELECT 1"},
            "duration_ms": 100.0,
        },
    ]
    log.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    result = CliRunner().invoke(main, ["audit", "show", "--audit-path", str(log)])
    assert result.exit_code == 0
    assert "catalog" in result.output
    assert "introspect" in result.output
    assert "catalog_list_schemas" in result.output
    assert "introspect_sql" in result.output


def test_audit_show_filter_agent(tmp_path):
    """--agent filter shows only matching records."""
    log = tmp_path / "audit.jsonl"
    records = [
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": "catalog",
            "tool": "catalog_list_schemas",
            "inputs": {},
            "duration_ms": 10,
        },
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": "mapping",
            "tool": "mapping_list",
            "inputs": {},
            "duration_ms": 20,
        },
    ]
    log.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    result = CliRunner().invoke(
        main, ["audit", "show", "--audit-path", str(log), "--agent", "catalog"]
    )
    assert result.exit_code == 0
    assert "catalog" in result.output
    assert "mapping_list" not in result.output


def test_audit_show_filter_last(tmp_path):
    """--last filter excludes old records."""
    log = tmp_path / "audit.jsonl"
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    new_ts = datetime.now(timezone.utc).isoformat()
    records = [
        {
            "timestamp": old_ts,
            "agent": "catalog",
            "tool": "old_tool",
            "inputs": {},
            "duration_ms": 1,
        },
        {
            "timestamp": new_ts,
            "agent": "catalog",
            "tool": "new_tool",
            "inputs": {},
            "duration_ms": 2,
        },
    ]
    log.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    result = CliRunner().invoke(main, ["audit", "show", "--audit-path", str(log), "--last", "1h"])
    assert result.exit_code == 0
    assert "new_tool" in result.output
    assert "old_tool" not in result.output


def test_info_loads_config():
    """info --config sample_config.yaml exits 0 and shows agents and destinations."""
    result = CliRunner().invoke(main, ["--config", SAMPLE_CONFIG, "info"])
    assert result.exit_code == 0
    assert "catalog" in result.output
    assert "introspect" in result.output
    assert "knowledge" in result.output
    assert "assembly" in result.output
    assert "test_triplestore" in result.output or "test_archive" in result.output
    assert "Agents (8)" in result.output


def test_validate_config_success():
    """validate-config with valid sample config exits 0."""
    result = CliRunner().invoke(main, ["--config", SAMPLE_CONFIG, "validate-config"])
    assert result.exit_code == 0
    assert "Config OK" in result.output


def test_validate_config_missing_file():
    """validate-config with nonexistent file exits 1."""
    result = CliRunner().invoke(main, ["--config", "nonexistent.yaml", "validate-config"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_validate_config_invalid_yaml(tmp_path):
    """validate-config with invalid YAML exits 1."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("datasources:\n  x:\n    type: invalid_type_not_in_enum\n")
    result = CliRunner().invoke(main, ["--config", str(bad), "validate-config"])
    assert result.exit_code == 1
    assert "Error" in result.output
