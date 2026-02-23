"""Test fixtures for Distribution Agent — sample manifests, packages, and configs."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO


def make_manifest(
    ct_id: str = "clxyz123abc",
    instance_id: str = "inst001",
) -> dict:
    """Return a sample artifact package manifest."""
    return {
        "ct_id": ct_id,
        "instance_id": instance_id,
        "timestamp": "2026-02-23T14:30:00Z",
        "artifacts": [
            {"type": "xml", "filename": "instance.xml", "destination": "archive"},
            {"type": "json", "filename": "instance.json", "destination": "document_store"},
            {"type": "rdf", "filename": "instance.ttl", "destination": "triplestore"},
            {"type": "gql", "filename": "instance.gql", "destination": "graph_database"},
            {"type": "jsonld", "filename": "instance.jsonld", "destination": "linked_data"},
        ],
    }


def make_package_zip(
    ct_id: str = "clxyz123abc",
    instance_id: str = "inst001",
) -> bytes:
    """Build a .pkg.zip in memory with manifest and dummy artifact files."""
    manifest = make_manifest(ct_id, instance_id)
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("instance.xml", '<sdc4:dm-clxyz123abc xmlns:sdc4="urn:sdc4">test</sdc4:dm-clxyz123abc>')
        zf.writestr("instance.json", '{"ct_id": "clxyz123abc", "data": "test"}')
        zf.writestr("instance.ttl", "@prefix sdc4: <urn:sdc4:> .\nsdc4:test a sdc4:Instance .")
        zf.writestr("instance.gql", 'CREATE (n:Instance {ct_id: "clxyz123abc"})')
        zf.writestr("instance.jsonld", '{"@context": {"sdc4": "urn:sdc4:"}, "@id": "urn:sdc4:clxyz123abc"}')
    return buf.getvalue()


def make_destination_configs() -> dict:
    """Return sample destination config dicts for testing."""
    return {
        "triplestore": {
            "type": "fuseki",
            "endpoint": "http://localhost:3030/sdc4/data",
            "auth": "Basic dXNlcjpwYXNz",
            "upload_method": "named_graph",
        },
        "graph_database": {
            "type": "neo4j",
            "endpoint": "http://localhost:7474",
            "auth": "Basic bmVvNGo6dGVzdA==",
            "database": "sdc4",
        },
        "document_store": {
            "type": "rest_api",
            "endpoint": "http://localhost:9200/sdc4/_doc",
            "method": "POST",
            "headers": {"Authorization": "Bearer test-token"},
        },
        "archive": {
            "type": "filesystem",
            "path": "./archive/{ct_id}/{instance_id}/",
            "create_directories": True,
        },
        "linked_data": {
            "type": "rest_api",
            "endpoint": "http://localhost:8080/jsonld",
            "method": "POST",
        },
    }
