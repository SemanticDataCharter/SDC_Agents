"""Tests for the Validation Toolset (4.5.0: local validation, settlement on the VSL)."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import httpx
import pytest

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.common.exceptions import InsufficientFundsError
from sdc_agents.toolsets.validation import ValidationToolset
from tests.conftest import read_audit_records
from tests.fixtures.validation_responses import (
    make_settle_402,
    make_settle_422,
    make_settle_response,
)

SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_data"
SCHEMA = SAMPLE / "sdc4_test_schema.xsd"
VALID = SAMPLE / "sdc4_test_instance_valid.xml"
INVALID = SAMPLE / "sdc4_test_instance_invalid.xml"
CT_ID = "clxyz123abcdefghijklmnop"
BASE = "https://sdcstudio.test.local"


@pytest.fixture
def validation_config(tmp_path: Path) -> SDCAgentsConfig:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return SDCAgentsConfig(
        sdcstudio={"base_url": BASE, "api_key": "test-token-secret"},
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl"), "log_level": "verbose"},
        output={"directory": str(output_dir)},
    )


@pytest.fixture
def output_dir(validation_config) -> Path:
    return Path(validation_config.output.directory)


@pytest.fixture
def schema_in_output(output_dir) -> Path:
    return Path(shutil.copy(SCHEMA, output_dir / "schema.xsd"))


def _copy(src: Path, output_dir: Path, name: str, *, model_marker: bool = False) -> Path:
    text = src.read_text()
    if model_marker:
        text = re.sub(r"^<\?xml[^>]*\?>\s*", "", text)
        text = f"<!-- model dm-{CT_ID} -->\n" + text
    path = output_dir / name
    path.write_text(text)
    return path


def _transport(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE)


def _toolset(config, handler=None):
    def default(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "no network expected"})

    return ValidationToolset(config=config, http_client=_transport(handler or default))


# --- Local validation ---


async def test_validate_instance_valid_against_an_explicit_schema(
    validation_config, output_dir, schema_in_output
):
    xml = _copy(VALID, output_dir, "record_0.xml")
    toolset = _toolset(validation_config)
    result = await toolset.validate_instance(xml_path=str(xml), schema_path=str(schema_in_output))
    assert result["valid"] is True
    assert result["structural_errors"] == 0 and result["semantic_errors"] == 0
    assert result["errors"] == []
    assert result["schema"]["path"] == str(schema_in_output)


async def test_validate_instance_reports_the_two_tiers(
    validation_config, output_dir, schema_in_output
):
    xml = _copy(INVALID, output_dir, "record_1.xml")
    toolset = _toolset(validation_config)
    result = await toolset.validate_instance(xml_path=str(xml), schema_path=str(schema_in_output))
    assert result["valid"] is False
    assert result["semantic_errors"] == 1
    assert result["errors"][0]["tier"] == "semantic"
    assert "not-a-number" in result["errors"][0]["reason"]
    assert result["recovered"] is False


async def test_recover_mode_writes_a_recovered_file(
    validation_config, output_dir, schema_in_output, monkeypatch
):
    """Recovery itself is sdcvalidator's (it needs a real SDC4 schema with the
    ExceptionalValue types); here the wiring: semantic errors in 'recover' mode
    produce <name>.recovered.xml and the result says so."""
    xml = _copy(INVALID, output_dir, "record_1.xml")
    toolset = _toolset(validation_config)
    validator = toolset._validator(schema_in_output)

    def fake_recovery(source, output_path=None, **kwargs):
        Path(output_path).write_text(VALID.read_text())

    monkeypatch.setattr(validator, "validate_with_recovery", fake_recovery)
    result = await toolset.validate_instance(
        xml_path=str(xml), schema_path=str(schema_in_output), mode="recover"
    )
    assert result["valid"] is False and result["recovered"] is True
    recovered = Path(result["recovered_path"])
    assert recovered.is_file() and recovered.name == "record_1.recovered.xml"
    assert result["recovered_valid"] is True


async def test_the_schema_is_fetched_once_from_the_catalog_by_the_instances_model_id(
    validation_config, output_dir
):
    """No schema_path: the dm-<ct_id> in the instance names it; one GET, then the cache."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == f"/api/v1/catalog/dm/{CT_ID}/xsd/":
            return httpx.Response(
                200, content=SCHEMA.read_bytes(), headers={"Content-Type": "application/xml"}
            )
        return httpx.Response(404)

    xml_a = _copy(VALID, output_dir, "a.xml", model_marker=True)
    xml_b = _copy(VALID, output_dir, "b.xml", model_marker=True)
    toolset = _toolset(validation_config, handler)
    first = await toolset.validate_instance(xml_path=str(xml_a))
    second = await toolset.validate_instance(xml_path=str(xml_b))
    assert first["valid"] and second["valid"]
    assert first["schema"]["ct_id"] == CT_ID
    assert len(calls) == 1, "the second instance used the cached schema"
    assert Path(first["schema"]["path"]).name == f"dm-{CT_ID}.xsd"


