"""Mock SDCStudio Catalog API responses matching serializer shapes."""


def make_schema_list_response() -> list[dict]:
    """List of DM summaries as returned by /api/v1/catalog/dms/."""
    return [
        {
            "ct_id": "clxyz123abc",
            "identifier": "dm-clxyz123abc",
            "title": "Lab Results",
            "description": "Standard laboratory test results model",
            "project_name": "Healthcare Core",
            "about": "",
            "created": "2026-01-15T10:00:00Z",
            "updated": "2026-01-15T10:00:00Z",
        },
        {
            "ct_id": "clxyz456def",
            "identifier": "dm-clxyz456def",
            "title": "Patient Demographics",
            "description": "Patient demographic information model",
            "project_name": "Healthcare Core",
            "about": "",
            "created": "2026-01-16T10:00:00Z",
            "updated": "2026-01-16T10:00:00Z",
        },
    ]


def make_schema_detail_response(ct_id: str = "clxyz123abc") -> dict:
    """Full DM detail as returned by /api/v1/catalog/dm/{ct_id}/."""
    return {
        "ct_id": ct_id,
        "identifier": f"dm-{ct_id}",
        "title": "Lab Results",
        "description": "Standard laboratory test results model",
        "project_name": "Healthcare Core",
        "about": "",
        "created": "2026-01-15T10:00:00Z",
        "updated": "2026-01-15T10:00:00Z",
        "components": [
            {
                "type": "Cluster",
                "ct_id": "clcluster001",
                "label": "lab-result-entry",
                "description": "A single lab result entry",
                "children": [
                    {
                        "type": "XdString",
                        "ct_id": "clxdstr001",
                        "label": "test-name",
                        "description": "Name of the laboratory test",
                    },
                    {
                        "type": "XdQuantity",
                        "ct_id": "clxdqty001",
                        "label": "result-value",
                        "description": "Numeric result value with units",
                        "units": "mg/dL",
                    },
                    {
                        "type": "XdTemporal",
                        "ct_id": "clxdtmp001",
                        "label": "collection-date",
                        "description": "Date the sample was collected",
                    },
                ],
            },
        ],
        "artifacts": {
            "xsd": f"/api/v1/catalog/dm/{ct_id}/xsd/",
            "ttl": f"/api/v1/catalog/dm/{ct_id}/ttl/",
            "skeleton": f"/api/v1/catalog/dm/{ct_id}/skeleton/",
            "html": f"/api/v1/catalog/dm/{ct_id}/html/",
        },
    }


def make_rdf_response() -> str:
    """Sample RDF/XML content for a schema."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:sdc="https://semanticdatacharter.org/ns/">
  <sdc:DataModel rdf:about="urn:sdc4:clxyz123abc">
    <sdc:title>Lab Results</sdc:title>
  </sdc:DataModel>
</rdf:RDF>"""


def make_skeleton_response() -> str:
    """Sample XML skeleton for a schema."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<sdc4:dm-clxyz123abc
    xmlns:sdc4="https://semanticdatacharter.org/ns/sdc4"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="https://semanticdatacharter.org/ns/sdc4 dm-clxyz123abc.xsd">
  <!-- Skeleton instance -->
</sdc4:dm-clxyz123abc>"""


def make_ontologies_response() -> str:
    """Sample ontology RDF content."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:owl="http://www.w3.org/2002/07/owl#">
  <owl:Ontology rdf:about="urn:sdc4:ontology:healthcare">
    <owl:versionInfo>4.0.0</owl:versionInfo>
  </owl:Ontology>
</rdf:RDF>"""


def make_wallet_response(
    balance: str = "25.00",
    auto_reload_enabled: bool = True,
    auto_reload_threshold: str = "5.00",
    auto_reload_amount: str = "25.00",
) -> dict:
    """Sample GET /api/v1/wallet/ response."""
    return {
        "balance": balance,
        "auto_reload_enabled": auto_reload_enabled,
        "auto_reload_threshold": auto_reload_threshold,
        "auto_reload_amount": auto_reload_amount,
        "updated_at": "2026-03-09T12:00:00Z",
    }
