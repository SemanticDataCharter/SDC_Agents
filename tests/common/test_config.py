"""Tests for configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sdc_agents.common.config import SDCAgentsConfig, load_config


def test_load_sample_config(sample_config_path: Path):
    """Sample config loads and validates successfully."""
    config = load_config(sample_config_path)
    assert isinstance(config, SDCAgentsConfig)
    assert config.sdcstudio.base_url == "https://sdcstudio.test.local"
    assert config.cache.root == ".test-cache"
    assert config.cache.ttl_hours == 1
    assert config.audit.log_level == "verbose"


def test_datasources_parsed(sample_config_path: Path):
    """Datasource entries are parsed correctly."""
    config = load_config(sample_config_path)
    assert "test_db" in config.datasources
    assert config.datasources["test_db"].type == "sql"
    assert "test_csv" in config.datasources
    assert config.datasources["test_csv"].type == "csv"


def test_env_var_substitution(tmp_path: Path):
    """${VAR} placeholders are substituted from environment."""
    config_file = tmp_path / "test.yaml"
    config_file.write_text(
        'sdcstudio:\n  base_url: "https://${TEST_SDC_HOST}"\n'
    )
    os.environ["TEST_SDC_HOST"] = "my-server.example.com"
    try:
        config = load_config(config_file)
        assert config.sdcstudio.base_url == "https://my-server.example.com"
    finally:
        del os.environ["TEST_SDC_HOST"]


def test_missing_env_var_raises(tmp_path: Path):
    """Missing environment variable causes KeyError (fail closed)."""
    config_file = tmp_path / "test.yaml"
    config_file.write_text(
        'sdcstudio:\n  base_url: "${NONEXISTENT_SDC_VAR}"\n'
    )
    # Ensure it's not set
    os.environ.pop("NONEXISTENT_SDC_VAR", None)
    with pytest.raises(KeyError, match="NONEXISTENT_SDC_VAR"):
        load_config(config_file)


def test_defaults_applied():
    """Default config values are set when YAML has empty sections."""
    config = SDCAgentsConfig()
    assert config.cache.ttl_hours == 24
    assert config.audit.log_level == "standard"
    assert config.output.directory == "./output"
