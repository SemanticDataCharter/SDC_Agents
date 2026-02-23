"""Mapping Toolset — column-to-component mapping operations.

Works with cached schemas and introspection results only.
No direct datasource access, no SDCStudio API access.
"""

from __future__ import annotations

import json
import time
from difflib import SequenceMatcher
from typing import Optional

from google.adk.tools import FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.cache import CacheManager
from sdc_agents.common.config import SDCAgentsConfig

# Type compatibility matrix: source_type -> set of compatible SDC4 component types
TYPE_COMPATIBILITY: dict[str, set[str]] = {
    "string": {"XdString"},
    "integer": {"XdCount", "XdQuantity", "XdIntegerList"},
    "decimal": {"XdQuantity", "XdDecimalList"},
    "boolean": {"XdBoolean", "XdBooleanList"},
    "date": {"XdTemporal"},
    "datetime": {"XdTemporal"},
    "time": {"XdTemporal"},
    "email": {"XdString"},
    "URL": {"XdString"},
    "UUID": {"XdString"},
}


def _name_similarity(a: str, b: str) -> float:
    """Compute name similarity between two identifiers.

    Normalizes underscores/hyphens and uses SequenceMatcher.
    """
    norm_a = a.lower().replace("_", " ").replace("-", " ")
    norm_b = b.lower().replace("_", " ").replace("-", " ")
    return SequenceMatcher(None, norm_a, norm_b).ratio()


class MappingToolset(BaseToolset):
    """Scoped toolset for column-to-SDC4-component mapping.

    Operates on cached data only — no direct datasource or API access.
    """

    def __init__(self, config: SDCAgentsConfig, **kwargs):
        super().__init__(**kwargs)
        self._config = config
        self._cache = CacheManager(config.cache.root)
        self._cache.ensure_dirs()
        self._audit = AuditLogger(config.audit.path, config.audit.log_level)

    async def get_tools(self, readonly_context=None) -> list:
        """Return the mapping tools as FunctionTool instances."""
        tools = [
            FunctionTool(self.mapping_suggest),
            FunctionTool(self.mapping_confirm),
            FunctionTool(self.mapping_list),
        ]
        if readonly_context and self.tool_filter:
            return [t for t in tools if self._is_tool_selected(t, readonly_context)]
        return tools

    async def mapping_suggest(
        self,
        column_name: str,
        column_type: str,
        schema_ct_id: str,
    ) -> list[dict]:
        """Suggest SDC4 component mappings for a datasource column.

        Uses type compatibility and name similarity to rank candidate
        components from a cached schema.

        Args:
            column_name: Name of the datasource column.
            column_type: Inferred type of the column (e.g. 'string', 'integer').
            schema_ct_id: ct_id of the target schema (must be cached).

        Returns:
            List of suggestions sorted by score, each with component ct_id,
            label, type, and similarity score.
        """
        start = time.monotonic()

        cache_path = self._cache.schema_path(schema_ct_id)
        if not self._cache.is_cached(cache_path):
            raise FileNotFoundError(
                f"Schema '{schema_ct_id}' not found in cache. "
                "Use catalog_get_schema first to cache it."
            )

        schema = json.loads(cache_path.read_text())
        compatible_types = TYPE_COMPATIBILITY.get(column_type, {"XdString"})

        suggestions = []
        for component in self._flatten_components(schema.get("components", [])):
            comp_type = component.get("type", "")
            if comp_type not in compatible_types:
                continue
            similarity = _name_similarity(column_name, component.get("label", ""))
            suggestions.append({
                "component_ct_id": component["ct_id"],
                "component_label": component.get("label", ""),
                "component_type": comp_type,
                "score": round(similarity, 3),
            })

        suggestions.sort(key=lambda s: s["score"], reverse=True)

        self._audit.log(
            agent="mapping",
            tool="mapping_suggest",
            inputs={
                "column_name": column_name,
                "column_type": column_type,
                "schema_ct_id": schema_ct_id,
            },
            outputs=suggestions,
            start_time=start,
        )
        return suggestions

    async def mapping_confirm(
        self,
        mapping_name: str,
        mappings: list[dict],
    ) -> dict:
        """Confirm and persist a set of column-to-component mappings.

        Validates that each mapping entry has required fields, then
        writes the mapping configuration to cache.

        Args:
            mapping_name: Name for this mapping configuration.
            mappings: List of dicts, each with 'column_name', 'component_ct_id',
                and 'component_type'.

        Returns:
            Confirmation dict with mapping_name, count, and cache path.
        """
        start = time.monotonic()

        required_keys = {"column_name", "component_ct_id", "component_type"}
        for i, m in enumerate(mappings):
            missing = required_keys - set(m.keys())
            if missing:
                raise ValueError(f"Mapping entry {i} missing keys: {missing}")

        mapping_config = {
            "name": mapping_name,
            "mappings": mappings,
        }
        cache_path = self._cache.mapping_path(mapping_name)
        cache_path.write_text(json.dumps(mapping_config, indent=2))

        result = {
            "mapping_name": mapping_name,
            "count": len(mappings),
            "path": str(cache_path),
        }

        self._audit.log(
            agent="mapping",
            tool="mapping_confirm",
            inputs={"mapping_name": mapping_name, "mappings": mappings},
            outputs=result,
            start_time=start,
        )
        return result

    async def mapping_list(self) -> list[dict]:
        """List all saved mapping configurations from cache.

        Returns:
            List of dicts with mapping name, count, and file path.
        """
        start = time.monotonic()

        mappings_dir = self._cache.root / "mappings"
        results = []
        if mappings_dir.is_dir():
            for path in sorted(mappings_dir.glob("*.json")):
                data = json.loads(path.read_text())
                results.append({
                    "name": data.get("name", path.stem),
                    "count": len(data.get("mappings", [])),
                    "path": str(path),
                })

        self._audit.log(
            agent="mapping",
            tool="mapping_list",
            inputs={},
            outputs=results,
            start_time=start,
        )
        return results

    def _flatten_components(self, components: list[dict]) -> list[dict]:
        """Recursively flatten a components tree into a flat list."""
        flat = []
        for comp in components:
            flat.append(comp)
            children = comp.get("children", [])
            if children:
                flat.extend(self._flatten_components(children))
        return flat
