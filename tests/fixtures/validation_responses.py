"""Mock VaaS API responses for Validation Toolset tests."""

from __future__ import annotations

import io
import json
import zipfile


def make_validation_success() -> dict:
    """Valid instance response with zero errors."""
    return {
        "valid": True,
        "mode": "strict",
        "schema": {
            "ct_id": "clxyz123abc",
            "title": "Lab Results",
        },
        "structural_errors": 0,
        "semantic_errors": 0,
        "recovered": False,
        "errors": [],
    }


def make_validation_failure() -> dict:
    """Validation response with structural errors."""
    return {
        "valid": False,
        "mode": "recover",
        "schema": {
            "ct_id": "clxyz123abc",
            "title": "Lab Results",
        },
        "structural_errors": 2,
        "semantic_errors": 0,
        "recovered": True,
        "recovered_xml": (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<sdc4:dm-clxyz123abc><!-- recovered --></sdc4:dm-clxyz123abc>"
        ),
        "errors": [
            {"line": 5, "message": "Missing required element: test-name"},
            {"line": 8, "message": "Invalid value for result-value"},
        ],
    }


def make_sign_response() -> dict:
    """Signed instance response with signature metadata."""
    return {
        "valid": True,
        "signed": True,
        "signed_xml": (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<sdc4:dm-clxyz123abc sdc4:signature="abc123">'
            "<!-- signed --></sdc4:dm-clxyz123abc>"
        ),
        "signature": {
            "algorithm": "SHA-256",
            "issuer": "sdcstudio.example.com",
            "timestamp": "2026-02-23T10:00:00Z",
            "schema_ct_id": "clxyz123abc",
            "ev_count": 4,
        },
        "verification": {
            "public_key_url": "https://sdcstudio.example.com/.well-known/sdc-signing-key",
            "verify_command": "sdc verify --instance signed.xml --key-url ...",
        },
    }


def make_insufficient_funds_response() -> dict:
    """HTTP 402 response body for insufficient wallet balance."""
    return {
        "detail": "Insufficient wallet balance.",
        "estimated_cost": "0.001",
        "balance_remaining": "0.0000",
    }


def make_package_bytes() -> bytes:
    """Small .zip artifact package fixture."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "ct_id": "clxyz123abc",
            "title": "Lab Results",
            "files": ["dm-clxyz123abc.xml", "dm-clxyz123abc.xsd"],
        }
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("dm-clxyz123abc.xml", "<sdc4:dm-clxyz123abc/>")
        zf.writestr("dm-clxyz123abc.xsd", "<xs:schema/>")
    return buf.getvalue()
