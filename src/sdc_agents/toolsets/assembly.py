"""Assembly toolset — discover components and assemble data models.

Discovers catalog components matching datasource structure, proposes
Cluster hierarchies, selects contextual components, and calls the
SDCStudio Assembly API to produce published data models.

Supports two assembly modes:
- **Pure reuse**: all components referenced by ct_id → synchronous (HTTP 200)
- **Mixed**: some components need minting (label + data_type) → async (HTTP 202)

Wallet-aware: raises ``InsufficientFundsError`` on HTTP 402.
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
from sdc_agents.common.exceptions import InsufficientFundsError
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

        # Set up HTTP client with Token auth (consistent with VaaS)
        if http_client:
            self._http = http_client
        else:
            headers = {}
            if config.sdcstudio.api_key:
                headers["Authorization"] = f"Token {config.sdcstudio.api_key}"
            self._http = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
            )

    async def get_tools(self) -> list[FunctionTool]:
        return [
            FunctionTool(self.discover_components),
            FunctionTool(self.propose_cluster_hierarchy),
            FunctionTool(self.select_contextual_components),
            FunctionTool(self.assemble_model),
        ]

    @staticmethod
    def _check_402(resp: httpx.Response) -> None:
        """Raise InsufficientFundsError if the response is HTTP 402."""
        if resp.status_code == 402:
            ct = resp.headers.get("content-type", "")
            data = resp.json() if ct.startswith("application/json") else {}
            est = resp.headers.get(
                "X-SDC-Estimated-Cost",
                data.get("estimated_cost", ""),
            )
            bal = resp.headers.get(
                "X-SDC-Balance-Remaining",
                data.get("balance_remaining", ""),
            )
            raise InsufficientFundsError(
                message=data.get("detail", data.get("error", "Insufficient wallet balance.")),
                estimated_cost=est,
                balance_remaining=bal,
            )

    @staticmethod
    def _extract_wallet_headers(resp: httpx.Response) -> dict:
        """Extract wallet-related headers from a successful response."""
        info = {}
        est = resp.headers.get("X-SDC-Estimated-Cost")
        bal = resp.headers.get("X-SDC-Balance-Remaining")
        if est:
            info["estimated_cost"] = est
        if bal:
            info["balance_remaining"] = bal
        return info

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

    @staticmethod
    def _match_to_component_ref(match: dict) -> dict:
        """Convert a component match dict to a component reference.

        Matched components (with ct_id) become reuse refs (free).
        Unmatched columns (with data_type but no ct_id) become mint refs (billable).
        """
        if match.get("ct_id"):
            return {"ct_id": match["ct_id"]}
        # Mint ref — label + data_type required
        ref: dict = {
            "label": match.get("column", match.get("label", "")),
            "data_type": match.get("data_type", match.get("type", "XdString")),
        }
        if match.get("description"):
            ref["description"] = match["description"]
        if match.get("units"):
            ref["units"] = match["units"]
        return ref

    async def propose_cluster_hierarchy(
        self,
        datasource_name: str,
        component_matches: list[dict],
        unmatched_columns: Optional[list[dict]] = None,
    ) -> dict:
        """Propose a Cluster hierarchy from datasource structure and matches.

        Args:
            datasource_name: Name of the datasource.
            component_matches: List of component match dicts from discover_components.
            unmatched_columns: Optional list of unmatched column dicts with
                ``name`` and ``data_type`` keys. These become mint-mode
                component refs (billable). If None, unmatched columns are omitted.

        Returns:
            Dict with hierarchy tree, cluster_count, new_component_count, and
            reuse_component_count.
        """
        start_time = time.monotonic()

        # Merge matches and unmatched into a single list with component refs
        all_items = list(component_matches)
        if unmatched_columns:
            for col in unmatched_columns:
                all_items.append(
                    {
                        "column": col.get("name", col.get("column", "")),
                        "data_type": col.get("data_type", "XdString"),
                        "description": col.get("description", ""),
                        "units": col.get("units", ""),
                        # No ct_id → mint mode
                    }
                )

        # Determine structure — flat columns vs nested
        nested_groups: dict[str, list[dict]] = {}
        flat_components: list[dict] = []

        for item in all_items:
            col_name = item.get("column", "")
            # Check if column name suggests grouping (e.g., "address.street")
            if "." in col_name:
                group, _ = col_name.rsplit(".", 1)
                nested_groups.setdefault(group, []).append(item)
            else:
                flat_components.append(item)

        # Build hierarchy
        clusters = []
        for group_name, group_items in nested_groups.items():
            clusters.append(
                {
                    "label": group_name.replace(".", "-"),
                    "components": [self._match_to_component_ref(m) for m in group_items],
                    "clusters": [],
                }
            )

        hierarchy = {
            "label": datasource_name.replace("_", "-"),
            "components": [self._match_to_component_ref(m) for m in flat_components],
            "clusters": clusters,
        }

        cluster_count = 1 + len(clusters)  # Root + nested
        new_count = sum(1 for item in all_items if not item.get("ct_id"))
        reuse_count = len(all_items) - new_count

        result = {
            "hierarchy": hierarchy,
            "cluster_count": cluster_count,
            "new_component_count": new_count,
            "reuse_component_count": reuse_count,
        }

        self._audit.log(
            agent="assembly",
            tool="propose_cluster_hierarchy",
            inputs={
                "datasource_name": datasource_name,
                "match_count": len(component_matches),
                "unmatched_count": len(unmatched_columns or []),
            },
            outputs={
                "cluster_count": cluster_count,
                "new_count": new_count,
                "reuse_count": reuse_count,
            },
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

    async def assemble_model(
        self,
        title: str,
        description: str,
        assembly_tree: dict,
        contextual: Optional[dict] = None,
    ) -> dict:
        """Assemble a data model by calling the SDCStudio Assembly API.

        Supports two response modes:
        - **Pure reuse** (HTTP 200): all components have ct_id. Returns
          dm_ct_id, title, status, artifact_urls immediately.
        - **Mixed** (HTTP 202): some components need minting. Returns
          task_id and data_source_ct_id for async polling.

        Args:
            title: Title for the new data model.
            description: Description of the data model.
            assembly_tree: Complete assembly tree with hierarchy and components.
                Components may be reuse refs (``{"ct_id": "..."}``}) or mint
                refs (``{"label": "...", "data_type": "..."}``).
            contextual: Optional contextual component references (audit,
                attestation, party, etc.). Each value is a component ref dict.

        Returns:
            Dict with assembly result. Shape depends on response mode:
            - Sync (200): ``{dm_ct_id, title, status, artifact_urls, mode: "sync"}``
            - Async (202): ``{task_id, data_source_ct_id, estimated_cost,
              new_components, status: "processing", mode: "async"}``

        Raises:
            ValueError: If assembly_tree is missing required structure.
            InsufficientFundsError: If wallet balance is insufficient (HTTP 402).
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
        payload: dict = {
            "title": title,
            "description": description,
            "data": assembly_tree,
        }
        if contextual:
            payload["contextual"] = contextual

        resp = await self._http.post(url, json=payload)
        self._check_402(resp)
        resp.raise_for_status()
        data = resp.json()

        if resp.status_code == 202:
            # Async path — components are being minted via agentic pipeline
            result = {
                "mode": "async",
                "status": data.get("status", "processing"),
                "task_id": data.get("task_id", ""),
                "data_source_ct_id": data.get("data_source_ct_id", ""),
                "estimated_cost": data.get("estimated_cost", ""),
                "new_components": data.get("new_components", 0),
                **self._extract_wallet_headers(resp),
            }
        else:
            # Sync path — pure reuse, DM already published
            result = {
                "mode": "sync",
                "dm_ct_id": data.get("dm_ct_id", data.get("ct_id", "")),
                "title": data.get("title", title),
                "status": data.get("status", "published"),
                "artifact_urls": data.get("artifact_urls", {}),
                **self._extract_wallet_headers(resp),
            }

        self._audit.log(
            agent="assembly",
            tool="assemble_model",
            inputs={"title": title, "mode": result.get("mode")},
            outputs=result,
            start_time=start_time,
        )
        return result
