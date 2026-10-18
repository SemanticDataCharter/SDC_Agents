"""Mock Verifiable Settlement Layer responses for Validation Toolset tests."""

from __future__ import annotations


def make_settle_response() -> dict:
    """POST /api/v1/vsl/settle: a signed Settlement Receipt."""
    return {
        "receipt": {
            "receipt_id": "rcpt0123456789abcdefghij",
            "version": "1.1",
            "schema_url": "https://semanticdatacharter.com/dmlib/dm-clxyz123abcdefghijklmnop.xsd",
            "decision": "PERMIT",
            "signatures": [{"alg": "ES256"}, {"alg": "ML-DSA-65"}],
        },
        "governance": {"decision": "PERMIT", "current_state": "draft", "target_state": "released"},
        "verification": {
            "tool": "pip install sdcreceipt",
            "command": "sdcreceipt verify receipt.json --keys keys.json",
            "keys_url": "https://sdcstudio.test.local/.well-known/sdcstudio-signing-keys.json",
            "schema_url": "https://semanticdatacharter.com/dmlib/dm-clxyz123abcdefghijklmnop.xsd",
        },
        "charged": "1.00",
    }


def make_settle_402() -> dict:
    """The settlement endpoint's 402 body."""
    return {
        "error": "Insufficient credits to issue a Settlement Receipt.",
        "cost": "1.00",
        "balance": "0.2500",
    }


def make_settle_422() -> dict:
    """A transition governance would not permit, with what it would."""
    return {
        "error": "Transition draft -> archived is not permitted.",
        "current_state": "draft",
        "allowed_transitions": ["released", "withdrawn"],
    }
