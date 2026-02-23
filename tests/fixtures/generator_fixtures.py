"""Sample fixtures for Generator Toolset tests."""

from __future__ import annotations


def make_skeleton_xml(ct_id: str = "clxyz123abc") -> str:
    """Return a sample skeleton XML with placeholder tokens."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<sdc4:dm-{ct_id}
    xmlns:sdc4="https://semanticdatacharter.org/ns/sdc4"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="https://semanticdatacharter.org/ns/sdc4 dm-{ct_id}.xsd">
  <sdc4:lab-result-entry>
    <sdc4:test-name>__PLACEHOLDER_clxdstr001__</sdc4:test-name>
    <sdc4:result-value>__PLACEHOLDER_clxdqty001__</sdc4:result-value>
    <sdc4:collection-date>__PLACEHOLDER_clxdtmp001__</sdc4:collection-date>
    <sdc4:is-critical>__PLACEHOLDER_clxdbool001__</sdc4:is-critical>
  </sdc4:lab-result-entry>
</sdc4:dm-{ct_id}>"""


def make_field_mapping(ct_id: str = "clxyz123abc") -> dict:
    """Return a sample field mapping linking placeholders to schema components."""
    return {
        "ct_id": ct_id,
        "fields": [
            {
                "placeholder": "__PLACEHOLDER_clxdstr001__",
                "ct_id": "clxdstr001",
                "element_name": "test-name",
                "type": "XdString",
                "label": "test-name",
                "required": True,
            },
            {
                "placeholder": "__PLACEHOLDER_clxdqty001__",
                "ct_id": "clxdqty001",
                "element_name": "result-value",
                "type": "XdQuantity",
                "label": "result-value",
                "required": True,
            },
            {
                "placeholder": "__PLACEHOLDER_clxdtmp001__",
                "ct_id": "clxdtmp001",
                "element_name": "collection-date",
                "type": "XdTemporal",
                "label": "collection-date",
                "required": True,
            },
            {
                "placeholder": "__PLACEHOLDER_clxdbool001__",
                "ct_id": "clxdbool001",
                "element_name": "is-critical",
                "type": "XdBoolean",
                "label": "is-critical",
                "required": False,
            },
        ],
    }


def make_mapping_config(
    mapping_name: str = "lab_mapping",
    ct_id: str = "clxyz123abc",
    datasource: str = "test_csv",
) -> dict:
    """Return a mapping config linking datasource columns to schema components."""
    return {
        "name": mapping_name,
        "schema_ct_id": ct_id,
        "datasource": datasource,
        "mappings": [
            {
                "column_name": "test_name",
                "component_ct_id": "clxdstr001",
                "component_type": "XdString",
            },
            {
                "column_name": "result",
                "component_ct_id": "clxdqty001",
                "component_type": "XdQuantity",
            },
            {
                "column_name": "collected_date",
                "component_ct_id": "clxdtmp001",
                "component_type": "XdTemporal",
            },
            {
                "column_name": "is_critical",
                "component_ct_id": "clxdbool001",
                "component_type": "XdBoolean",
            },
        ],
    }
