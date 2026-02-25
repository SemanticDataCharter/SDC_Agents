"""Assembly toolset — discover components and assemble data models.

Discovers catalog components matching datasource structure, proposes
Cluster hierarchies, selects contextual components, and calls the
SDCStudio Assembly API to produce published data models.
"""

from __future__ import annotations

import json
import time
from difflib import SequenceMatcher
from typing import Optional

import httpx
from google.adk.tools import FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.cache import CacheManager
from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.mapping import TYPE_COMPATIBILITY


class AssemblyToolset(BaseToolset):
    """Toolset for component discovery and data model assembly."""

    def __init__(
        self,
        config: SDCAgentsConfig,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._config = config
        self._base_url = config.sdcstudio.base_url.rstrip("/")
        self._cache = CacheManager(config.cache.root)
        self._cache.ensure_dirs()
        self._audit = AuditLogger(config.audit.path, config.audit.log_level)
        self._http = http_client or httpx.AsyncClient(base_url=self._base_url)

    async def get_tools(self) -> list[FunctionTool]:
        return [
            FunctionTool(self.discover_components),
            FunctionTool(self.propose_cluster_hierarchy),
            FunctionTool(self.select_contextual_components),
            FunctionTool(self.assemble_model),
        ]

    def _name_similarity(self, name_a: str, name_b: str) -> float:
        """Compute name similarity score between two labels."""
        a = name_a.lower().replace("_", " ").replace("-", " ")
        b = name_b.lower().replace("_", " ").replace("-", " ")
        return SequenceMatcher(None, a, b).ratio()

    async def discover_components(
        self, datasource_name: str, schema_ct_id: Optional[str] = None
    ) -> dict:
        """Discover catalog components matching a datasource's structure.

        Args:
            datasource_name: Name of a previously introspected datasource.
            schema_ct_id: Optional schema ct_id to match against. If None,
                matches against all cached schema components.

        Returns:
            Dict with datasource, matches list, and unmatched columns.
        """
        start_time = time.monotonic()

        # Load introspection result from cache
        intro_path = self._cache.introspection_path(datasource_name)
        if not intro_path.exists():
            raise FileNotFoundError(
                f"No cached introspection for datasource '{datasource_name}'. "
                "Run introspection first."
            )

        introspection = json.loads(intro_path.read_text())

        # Load schema component tree if specified
        components = []
        if schema_ct_id:
            schema_path = self._cache.schema_path(schema_ct_id)
            if schema_path.exists():
                schema_data = json.loads(schema_path.read_text())
                components = self._extract_components(schema_data)

        # Match columns to components
        columns = introspection.get("columns", [])
        matches = []
        matched_columns = set()

        for col in columns:
            col_name = col.get("name", "")
            col_type = col.get("data_type", "string")
            compatible_types = TYPE_COMPATIBILITY.get(col_type, {"XdString"})

            best_match = None
            best_score = 0.0

            for comp in components:
                comp_type = comp.get("type", "")
                if comp_type not in compatible_types:
                    continue

                comp_label = comp.get("label", "")
                score = self._name_similarity(col_name, comp_label)

                if score > best_score:
                    best_score = score
                    best_match = comp

            if best_match and best_score > 0.3:
                matches.append(
                    {
                        "column": col_name,
                        "ct_id": best_match.get("ct_id", ""),
                        "label": best_match.get("label", ""),
                        "type": best_match.get("type", ""),
                        "score": round(best_score, 4),
                    }
                )
                matched_columns.add(col_name)

        unmatched = [
            col.get("name", "") for col in columns if col.get("name", "") not in matched_columns
        ]

        result = {
            "datasource": datasource_name,
            "matches": matches,
            "unmatched": unmatched,
        }

        self._audit.log(
            agent="assembly",
            tool="discover_components",
            inputs={"datasource_name": datasource_name, "schema_ct_id": schema_ct_id},
            outputs={"match_count": len(matches), "unmatched_count": len(unmatched)},
            start_time=start_time,
        )
        return result

    def _extract_components(self, schema_data: dict) -> list[dict]:
        """Recursively extract leaf components from a schema tree."""
        components = []
        for comp in schema_data.get("components", []):
            if comp.get("type") == "Cluster":
                # Recurse into Cluster children
                components.extend(self._extract_components(comp))
            else:
                components.append(comp)
            # Also check children key
            for child in comp.get("children", []):
                if child.get("type") == "Cluster":
                    components.extend(self._extract_components(child))
                elif child not in components:
                    components.append(child)
        return components

    async def propose_cluster_hierarchy(
        self, datasource_name: str, component_matches: list[dict]
    ) -> dict:
        """Propose a Cluster hierarchy from datasource structure and matches.

        Args:
            datasource_name: Name of the datasource.
            component_matches: List of component match dicts from discover_components.

        Returns:
            Dict with hierarchy tree and cluster_count.
        """
        start_time = time.monotonic()

        # Determine structure — flat columns vs nested
        nested_groups = {}
        flat_components = []

        for match in component_matches:
            col_name = match.get("column", "")
            # Check if column name suggests grouping (e.g., "address.street")
            if "." in col_name:
                group, _ = col_name.rsplit(".", 1)
                nested_groups.setdefault(group, []).append(match)
            else:
                flat_components.append(match)

        # Build hierarchy
        clusters = []
        for group_name, group_matches in nested_groups.items():
            clusters.append(
                {
                    "label": group_name.replace(".", "-"),
                    "components": [{"ct_id": m["ct_id"]} for m in group_matches],
                    "clusters": [],
                }
            )

        hierarchy = {
            "label": datasource_name.replace("_", "-"),
            "components": [{"ct_id": m["ct_id"]} for m in flat_components],
            "clusters": clusters,
        }

        cluster_count = 1 + len(clusters)  # Root + nested

        result = {
            "hierarchy": hierarchy,
            "cluster_count": cluster_count,
        }

        self._audit.log(
            agent="assembly",
            tool="propose_cluster_hierarchy",
            inputs={"datasource_name": datasource_name, "match_count": len(component_matches)},
            outputs={"cluster_count": cluster_count},
            start_time=start_time,
        )
        return result

    async def select_contextual_components(
        self, context_description: Optional[str] = None
    ) -> dict:
        """Select contextual components (audit, attestation, party) from default project.

        Args:
            context_description: Optional description to guide component selection.

        Returns:
            Dict with contextual component selections and project name.
        """
        start_time = time.monotonic()

        project = self._config.sdcstudio.default_library_project
        if not project:
            raise ValueError(
                "No default_library_project configured in sdcstudio settings. "
                "Set sdcstudio.default_library_project in your config."
            )

        # Fetch catalog components filtered to default project
        url = f"{self._base_url}/api/catalog/schemas/"
        params = {"project_name": project}

        resp = await self._http.get(url, params=params)
        resp.raise_for_status()
        schemas = resp.json()

        # Match contextual slots by label patterns
        contextual = {"audit": None, "attestation": None, "party": None}
        slot_patterns = {
            "audit": ["audit", "audit-trail", "audit-log"],
            "attestation": ["attestation", "attest", "signature"],
            "party": ["party", "participant", "actor"],
        }

        for schema in schemas:
            for comp in schema.get("components", []):
                label = comp.get("label", "").lower()
                for slot, patterns in slot_patterns.items():
                    if contextual[slot] is None and any(p in label for p in patterns):
                        contextual[slot] = {
                            "ct_id": comp.get("ct_id", ""),
                            "label": comp.get("label", ""),
                        }

        result = {
            "contextual": contextual,
            "project": project,
        }

        self._audit.log(
            agent="assembly",
            tool="select_contextual_components",
            inputs={"context_description": context_description, "project": project},
            outputs=result,
            start_time=start_time,
        )
        return result

    async def assemble_model(self, title: str, description: str, assembly_tree: dict) -> dict:
        """Assemble a data model by calling the SDCStudio Assembly API.

        Args:
            title: Title for the new data model.
            description: Description of the data model.
            assembly_tree: Complete assembly tree with hierarchy and components.

        Returns:
            Dict with dm_ct_id, title, status, and artifact_urls.

        Raises:
            ValueError: If assembly_tree is missing required structure.
            httpx.HTTPStatusError: If the Assembly API returns an error.
        """
        start_time = time.monotonic()

        # Validate assembly tree structure
        if not isinstance(assembly_tree, dict):
            raise ValueError("assembly_tree must be a dict")
        if "label" not in assembly_tree:
            raise ValueError("assembly_tree must have a 'label' key")
        if "components" not in assembly_tree and "clusters" not in assembly_tree:
            raise ValueError("assembly_tree must have 'components' and/or 'clusters'")

        url = f"{self._base_url}/api/v1/dmgen/assemble/"
        payload = {
            "title": title,
            "description": description,
            "assembly_tree": assembly_tree,
        }
        headers = {}
        if self._config.sdcstudio.api_key:
            headers["Authorization"] = f"Bearer {self._config.sdcstudio.api_key}"

        resp = await self._http.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        result = {
            "dm_ct_id": data.get("dm_ct_id", ""),
            "title": data.get("title", title),
            "status": data.get("status", "published"),
            "artifact_urls": data.get("artifact_urls", {}),
        }

        self._audit.log(
            agent="assembly",
            tool="assemble_model",
            inputs={"title": title},
            outputs=result,
            start_time=start_time,
        )
        return result
