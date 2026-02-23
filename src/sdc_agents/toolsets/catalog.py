"""Catalog Toolset — read-only access to SDCStudio Catalog API.

Provides schema discovery, download, and artifact retrieval tools.
Cache-first for immutable schemas (keyed by ct_id).
"""

from __future__ import annotations

import json
import time
from typing import Optional

import httpx
from google.adk.tools import FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.cache import CacheManager
from sdc_agents.common.config import SDCAgentsConfig


class CatalogToolset(BaseToolset):
    """Scoped toolset for SDCStudio Catalog API interactions.

    All tools are read-only. Schemas are immutable and cached by ct_id.
    """

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

    async def get_tools(self, readonly_context=None) -> list:
        """Return the catalog tools as FunctionTool instances."""
        tools = [
            FunctionTool(self.catalog_list_schemas),
            FunctionTool(self.catalog_get_schema),
            FunctionTool(self.catalog_download_schema_rdf),
            FunctionTool(self.catalog_download_skeleton),
            FunctionTool(self.catalog_download_ontologies),
        ]
        if readonly_context and self.tool_filter:
            return [t for t in tools if self._is_tool_selected(t, readonly_context)]
        return tools

    async def close(self) -> None:
        await self._http.aclose()

    async def catalog_list_schemas(self, query: str = "") -> list[dict]:
        """List available SDC4 schemas from the catalog.

        Args:
            query: Optional search term to filter schemas by title or description.

        Returns:
            List of schema summaries with ct_id, title, description, and project_name.
        """
        start = time.monotonic()
        params = {"search": query} if query else {}
        resp = await self._http.get("/api/catalog/schemas/", params=params)
        resp.raise_for_status()
        result = resp.json()
        self._audit.log(
            agent="catalog",
            tool="catalog_list_schemas",
            inputs={"query": query},
            outputs=result,
            start_time=start,
        )
        return result

    async def catalog_get_schema(self, ct_id: str) -> dict:
        """Get full schema details including components tree and artifact URLs.

        Args:
            ct_id: The CUID2 identifier of the schema.

        Returns:
            Schema detail with ct_id, title, description, components, and artifacts.
        """
        start = time.monotonic()
        cache_path = self._cache.schema_path(ct_id)

        if self._cache.is_cached(cache_path):
            result = json.loads(cache_path.read_text())
        else:
            resp = await self._http.get(f"/api/catalog/schemas/{ct_id}/")
            resp.raise_for_status()
            result = resp.json()
            cache_path.write_text(json.dumps(result, indent=2))

        self._audit.log(
            agent="catalog",
            tool="catalog_get_schema",
            inputs={"ct_id": ct_id},
            outputs=result,
            start_time=start,
        )
        return result

    async def catalog_download_schema_rdf(self, ct_id: str) -> str:
        """Download the RDF representation of a schema.

        Args:
            ct_id: The CUID2 identifier of the schema.

        Returns:
            RDF/XML content as a string.
        """
        start = time.monotonic()
        resp = await self._http.get(f"/api/catalog/schemas/{ct_id}/artifacts/rdf/")
        resp.raise_for_status()
        result = resp.text
        self._audit.log(
            agent="catalog",
            tool="catalog_download_schema_rdf",
            inputs={"ct_id": ct_id},
            outputs=result,
            start_time=start,
        )
        return result

    async def catalog_download_skeleton(self, ct_id: str) -> str:
        """Download an XML skeleton instance for a schema.

        Args:
            ct_id: The CUID2 identifier of the schema.

        Returns:
            XML skeleton content as a string.
        """
        start = time.monotonic()
        resp = await self._http.get(f"/api/catalog/schemas/{ct_id}/artifacts/skeleton/")
        resp.raise_for_status()
        result = resp.text
        self._audit.log(
            agent="catalog",
            tool="catalog_download_skeleton",
            inputs={"ct_id": ct_id},
            outputs=result,
            start_time=start,
        )
        return result

    async def catalog_download_ontologies(self, ct_id: str) -> str:
        """Download ontology definitions associated with a schema.

        Args:
            ct_id: The CUID2 identifier of the schema.

        Returns:
            RDF/XML ontology content as a string.
        """
        start = time.monotonic()
        resp = await self._http.get(f"/api/catalog/schemas/{ct_id}/artifacts/ontologies/")
        resp.raise_for_status()
        result = resp.text
        self._audit.log(
            agent="catalog",
            tool="catalog_download_ontologies",
            inputs={"ct_id": ct_id},
            outputs=result,
            start_time=start,
        )
        return result
