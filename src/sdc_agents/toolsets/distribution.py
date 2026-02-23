"""Distribution Toolset — route artifact packages to customer destinations.

Delivers validated artifact packages (.pkg.zip) to triplestores (Fuseki/GraphDB),
graph databases (Neo4j HTTP API), REST APIs, and filesystem destinations.
All connectors use httpx — no driver-specific dependencies.
"""

from __future__ import annotations

import json
import time
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx
from google.adk.tools import FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.cache import CacheManager
from sdc_agents.common.config import SDCAgentsConfig


class DistributionToolset(BaseToolset):
    """Scoped toolset for distributing SDC4 artifact packages.

    Routes artifacts from .pkg.zip packages to configured destinations
    (triplestores, graph databases, REST APIs, filesystem).
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
        self._cache = CacheManager(config.cache.root)
        self._cache.ensure_dirs()
        self._audit = AuditLogger(config.audit.path, config.audit.log_level)
        self._output_dir = Path(config.output.directory).resolve()
        self._output_dir.mkdir(parents=True, exist_ok=True)

        if http_client:
            self._http = http_client
        else:
            self._http = httpx.AsyncClient()

    async def get_tools(self, readonly_context=None) -> list:
        """Return the distribution tools as FunctionTool instances."""
        tools = [
            FunctionTool(self.inspect_package),
            FunctionTool(self.list_destinations),
            FunctionTool(self.distribute_package),
            FunctionTool(self.distribute_batch),
            FunctionTool(self.bootstrap_triplestore),
        ]
        if readonly_context and self.tool_filter:
            return [t for t in tools if self._is_tool_selected(t, readonly_context)]
        return tools

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()

    def _check_path(self, path_str: str) -> Path:
        """Verify a path is within the configured output directory.

        Raises PermissionError if the path escapes the output directory.
        """
        resolved = Path(path_str).resolve()
        try:
            resolved.relative_to(self._output_dir)
        except ValueError:
            raise PermissionError(
                f"Access denied: '{path_str}' is outside the output directory "
                f"'{self._output_dir}'. Only files within the output directory "
                "can be distributed."
            )
        return resolved

    def _read_package(self, package_path: Path) -> tuple[dict, zipfile.ZipFile]:
        """Read a .pkg.zip and parse its manifest.

        Returns (manifest_dict, ZipFile object).
        """
        pkg_bytes = package_path.read_bytes()
        zf = zipfile.ZipFile(BytesIO(pkg_bytes))
        manifest = json.loads(zf.read("manifest.json"))
        return manifest, zf

    # --- Connector helpers (private) ---

    async def _deliver_to_sparql(
        self,
        endpoint: str,
        auth: Optional[str],
        content: bytes,
        content_type: str,
        graph_uri: str,
    ) -> dict:
        """PUT content to a SPARQL Graph Store Protocol endpoint."""
        headers = {"Content-Type": content_type}
        if auth:
            headers["Authorization"] = auth
        resp = await self._http.put(
            endpoint,
            params={"graph": graph_uri},
            content=content,
            headers=headers,
        )
        resp.raise_for_status()
        return {"status": "delivered", "graph_uri": graph_uri, "http_status": resp.status_code}

    async def _deliver_to_neo4j(
        self,
        endpoint: str,
        auth: Optional[str],
        database: str,
        statements: str,
    ) -> dict:
        """POST statements to Neo4j HTTP transactional endpoint."""
        url = f"{endpoint}/db/{database}/tx/commit"
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = auth
        body = {"statements": [{"statement": statements}]}
        resp = await self._http.post(url, json=body, headers=headers)
        resp.raise_for_status()
        return {"status": "delivered", "http_status": resp.status_code}

    async def _deliver_to_rest(
        self,
        endpoint: str,
        method: str,
        headers: Optional[dict],
        content: bytes,
        content_type: str,
    ) -> dict:
        """POST/PUT content to a REST API endpoint."""
        req_headers = {"Content-Type": content_type}
        if headers:
            req_headers.update(headers)
        if method.upper() == "PUT":
            resp = await self._http.put(endpoint, content=content, headers=req_headers)
        else:
            resp = await self._http.post(endpoint, content=content, headers=req_headers)
        resp.raise_for_status()
        return {"status": "delivered", "http_status": resp.status_code}

    def _deliver_to_filesystem(
        self,
        path_pattern: str,
        ct_id: str,
        instance_id: str,
        filename: str,
        content: bytes,
        create_directories: bool,
    ) -> dict:
        """Write artifact content to a filesystem path."""
        dest_str = path_pattern.replace("{ct_id}", ct_id).replace("{instance_id}", instance_id)
        dest_dir = Path(dest_str)
        if create_directories:
            dest_dir.mkdir(parents=True, exist_ok=True)
        output_file = dest_dir / filename
        output_file.write_bytes(content)
        return {"status": "delivered", "path": str(output_file)}

    async def _check_named_graph_exists(
        self,
        endpoint: str,
        auth: Optional[str],
        graph_uri: str,
    ) -> bool:
        """Check if a named graph exists via SPARQL ASK query."""
        query = f"ASK WHERE {{ GRAPH <{graph_uri}> {{ ?s ?p ?o }} }}"
        headers = {
            "Content-Type": "application/sparql-query",
            "Accept": "application/sparql-results+json",
        }
        if auth:
            headers["Authorization"] = auth
        # SPARQL query endpoint is typically the dataset URL
        resp = await self._http.post(endpoint, content=query.encode(), headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data.get("boolean", False)

    # --- Content type mapping ---

    _ARTIFACT_CONTENT_TYPES = {
        "xml": "application/xml",
        "json": "application/json",
        "rdf": "text/turtle",
        "ttl": "text/turtle",
        "gql": "text/plain",
        "jsonld": "application/ld+json",
        "shacl": "text/turtle",
    }

    def _content_type_for(self, artifact_type: str) -> str:
        """Return the content type for an artifact type."""
        return self._ARTIFACT_CONTENT_TYPES.get(artifact_type, "application/octet-stream")

    # --- Tools ---

    async def inspect_package(self, package_path: str) -> dict:
        """Inspect a .pkg.zip artifact package without distributing it.

        Args:
            package_path: Path to the .pkg.zip file (must be within output directory).

        Returns:
            Dict with ct_id, instance_id, artifacts list (type, filename, size_bytes),
            and the full manifest.
        """
        start = time.monotonic()

        resolved = self._check_path(package_path)
        manifest, zf = self._read_package(resolved)

        artifacts = []
        for entry in manifest.get("artifacts", []):
            filename = entry["filename"]
            try:
                info = zf.getinfo(filename)
                size_bytes = info.file_size
            except KeyError:
                size_bytes = 0
            artifacts.append(
                {
                    "type": entry["type"],
                    "filename": filename,
                    "destination": entry.get("destination"),
                    "size_bytes": size_bytes,
                }
            )
        zf.close()

        result = {
            "ct_id": manifest.get("ct_id"),
            "instance_id": manifest.get("instance_id"),
            "artifacts": artifacts,
            "manifest": manifest,
        }

        self._audit.log(
            agent="distribution",
            tool="inspect_package",
            inputs={"package_path": package_path},
            outputs=result,
            start_time=start,
        )
        return result

    async def list_destinations(self) -> list[dict]:
        """List configured destinations with connectivity status.

        Returns:
            List of dicts with name, type, endpoint, and status
            ('reachable' or 'unreachable').
        """
        start = time.monotonic()

        results = []
        for name, dest in self._config.destinations.items():
            entry = {
                "name": name,
                "type": dest.type,
                "endpoint": dest.endpoint or dest.path,
                "status": "unreachable",
            }
            try:
                if dest.type == "filesystem":
                    parent = Path(dest.path).parent if dest.path else Path(".")
                    if parent.exists():
                        entry["status"] = "reachable"
                elif dest.type in ("fuseki", "graphdb"):
                    headers = {}
                    if dest.auth:
                        headers["Authorization"] = dest.auth
                    resp = await self._http.get(dest.endpoint, headers=headers, timeout=5.0)
                    if resp.status_code < 500:
                        entry["status"] = "reachable"
                elif dest.type == "neo4j":
                    headers = {}
                    if dest.auth:
                        headers["Authorization"] = dest.auth
                    resp = await self._http.get(dest.endpoint, headers=headers, timeout=5.0)
                    if resp.status_code < 500:
                        entry["status"] = "reachable"
                elif dest.type == "rest_api":
                    headers = {}
                    if dest.headers:
                        headers.update(dest.headers)
                    resp = await self._http.head(dest.endpoint, headers=headers, timeout=5.0)
                    if resp.status_code < 500:
                        entry["status"] = "reachable"
            except Exception:
                pass  # status stays "unreachable"

            results.append(entry)

        self._audit.log(
            agent="distribution",
            tool="list_destinations",
            inputs={},
            outputs=results,
            start_time=start,
        )
        return results

    async def distribute_package(self, package_path: str) -> dict:
        """Distribute all artifacts from a .pkg.zip to their configured destinations.

        Args:
            package_path: Path to the .pkg.zip file (must be within output directory).

        Returns:
            Dict with package_path, ct_id, artifacts_distributed count, and
            per-artifact results.
        """
        start = time.monotonic()

        resolved = self._check_path(package_path)
        manifest, zf = self._read_package(resolved)
        ct_id = manifest.get("ct_id", "unknown")
        instance_id = manifest.get("instance_id", "unknown")

        per_artifact_results = []
        distributed = 0

        for entry in manifest.get("artifacts", []):
            dest_name = entry.get("destination")
            filename = entry["filename"]
            artifact_type = entry["type"]

            if dest_name not in self._config.destinations:
                per_artifact_results.append(
                    {
                        "artifact": filename,
                        "destination": dest_name,
                        "status": "skipped",
                        "reason": f"Destination '{dest_name}' not configured",
                    }
                )
                continue

            dest = self._config.destinations[dest_name]
            try:
                content = zf.read(filename)
                content_type = self._content_type_for(artifact_type)

                if dest.type in ("fuseki", "graphdb"):
                    graph_uri = f"urn:sdc4:{ct_id}:{instance_id}:{artifact_type}"
                    await self._deliver_to_sparql(
                        dest.endpoint,
                        dest.auth,
                        content,
                        content_type,
                        graph_uri,
                    )
                elif dest.type == "neo4j":
                    await self._deliver_to_neo4j(
                        dest.endpoint,
                        dest.auth,
                        dest.database or "neo4j",
                        content.decode("utf-8"),
                    )
                elif dest.type == "rest_api":
                    await self._deliver_to_rest(
                        dest.endpoint,
                        dest.method or "POST",
                        dest.headers,
                        content,
                        content_type,
                    )
                elif dest.type == "filesystem":
                    self._deliver_to_filesystem(
                        dest.path or "./archive/{ct_id}/{instance_id}/",
                        ct_id,
                        instance_id,
                        filename,
                        content,
                        dest.create_directories,
                    )

                per_artifact_results.append(
                    {
                        "artifact": filename,
                        "destination": dest_name,
                        "status": "delivered",
                    }
                )
                distributed += 1
            except Exception as exc:
                per_artifact_results.append(
                    {
                        "artifact": filename,
                        "destination": dest_name,
                        "status": "failed",
                        "error": str(exc),
                    }
                )

        zf.close()

        result = {
            "package_path": package_path,
            "ct_id": ct_id,
            "artifacts_distributed": distributed,
            "results": per_artifact_results,
        }

        self._audit.log(
            agent="distribution",
            tool="distribute_package",
            inputs={"package_path": package_path},
            outputs=result,
            start_time=start,
        )
        return result

    async def distribute_batch(self, package_dir: Optional[str] = None) -> dict:
        """Distribute all .pkg.zip packages in a directory.

        Args:
            package_dir: Directory containing .pkg.zip files. Defaults to output directory.

        Returns:
            Dict with count, per-package results, and failed count.
        """
        start = time.monotonic()

        if package_dir:
            dir_path = self._check_path(package_dir)
        else:
            dir_path = self._output_dir

        packages = sorted(dir_path.glob("*.pkg.zip"))
        results = []
        failed = 0

        for pkg in packages:
            try:
                r = await self.distribute_package(str(pkg))
                results.append(
                    {
                        "package_path": str(pkg),
                        "artifacts_distributed": r["artifacts_distributed"],
                        "errors": [e for e in r["results"] if e["status"] == "failed"],
                    }
                )
                if any(e["status"] == "failed" for e in r["results"]):
                    failed += 1
            except Exception as exc:
                results.append(
                    {
                        "package_path": str(pkg),
                        "artifacts_distributed": 0,
                        "errors": [{"error": str(exc)}],
                    }
                )
                failed += 1

        result = {
            "count": len(results),
            "results": results,
            "failed": failed,
        }

        self._audit.log(
            agent="distribution",
            tool="distribute_batch",
            inputs={"package_dir": str(dir_path)},
            outputs=result,
            start_time=start,
        )
        return result

    async def bootstrap_triplestore(
        self,
        ct_id: Optional[str] = None,
        include_third_party: bool = True,
    ) -> dict:
        """Bootstrap a triplestore with SDC4 ontologies and schema RDF.

        Loads ontology files from the cache into named graphs. Checks for
        existing graphs before uploading (idempotent).

        Args:
            ct_id: Optional schema ct_id to load its RDF as a named graph.
            include_third_party: If True, load third-party ontologies (default True).

        Returns:
            Dict with graphs_loaded list showing each graph's status.
        """
        start = time.monotonic()

        # Find triplestore destination
        ts_dest = None
        for name, dest in self._config.destinations.items():
            if dest.type in ("fuseki", "graphdb"):
                ts_dest = dest
                break

        if ts_dest is None:
            raise ValueError(
                "No triplestore destination configured. Add a 'fuseki' or "
                "'graphdb' entry to the destinations config."
            )

        endpoint = ts_dest.endpoint
        auth = ts_dest.auth
        graphs_loaded = []

        # Load ontology files from cache
        ontology_dir = self._cache.root / "ontologies"
        if ontology_dir.is_dir():
            for ont_file in sorted(ontology_dir.glob("*.rdf")):
                graph_uri = f"urn:sdc4:ontology:{ont_file.stem}"
                exists = await self._check_named_graph_exists(endpoint, auth, graph_uri)
                if exists:
                    graphs_loaded.append(
                        {
                            "name": ont_file.name,
                            "graph_uri": graph_uri,
                            "status": "already_exists",
                        }
                    )
                else:
                    content = ont_file.read_bytes()
                    await self._deliver_to_sparql(
                        endpoint,
                        auth,
                        content,
                        "application/rdf+xml",
                        graph_uri,
                    )
                    graphs_loaded.append(
                        {
                            "name": ont_file.name,
                            "graph_uri": graph_uri,
                            "status": "loaded",
                        }
                    )

            # Also load .ttl files
            for ttl_file in sorted(ontology_dir.glob("*.ttl")):
                graph_uri = f"urn:sdc4:ontology:{ttl_file.stem}"
                exists = await self._check_named_graph_exists(endpoint, auth, graph_uri)
                if exists:
                    graphs_loaded.append(
                        {
                            "name": ttl_file.name,
                            "graph_uri": graph_uri,
                            "status": "already_exists",
                        }
                    )
                else:
                    content = ttl_file.read_bytes()
                    await self._deliver_to_sparql(
                        endpoint,
                        auth,
                        content,
                        "text/turtle",
                        graph_uri,
                    )
                    graphs_loaded.append(
                        {
                            "name": ttl_file.name,
                            "graph_uri": graph_uri,
                            "status": "loaded",
                        }
                    )

        # Load schema RDF if ct_id provided
        if ct_id:
            schema_ttl = self._cache.root / "schemas" / f"dm-{ct_id}.ttl"
            if schema_ttl.is_file():
                graph_uri = f"urn:sdc4:schema:{ct_id}"
                exists = await self._check_named_graph_exists(endpoint, auth, graph_uri)
                if exists:
                    graphs_loaded.append(
                        {
                            "name": schema_ttl.name,
                            "graph_uri": graph_uri,
                            "status": "already_exists",
                        }
                    )
                else:
                    content = schema_ttl.read_bytes()
                    await self._deliver_to_sparql(
                        endpoint,
                        auth,
                        content,
                        "text/turtle",
                        graph_uri,
                    )
                    graphs_loaded.append(
                        {
                            "name": schema_ttl.name,
                            "graph_uri": graph_uri,
                            "status": "loaded",
                        }
                    )

        result = {"graphs_loaded": graphs_loaded}

        self._audit.log(
            agent="distribution",
            tool="bootstrap_triplestore",
            inputs={"ct_id": ct_id, "include_third_party": include_third_party},
            outputs=result,
            start_time=start,
        )
        return result
