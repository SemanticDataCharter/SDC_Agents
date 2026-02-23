"""Tests for the audit logger."""

from __future__ import annotations

import time

from sdc_agents.common.audit import AuditLogger
from tests.conftest import read_audit_records


def test_log_writes_record(tmp_audit: AuditLogger):
    """A log call writes a valid JSONL record."""
    start = time.monotonic()
    tmp_audit.log(
        agent="catalog",
        tool="list_schemas",
        inputs={"query": "lab"},
        outputs=[{"ct_id": "abc123"}],
        start_time=start,
    )
    records = read_audit_records(tmp_audit)
    assert len(records) == 1
    assert records[0]["agent"] == "catalog"
    assert records[0]["tool"] == "list_schemas"
    assert "timestamp" in records[0]
    assert "duration_ms" in records[0]


def test_sanitize_redacts_sensitive_keys(tmp_audit: AuditLogger):
    """Keys containing sensitive fragments are redacted."""
    start = time.monotonic()
    tmp_audit.log(
        agent="introspect",
        tool="sql_query",
        inputs={
            "connection_string": "postgresql://user:pass@host/db",
            "api_token": "secret-token-123",
            "api_key": "my-key",
            "password": "hunter2",
            "secret_value": "shh",
            "query": "SELECT * FROM t",
        },
        outputs={"rows": 5},
        start_time=start,
    )
    records = read_audit_records(tmp_audit)
    inputs = records[0]["inputs"]
    assert inputs["connection_string"] == "***REDACTED***"
    assert inputs["api_token"] == "***REDACTED***"
    assert inputs["api_key"] == "***REDACTED***"
    assert inputs["password"] == "***REDACTED***"
    assert inputs["secret_value"] == "***REDACTED***"
    assert inputs["query"] == "SELECT * FROM t"


def test_standard_level_summarizes(tmp_path):
    """Standard log level summarizes list outputs to counts."""
    audit = AuditLogger(tmp_path / "audit.jsonl", log_level="standard")
    start = time.monotonic()
    audit.log(
        agent="catalog",
        tool="list_schemas",
        inputs={},
        outputs=[{"ct_id": "a"}, {"ct_id": "b"}],
        start_time=start,
    )
    records = read_audit_records(audit)
    outputs = records[0]["outputs"]
    assert outputs["_type"] == "list"
    assert outputs["_count"] == 2


def test_verbose_level_preserves_outputs(tmp_audit: AuditLogger):
    """Verbose log level preserves full output content."""
    start = time.monotonic()
    tmp_audit.log(
        agent="catalog",
        tool="get_schema",
        inputs={},
        outputs={"ct_id": "abc", "title": "Test"},
        start_time=start,
    )
    records = read_audit_records(tmp_audit)
    assert records[0]["outputs"]["ct_id"] == "abc"


def test_append_only(tmp_audit: AuditLogger):
    """Multiple logs append, not overwrite."""
    for i in range(3):
        tmp_audit.log(
            agent="test",
            tool=f"tool_{i}",
            inputs={},
            outputs={},
            start_time=time.monotonic(),
        )
    records = read_audit_records(tmp_audit)
    assert len(records) == 3
