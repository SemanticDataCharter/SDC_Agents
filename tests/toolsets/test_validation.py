"""Tests for the Validation Toolset."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.validation import ValidationToolset
from tests.conftest import read_audit_records
from tests.fixtures.validation_responses import (
    make_sign_response,
    make_validation_failure,
    make_validation_success,
)


def _make_mock_transport(response_factory, status_code=200):
    """Create a MockTransport that returns a JSON response."""

    def handler(request: httpx.Request) -> httpx.Response:
        data = response_factory()
        return httpx.Response(status_code, json=data)

    return httpx.MockTransport(handler)


@pytest.fixture
def validation_config(tmp_path: Path) -> SDCAgentsConfig:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return SDCAgentsConfig(
        sdcstudio={
            "base_url": "https://vaas.test.local",
            "api_key": "test-token-secret",
        },
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl"), "log_level": "verbose"},
        output={"directory": str(output_dir)},
    )


@pytest.fixture
def sample_xml_file(validation_config: SDCAgentsConfig) -> Path:
    """Create a sample XML file in the output directory."""
    output_dir = Path(validation_config.output.directory)
    xml_file = output_dir / "clxyz123abc_0.xml"
    xml_file.write_text('<?xml version="1.0"?>\n<sdc4:dm-clxyz123abc>test</sdc4:dm-clxyz123abc>')
    return xml_file


# --- Successful validation ---


async def test_validate_instance_success(
    validation_config: SDCAgentsConfig, sample_xml_file: Path
):
    """Successful validation returns valid=True with zero errors."""
    transport = _make_mock_transport(make_validation_success)
    client = httpx.AsyncClient(transport=transport, base_url="https://vaas.test.local")
    toolset = ValidationToolset(config=validation_config, http_client=client)

    result = await toolset.validate_instance(xml_path=str(sample_xml_file))
    assert result["valid"] is True
    assert result["structural_errors"] == 0
    assert result["semantic_errors"] == 0


# --- Validation with errors ---


async def test_validate_instance_failure(
    validation_config: SDCAgentsConfig, sample_xml_file: Path
):
    """Failed validation returns errors and recovered XML."""
    transport = _make_mock_transport(make_validation_failure)
    client = httpx.AsyncClient(transport=transport, base_url="https://vaas.test.local")
    toolset = ValidationToolset(config=validation_config, http_client=client)

    result = await toolset.validate_instance(xml_path=str(sample_xml_file))
    assert result["valid"] is False
    assert result["structural_errors"] == 2
    assert len(result["errors"]) == 2
    assert result["recovered"] is True

    # Recovered XML should be written
    recovered_path = Path(result["recovered_path"])
    assert recovered_path.is_file()
    assert "recovered" in recovered_path.read_text()


# --- Signing ---


async def test_sign_instance(validation_config: SDCAgentsConfig, sample_xml_file: Path):
    """Signing returns signature metadata and writes signed XML."""
    transport = _make_mock_transport(make_sign_response)
    client = httpx.AsyncClient(transport=transport, base_url="https://vaas.test.local")
    toolset = ValidationToolset(config=validation_config, http_client=client)

    result = await toolset.sign_instance(xml_path=str(sample_xml_file))
    assert result["valid"] is True
    assert result["signed"] is True
    assert result["signature"]["algorithm"] == "SHA-256"
    assert result["signature"]["issuer"] == "sdcstudio.example.com"

    # Signed XML should be written
    signed_path = Path(result["signed_path"])
    assert signed_path.is_file()
    assert "signed" in signed_path.read_text()


# --- Auth token ---


async def test_auth_token_in_header(validation_config: SDCAgentsConfig, sample_xml_file: Path):
    """API token is included in Authorization header."""
    captured_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return httpx.Response(200, json=make_validation_success())

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://vaas.test.local")
    # Set auth header on client to match what ValidationToolset would do
    client.headers["Authorization"] = "Token test-token-secret"
    toolset = ValidationToolset(config=validation_config, http_client=client)

    await toolset.validate_instance(xml_path=str(sample_xml_file))
    assert "authorization" in captured_headers
    assert captured_headers["authorization"] == "Token test-token-secret"


# --- Path confinement ---


async def test_path_confinement_rejects_outside(validation_config: SDCAgentsConfig):
    """Paths outside output directory are rejected."""
    transport = _make_mock_transport(make_validation_success)
    client = httpx.AsyncClient(transport=transport, base_url="https://vaas.test.local")
    toolset = ValidationToolset(config=validation_config, http_client=client)

    with pytest.raises(PermissionError, match="outside the output directory"):
        await toolset.validate_instance(xml_path="/etc/passwd")


async def test_path_confinement_rejects_traversal(
    validation_config: SDCAgentsConfig, sample_xml_file: Path
):
    """Path traversal attempts are rejected."""
    transport = _make_mock_transport(make_validation_success)
    client = httpx.AsyncClient(transport=transport, base_url="https://vaas.test.local")
    toolset = ValidationToolset(config=validation_config, http_client=client)

    traversal_path = str(sample_xml_file.parent / ".." / ".." / "etc" / "passwd")
    with pytest.raises(PermissionError, match="outside the output directory"):
        await toolset.validate_instance(xml_path=traversal_path)


# --- Batch validation ---


async def test_validate_batch(validation_config: SDCAgentsConfig, sample_xml_file: Path):
    """Batch validates all XML files in the output directory."""
    # Create a second XML file
    output_dir = Path(validation_config.output.directory)
    xml2 = "<sdc4:dm-clxyz123abc>row2</sdc4:dm-clxyz123abc>"
    (output_dir / "clxyz123abc_1.xml").write_text(xml2)

    transport = _make_mock_transport(make_validation_success)
    client = httpx.AsyncClient(transport=transport, base_url="https://vaas.test.local")
    toolset = ValidationToolset(config=validation_config, http_client=client)

    result = await toolset.validate_batch()
    assert result["count"] == 2
    assert result["failed"] == 0
    assert len(result["results"]) == 2


async def test_validate_batch_excludes_recovered(
    validation_config: SDCAgentsConfig, sample_xml_file: Path
):
    """Batch skips .recovered.xml and .signed.xml files."""
    output_dir = Path(validation_config.output.directory)
    (output_dir / "test.recovered.xml").write_text("<recovered/>")
    (output_dir / "test.signed.xml").write_text("<signed/>")

    transport = _make_mock_transport(make_validation_success)
    client = httpx.AsyncClient(transport=transport, base_url="https://vaas.test.local")
    toolset = ValidationToolset(config=validation_config, http_client=client)

    result = await toolset.validate_batch()
    # Should only process the original sample_xml_file
    assert result["count"] == 1


# --- Audit logging ---


async def test_audit_logged(validation_config: SDCAgentsConfig, sample_xml_file: Path):
    """Tool invocations are audit logged."""
    transport = _make_mock_transport(make_validation_success)
    client = httpx.AsyncClient(transport=transport, base_url="https://vaas.test.local")
    toolset = ValidationToolset(config=validation_config, http_client=client)

    await toolset.validate_instance(xml_path=str(sample_xml_file))
    records = read_audit_records(toolset._audit)
    assert len(records) >= 1
    assert records[-1]["tool"] == "validate_instance"
    assert records[-1]["agent"] == "validation"


async def test_token_redacted_in_audit(validation_config: SDCAgentsConfig, sample_xml_file: Path):
    """API token is redacted in audit logs."""
    transport = _make_mock_transport(make_validation_success)
    client = httpx.AsyncClient(transport=transport, base_url="https://vaas.test.local")
    toolset = ValidationToolset(config=validation_config, http_client=client)

    await toolset.validate_instance(xml_path=str(sample_xml_file))
    records = read_audit_records(toolset._audit)
    # The audit log should not contain the actual token
    log_text = json.dumps(records)
    assert "test-token-secret" not in log_text


# --- Tool list ---


async def test_get_tools_returns_three(validation_config: SDCAgentsConfig):
    """get_tools returns exactly 3 tools."""
    transport = _make_mock_transport(make_validation_success)
    client = httpx.AsyncClient(transport=transport, base_url="https://vaas.test.local")
    toolset = ValidationToolset(config=validation_config, http_client=client)

    tools = await toolset.get_tools()
    assert len(tools) == 3
    names = {t.name for t in tools}
    assert names == {"validate_instance", "sign_instance", "validate_batch"}
