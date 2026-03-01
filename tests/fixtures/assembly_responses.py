"""Test fixtures for Assembly Agent responses."""

from __future__ import annotations


def make_assembly_api_response(
    dm_ct_id: str = "cldm00assembly01",
    title: str = "Lab Results Model",
) -> dict:
    """Sample POST /api/v1/dmgen/assemble/ response."""
    return {
        "dm_ct_id": dm_ct_id,
        "title": title,
        "status": "published",
        "artifact_urls": {
            "xsd": f"/api/catalog/schemas/{dm_ct_id}/artifacts/xsd/",
            "rdf": f"/api/catalog/schemas/{dm_ct_id}/artifacts/rdf/",
            "skeleton": f"/api/catalog/schemas/{dm_ct_id}/artifacts/skeleton/",
            "html": f"/api/catalog/schemas/{dm_ct_id}/artifacts/html/",
        },
    }


def make_contextual_components_response(project: str = "SDC4-Core") -> list[dict]:
    """Sample catalog response for default project with contextual components."""
    return [
        {
            "ct_id": "clctx_audit01",
            "title": "Audit Components",
            "project_name": project,
            "components": [
                {
                    "type": "Cluster",
                    "ct_id": "clctx_audit_cluster",
                    "label": "audit-trail",
                    "children": [],
                },
            ],
        },
        {
            "ct_id": "clctx_attest01",
            "title": "Attestation Components",
            "project_name": project,
            "components": [
                {
                    "type": "Cluster",
                    "ct_id": "clctx_attest_cluster",
                    "label": "attestation",
                    "children": [],
                },
            ],
        },
        {
            "ct_id": "clctx_party01",
            "title": "Party Components",
            "project_name": project,
            "components": [
                {
                    "type": "Cluster",
                    "ct_id": "clctx_party_cluster",
                    "label": "party-identifier",
                    "children": [],
                },
            ],
        },
    ]


def make_assembly_processing_response(
    task_id: str = "celery-task-abc123",
    data_source_ct_id: str = "clds00assembly01",
    new_components: int = 2,
    estimated_cost: str = "0.20",
) -> dict:
    """Sample HTTP 202 response for mixed (reuse + mint) assembly."""
    return {
        "status": "processing",
        "task_id": task_id,
        "data_source_ct_id": data_source_ct_id,
        "estimated_cost": estimated_cost,
        "new_components": new_components,
    }


def make_assembly_insufficient_funds_response(
    estimated_cost: str = "0.30",
    balance: str = "0.05",
) -> dict:
    """HTTP 402 response body for insufficient wallet balance."""
    return {
        "error": f"Insufficient wallet balance. Need ${estimated_cost}, have ${balance}.",
        "error_type": "insufficient_funds",
    }


def make_discover_components_result(
    datasource: str = "lab_results",
) -> dict:
    """Sample component match output from discover_components."""
    return {
        "datasource": datasource,
        "matches": [
            {
                "column": "test_name",
                "ct_id": "clxdstr001",
                "label": "test-name",
                "type": "XdString",
                "score": 0.9231,
            },
            {
                "column": "result_value",
                "ct_id": "clxdqty001",
                "label": "result-value",
                "type": "XdQuantity",
                "score": 0.8462,
            },
            {
                "column": "test_date",
                "ct_id": "clxdtmp001",
                "label": "test-date",
                "type": "XdTemporal",
                "score": 0.9000,
            },
        ],
        "unmatched": ["internal_id", "notes"],
    }
