"""Shared test fixtures for SDC Agents."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.cache import CacheManager
from sdc_agents.common.config import SDCAgentsConfig, load_config


@pytest.fixture
def sample_config_path() -> Path:
    return Path(__file__).parent / "fixtures" / "sample_config.yaml"


@pytest.fixture
def config(sample_config_path: Path) -> SDCAgentsConfig:
    return load_config(sample_config_path)


@pytest.fixture
def tmp_cache(tmp_path: Path) -> CacheManager:
    cache = CacheManager(tmp_path / ".sdc-cache")
    cache.ensure_dirs()
    return cache


@pytest.fixture
def tmp_audit(tmp_path: Path) -> AuditLogger:
    return AuditLogger(tmp_path / "audit.jsonl", log_level="verbose")


@pytest.fixture
def csv_path() -> Path:
    return Path(__file__).parent / "fixtures" / "sample_data" / "lab_results.csv"


def read_audit_records(audit: AuditLogger) -> list[dict]:
    """Helper to read all JSONL records from an audit log."""
    records = []
    if audit.path.exists():
        for line in audit.path.read_text().strip().split("\n"):
            if line:
                records.append(json.loads(line))
    return records
