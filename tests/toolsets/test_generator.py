"""Tests for the Generator Toolset."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.generator import GeneratorToolset
from tests.conftest import read_audit_records
from tests.fixtures.generator_fixtures import (
    make_field_mapping,
    make_mapping_config,
    make_skeleton_xml,
)


@pytest.fixture
def generator_config(tmp_path: Path, csv_path: Path) -> SDCAgentsConfig:
    return SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl"), "log_level": "verbose"},
        output={"directory": str(tmp_path / "output")},
        datasources={
            "test_csv": {
                "type": "csv",
                "path": str(csv_path),
            },
        },
    )


@pytest.fixture
def populated_cache(generator_config: SDCAgentsConfig) -> SDCAgentsConfig:
    """Pre-populate cache with skeleton, field mapping, and mapping config."""
    from sdc_agents.common.cache import CacheManager

    cache = CacheManager(generator_config.cache.root)
    cache.ensure_dirs()

    ct_id = "clxyz123abc"

    # Write skeleton XML
    cache.skeleton_path(ct_id).write_text(make_skeleton_xml(ct_id))

    # Write field mapping
    cache.field_mapping_path(ct_id).write_text(json.dumps(make_field_mapping(ct_id)))

    # Write mapping config
    mapping_config = make_mapping_config("lab_mapping", ct_id, "test_csv")
    cache.mapping_path("lab_mapping").write_text(json.dumps(mapping_config))

    return generator_config


@pytest.fixture
def generator_toolset(populated_cache: SDCAgentsConfig) -> GeneratorToolset:
    return GeneratorToolset(config=populated_cache)


# --- Tool list ---


async def test_get_tools_returns_three(generator_toolset: GeneratorToolset):
    """get_tools returns exactly 3 tools."""
    tools = await generator_toolset.get_tools()
    assert len(tools) == 3
    names = {t.name for t in tools}
    assert names == {"generate_instance", "generate_batch", "generate_preview"}


# --- Single instance generation ---


async def test_generate_instance(generator_toolset: GeneratorToolset, tmp_path: Path):
    """Generate a single XML instance with substituted values."""
    result = await generator_toolset.generate_instance(mapping_name="lab_mapping", row_index=0)
    assert result["ct_id"] == "clxyz123abc"
    assert result["row_index"] == 0
    assert "xml_path" in result

    # Verify the XML was written
    xml_path = Path(result["xml_path"])
    assert xml_path.is_file()
    content = xml_path.read_text()
    assert "CBC" in content  # test_name from row 0
    assert "98.6" in content  # result value from row 0


async def test_generate_instance_with_record(generator_toolset: GeneratorToolset):
    """Generate using an explicit record dict."""
    record = {
        "test_name": "CustomTest",
        "result": "42.0",
        "collected_date": "2026-03-01",
        "is_critical": "false",
    }
    result = await generator_toolset.generate_instance(mapping_name="lab_mapping", record=record)
    xml_path = Path(result["xml_path"])
    content = xml_path.read_text()
    assert "CustomTest" in content
    assert "42.0" in content


async def test_generate_instance_missing_required(populated_cache: SDCAgentsConfig):
    """Missing required field reports error."""
    # Create a mapping config that references a required field
    # but the CSV doesn't have data for it — use a record with empty value
    toolset = GeneratorToolset(config=populated_cache)
    record = {
        "test_name": "",
        "result": "",
        "collected_date": "2026-01-15",
        "is_critical": "true",
    }
    result = await toolset.generate_instance(mapping_name="lab_mapping", record=record)
    assert "errors" in result
    assert len(result["errors"]) > 0


# --- Preview ---


async def test_generate_preview(generator_toolset: GeneratorToolset, tmp_path: Path):
    """Preview returns XML string without writing to disk."""
    output_dir = Path(generator_toolset._output_dir)
    # Count files before preview
    files_before = list(output_dir.glob("*.xml"))

    result = await generator_toolset.generate_preview(mapping_name="lab_mapping", row_index=0)
    assert "xml" in result
    assert "CBC" in result["xml"]
    assert result["ct_id"] == "clxyz123abc"

    # No new files written (only preview)
    files_after = list(output_dir.glob("*.xml"))
    assert len(files_after) == len(files_before)


# --- Batch generation ---


async def test_generate_batch(generator_toolset: GeneratorToolset):
    """Batch generates multiple files."""
    result = await generator_toolset.generate_batch(mapping_name="lab_mapping", limit=3, offset=0)
    assert result["count"] == 3
    assert len(result["files"]) == 3
    # Verify each file exists
    for f in result["files"]:
        assert Path(f).is_file()


async def test_generate_batch_stops_at_end(generator_toolset: GeneratorToolset):
    """Batch stops when datasource rows are exhausted."""
    result = await generator_toolset.generate_batch(
        mapping_name="lab_mapping", limit=100, offset=0
    )
    # CSV has 5 rows
    assert result["count"] == 5


# --- Error cases ---


async def test_missing_mapping_raises(generator_toolset: GeneratorToolset):
    """Unknown mapping name raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="not found in cache"):
        await generator_toolset.generate_instance(mapping_name="nonexistent")


async def test_missing_skeleton_raises(populated_cache: SDCAgentsConfig):
    """Missing skeleton XML raises FileNotFoundError."""
    from sdc_agents.common.cache import CacheManager

    cache = CacheManager(populated_cache.cache.root)

    # Create a mapping pointing to a non-existent schema
    bad_mapping = {
        "name": "bad_mapping",
        "schema_ct_id": "cl_nonexistent",
        "datasource": "test_csv",
        "mappings": [],
    }
    cache.mapping_path("bad_mapping").write_text(json.dumps(bad_mapping))

    toolset = GeneratorToolset(config=populated_cache)
    with pytest.raises(FileNotFoundError, match="Skeleton"):
        await toolset.generate_instance(mapping_name="bad_mapping")


# --- Audit logging ---


async def test_audit_logged(generator_toolset: GeneratorToolset):
    """Tool invocations are audit logged."""
    await generator_toolset.generate_instance(mapping_name="lab_mapping", row_index=0)
    records = read_audit_records(generator_toolset._audit)
    assert len(records) >= 1
    assert records[-1]["tool"] == "generate_instance"
    assert records[-1]["agent"] == "generator"