async def test_an_unpublished_model_is_a_clear_error(validation_config, output_dir):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    xml = _copy(VALID, output_dir, "a.xml", model_marker=True)
    toolset = _toolset(validation_config, handler)
    with pytest.raises(FileNotFoundError, match="published"):
        await toolset.validate_instance(xml_path=str(xml))


async def test_an_instance_without_a_model_id_needs_a_schema_path(validation_config, output_dir):
    xml = _copy(VALID, output_dir, "a.xml")
    toolset = _toolset(validation_config)
    with pytest.raises(ValueError, match="schema_path"):
        await toolset.validate_instance(xml_path=str(xml))


# --- Path confinement ---


async def test_path_confinement_rejects_outside(validation_config):
    toolset = _toolset(validation_config)
    with pytest.raises(PermissionError, match="outside the output directory"):
        await toolset.validate_instance(xml_path="/etc/passwd", schema_path=str(SCHEMA))


async def test_schema_path_is_confined_too(validation_config, output_dir):
    xml = _copy(VALID, output_dir, "a.xml")
    toolset = _toolset(validation_config)
    with pytest.raises(PermissionError):
        await toolset.validate_instance(xml_path=str(xml), schema_path=str(SCHEMA))


# --- Batch ---


async def test_validate_batch(validation_config, output_dir, schema_in_output):
    _copy(VALID, output_dir, "r0.xml")
    _copy(INVALID, output_dir, "r1.xml")
    (output_dir / "r1.recovered.xml").write_text("<skip/>")
    toolset = _toolset(validation_config)
    result = await toolset.validate_batch(schema_path=str(schema_in_output))
    assert result["count"] == 2 and result["failed"] == 1
    assert [r["valid"] for r in result["results"]] == [True, False]


# --- Settlement ---


async def test_settle_instance_writes_the_receipt(validation_config, output_dir):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=make_settle_response())

    xml = _copy(VALID, output_dir, "r0.xml")
    client = _transport(handler)
    client.headers["Authorization"] = "Token test-token-secret"
    toolset = ValidationToolset(config=validation_config, http_client=client)
    result = await toolset.settle_instance(
        xml_path=str(xml),
        target_state="released",
        condition={"type": "delivery", "ref": "PO-1"},
        parties=["https://buyer.example/.well-known/vsl-key.json", "did:web:seller.example"],
    )
    assert seen["path"] == "/api/v1/vsl/settle"
    assert seen["auth"] == "Token test-token-secret"
    assert seen["body"]["payload"] == xml.read_text(
        encoding="utf-8"
    ), "bytes as on disk, untrimmed"
    assert seen["body"]["target_state"] == "released" and len(seen["body"]["parties"]) == 2
    assert "previous_receipt_id" not in seen["body"]
    assert result["settled"] is True
    assert result["receipt_id"] == "rcpt0123456789abcdefghij"
    assert result["charged_credits"] == 1000
    receipt_path = Path(result["receipt_path"])
    assert receipt_path.name == "r0.receipt.json"
    assert json.loads(receipt_path.read_text())["decision"] == "PERMIT"


async def test_settle_402_is_insufficient_funds_in_credits(validation_config, output_dir):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json=make_settle_402())

    xml = _copy(VALID, output_dir, "r0.xml")
    toolset = _toolset(validation_config, handler)
    with pytest.raises(InsufficientFundsError) as exc_info:
        await toolset.settle_instance(xml, "released", {}, ["a", "b"])
    assert exc_info.value.estimated_cost == 1.0
    assert exc_info.value.balance_remaining == 0.25
    assert exc_info.value.estimated_cost_credits == 1000
    assert exc_info.value.balance_remaining_credits == 250


async def test_settle_422_surfaces_the_allowed_transitions(validation_config, output_dir):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json=make_settle_422())

    xml = _copy(VALID, output_dir, "r0.xml")
    toolset = _toolset(validation_config, handler)
    with pytest.raises(ValueError, match="allowed_transitions"):
        await toolset.settle_instance(xml, "archived", {}, ["a", "b"])


async def test_settle_needs_an_api_key(tmp_path, output_dir, validation_config):
    config = SDCAgentsConfig(
        sdcstudio={"base_url": BASE},
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl"), "log_level": "verbose"},
        output={"directory": str(output_dir)},
    )
    xml = _copy(VALID, output_dir, "r0.xml")
    toolset = _toolset(config)
    with pytest.raises(PermissionError, match="API key"):
        await toolset.settle_instance(xml, "released", {}, ["a", "b"])


# --- Audit ---


async def test_audit_logged_and_token_redacted(validation_config, output_dir, schema_in_output):
    xml = _copy(VALID, output_dir, "r0.xml")
    toolset = _toolset(validation_config)
    await toolset.validate_instance(xml_path=str(xml), schema_path=str(schema_in_output))
    records = read_audit_records(toolset._audit)
    assert records[-1]["tool"] == "validate_instance" and records[-1]["agent"] == "validation"
    assert "test-token-secret" not in json.dumps(records)


# --- Tool list ---


async def test_get_tools_returns_three(validation_config):
    toolset = _toolset(validation_config)
    tools = await toolset.get_tools()
    assert {t.name for t in tools} == {"validate_instance", "settle_instance", "validate_batch"}
