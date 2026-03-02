"""Test fixtures for Assembly Agent responses."""

from __future__ import annotations


def make_assembly_api_response(
    ct_id: str = "cldm00assembly01",
    title: str = "Lab Results Model",
) -> dict:
    """Sample POST /api/v1/dmgen/assemble/ 200 response (CatalogDMDetailSerializer)."""
    return {
        "ct_id": ct_id,
        "identifier": f"dm-{ct_id}",
        "title": title,
        "description": "A model for lab test results",
        "project_name": "Healthcare Core",
        "about": "",
        "created": "2026-01-15T10:00:00Z",
        "updated": "2026-01-15T10:00:00Z",
        "artifacts": {
            "xsd": f"/api/v1/catalog/dm/{ct_id}/xsd/",
            "ttl": f"/api/v1/catalog/dm/{ct_id}/ttl/",
            "skeleton": f"/api/v1/catalog/dm/{ct_id}/skeleton/",
            "html": f"/api/v1/catalog/dm/{ct_id}/html/",
        },
        "components": [
            {
                "type": "XdString",
                "ct_id": "clxdstr001",
                "label": "test-name",
            },
            {
                "type": "XdQuantity",
                "ct_id": "clxdqty001",
                "label": "result-value",
            },
        ],
    }


def make_contextual_components_response(
    component_type: str = "audit", project: str = "SDC4-Core"
) -> dict:
    """Sample /api/v1/catalog/components/?type={type}&project={project} response.

    Returns paginated catalog component results for one contextual type.
    """
    type_data = {
        "audit": {
            "ct_id": "clctx_audit_cluster",
            "label": "audit-trail",
            "component_type": "Audit",
        },
        "attestation": {
            "ct_id": "clctx_attest_cluster",
            "label": "attestation",
            "component_type": "Attestation",
        },
        "party": {
            "ct_id": "clctx_party_cluster",
            "label": "party-identifier",
            "component_type": "Party",
        },
    }
    comp = type_data.get(component_type, type_data["audit"])
    return {
        "count": 1,
        "page": 1,
        "page_size": 50,
        "results": [
            {
                "ct_id": comp["ct_id"],
                "label": comp["label"],
                "description": f"Default {comp['component_type']} component",
                "component_type": comp["component_type"],
                "project_name": project,
                "reuse_ref": f"@{project}:{comp['label']}",
                "units": "",
                "pred_obj": [],
            },
        ],
    }


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
        "estimated_cost": estimated_cost,
        "balance": balance,
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
