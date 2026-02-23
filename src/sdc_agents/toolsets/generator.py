"""Generator Toolset — XML instance generation from mapped datasource records.

Produces SDC4 XML instances by substituting datasource values into
skeleton XML templates using field mappings. No network access.
"""

from __future__ import annotations

import csv
import io
import json
import time
from pathlib import Path
from typing import Optional

from google.adk.tools import FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.cache import CacheManager
from sdc_agents.common.config import SDCAgentsConfig


class GeneratorToolset(BaseToolset):
    """Scoped toolset for SDC4 XML instance generation.

    Reads skeleton XML and field mappings from cache, substitutes
    datasource values, and writes XML output files.
    """

    def __init__(self, config: SDCAgentsConfig, **kwargs):
        super().__init__(**kwargs)
        self._config = config
        self._cache = CacheManager(config.cache.root)
        self._cache.ensure_dirs()
        self._audit = AuditLogger(config.audit.path, config.audit.log_level)
        self._output_dir = Path(config.output.directory)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def get_tools(self, readonly_context=None) -> list:
        """Return the generator tools as FunctionTool instances."""
        tools = [
            FunctionTool(self.generate_instance),
            FunctionTool(self.generate_batch),
            FunctionTool(self.generate_preview),
        ]
        if readonly_context and self.tool_filter:
            return [t for t in tools if self._is_tool_selected(t, readonly_context)]
        return tools

    def _load_mapping_config(self, mapping_name: str) -> dict:
        """Load a mapping config from cache."""
        path = self._cache.mapping_path(mapping_name)
        if not self._cache.is_cached(path):
            raise FileNotFoundError(
                f"Mapping '{mapping_name}' not found in cache. "
                "Use mapping_confirm to save it first."
            )
        return json.loads(path.read_text())

    def _load_skeleton(self, ct_id: str) -> str:
        """Load skeleton XML from cache."""
        path = self._cache.skeleton_path(ct_id)
        if not self._cache.is_cached(path):
            raise FileNotFoundError(
                f"Skeleton for schema '{ct_id}' not found in cache. "
                "Use catalog_download_skeleton to cache it first."
            )
        return path.read_text()

    def _load_field_mapping(self, ct_id: str) -> dict:
        """Load field mapping from cache."""
        path = self._cache.field_mapping_path(ct_id)
        if not self._cache.is_cached(path):
            raise FileNotFoundError(f"Field mapping for schema '{ct_id}' not found in cache.")
        return json.loads(path.read_text())

    def _fetch_record(self, datasource_name: str, row_index: int) -> dict:
        """Fetch a single record from a datasource by row index.

        Currently supports CSV datasources. SQL support requires async context.
        """
        if datasource_name not in self._config.datasources:
            raise KeyError(
                f"Unknown datasource '{datasource_name}'. "
                f"Available: {list(self._config.datasources.keys())}"
            )
        ds = self._config.datasources[datasource_name]

        if ds.type == "csv":
            csv_path = Path(ds.path)
            if not csv_path.is_file():
                raise FileNotFoundError(f"CSV file not found: {ds.path}")
            content = csv_path.read_text()
            reader = csv.DictReader(io.StringIO(content))
            for i, row in enumerate(reader):
                if i == row_index:
                    return row
            raise IndexError(
                f"Row index {row_index} out of range for datasource '{datasource_name}'"
            )

        if ds.type == "json":
            json_path = Path(ds.path)
            if not json_path.is_file():
                raise FileNotFoundError(f"JSON file not found: {ds.path}")
            raw = json.loads(json_path.read_text())

            # Apply JSONPath if configured
            if ds.jsonpath:
                from jsonpath_ng import parse as jp_parse

                expression = jp_parse(ds.jsonpath)
                matches = expression.find(raw)
                records = [m.value for m in matches]
            else:
                records = raw if isinstance(raw, list) else [raw]

            if row_index >= len(records):
                raise IndexError(
                    f"Row index {row_index} out of range for datasource '{datasource_name}'"
                )
            record = records[row_index]
            # Convert all values to strings for XML substitution
            return {k: str(v) for k, v in record.items()}

        raise ValueError(
            f"Datasource type '{ds.type}' not supported for record fetching. "
            "Use CSV or JSON datasources, or provide a record dict directly."
        )

    def _substitute(
        self,
        skeleton_xml: str,
        field_mapping: dict,
        mapping_config: dict,
        record: dict,
    ) -> tuple[str, list[dict]]:
        """Substitute values into skeleton XML.

        Returns:
            Tuple of (xml_string, errors_list).
        """
        errors = []
        xml_str = skeleton_xml

        # Build column->component lookup from mapping config
        col_to_component: dict[str, str] = {}
        for m in mapping_config.get("mappings", []):
            col_to_component[m["column_name"]] = m["component_ct_id"]

        # Build component_ct_id->placeholder lookup from field mapping
        comp_to_field: dict[str, dict] = {}
        for field in field_mapping.get("fields", []):
            comp_to_field[field["ct_id"]] = field

        # Substitute each mapped column
        for col_name, comp_ct_id in col_to_component.items():
            field = comp_to_field.get(comp_ct_id)
            if not field:
                continue

            placeholder = field["placeholder"]
            value = record.get(col_name)

            if value is not None and str(value).strip():
                xml_str = xml_str.replace(placeholder, str(value))
            elif field.get("required", False):
                errors.append(
                    {
                        "field": field["element_name"],
                        "ct_id": comp_ct_id,
                        "error": "Required field has no mapped value",
                    }
                )

        # Handle unfilled optional placeholders — remove elements
        for field in field_mapping.get("fields", []):
            placeholder = field["placeholder"]
            if placeholder in xml_str:
                if field.get("required", False):
                    errors.append(
                        {
                            "field": field["element_name"],
                            "ct_id": field["ct_id"],
                            "error": "Required field not mapped",
                        }
                    )
                else:
                    # Remove the element containing the unfilled placeholder
                    xml_str = self._remove_placeholder_element(xml_str, placeholder)

        return xml_str, errors

    def _remove_placeholder_element(self, xml_str: str, placeholder: str) -> str:
        """Remove an XML element that still contains an unfilled placeholder."""
        # Find the line containing the placeholder and remove it
        lines = xml_str.split("\n")
        filtered = [line for line in lines if placeholder not in line]
        return "\n".join(filtered)

    async def generate_instance(
        self,
        mapping_name: str,
        row_index: Optional[int] = None,
        record: Optional[dict] = None,
    ) -> dict:
        """Generate an SDC4 XML instance from a mapped datasource record.

        Args:
            mapping_name: Name of the mapping configuration (from cache).
            row_index: Row index to fetch from the datasource. Ignored if
                record is provided.
            record: Explicit record dict to use instead of fetching from datasource.

        Returns:
            Dict with xml_path, ct_id, root_element, and row_index.
        """
        start = time.monotonic()

        mapping_config = self._load_mapping_config(mapping_name)
        ct_id = mapping_config["schema_ct_id"]
        skeleton_xml = self._load_skeleton(ct_id)
        field_mapping = self._load_field_mapping(ct_id)

        # Get record data
        if record is None:
            if row_index is None:
                row_index = 0
            ds_name = mapping_config.get("datasource")
            if not ds_name:
                raise ValueError("Mapping config has no 'datasource' field")
            record = self._fetch_record(ds_name, row_index)

        xml_str, errors = self._substitute(skeleton_xml, field_mapping, mapping_config, record)

        if errors:
            # Still write the file but report errors
            pass

        # Write output
        idx = row_index if row_index is not None else 0
        filename = f"{ct_id}_{idx}.xml"
        output_path = self._output_dir / filename
        output_path.write_text(xml_str)

        # Determine root element name from skeleton
        root_element = f"sdc4:dm-{ct_id}"

        result = {
            "xml_path": str(output_path),
            "ct_id": ct_id,
            "root_element": root_element,
            "row_index": idx,
        }
        if errors:
            result["errors"] = errors

        self._audit.log(
            agent="generator",
            tool="generate_instance",
            inputs={"mapping_name": mapping_name, "row_index": idx},
            outputs=result,
            start_time=start,
        )
        return result

    async def generate_batch(
        self,
        mapping_name: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """Generate multiple XML instances from mapped datasource records.

        Args:
            mapping_name: Name of the mapping configuration.
            limit: Maximum number of records to process (default 100).
            offset: Starting row index (default 0).

        Returns:
            Dict with count, output_dir, files list, and errors list.
        """
        start = time.monotonic()

        files = []
        errors = []
        for i in range(offset, offset + limit):
            try:
                result = await self.generate_instance(mapping_name=mapping_name, row_index=i)
                files.append(result["xml_path"])
                if "errors" in result:
                    errors.append({"row": i, "error": result["errors"]})
            except IndexError:
                # Reached end of datasource
                break
            except Exception as exc:
                errors.append({"row": i, "error": str(exc)})

        result = {
            "count": len(files),
            "output_dir": str(self._output_dir),
            "files": files,
            "errors": errors,
        }

        self._audit.log(
            agent="generator",
            tool="generate_batch",
            inputs={"mapping_name": mapping_name, "limit": limit, "offset": offset},
            outputs=result,
            start_time=start,
        )
        return result

    async def generate_preview(
        self,
        mapping_name: str,
        row_index: int = 0,
    ) -> dict:
        """Preview an XML instance without writing to disk.

        Args:
            mapping_name: Name of the mapping configuration.
            row_index: Row index to preview (default 0).

        Returns:
            Dict with xml string, ct_id, and root_element.
        """
        start = time.monotonic()

        mapping_config = self._load_mapping_config(mapping_name)
        ct_id = mapping_config["schema_ct_id"]
        skeleton_xml = self._load_skeleton(ct_id)
        field_mapping = self._load_field_mapping(ct_id)

        ds_name = mapping_config.get("datasource")
        if not ds_name:
            raise ValueError("Mapping config has no 'datasource' field")
        record = self._fetch_record(ds_name, row_index)

        xml_str, errors = self._substitute(skeleton_xml, field_mapping, mapping_config, record)

        result = {
            "xml": xml_str,
            "ct_id": ct_id,
            "root_element": f"sdc4:dm-{ct_id}",
        }
        if errors:
            result["errors"] = errors

        self._audit.log(
            agent="generator",
            tool="generate_preview",
            inputs={"mapping_name": mapping_name, "row_index": row_index},
            outputs=result,
            start_time=start,
        )
        return result
