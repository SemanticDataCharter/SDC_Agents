"""Validation Toolset — validate and sign XML instances via VaaS API.

Provides instance validation, signing, and batch processing tools.
Network access to SDCStudio VaaS API only. Token auth required.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import httpx
from google.adk.tools import FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.cache import CacheManager
from sdc_agents.common.config import SDCAgentsConfig


class ValidationToolset(BaseToolset):
    """Scoped toolset for SDC4 XML instance validation and signing.

    Validates XML instances against their schemas via the VaaS API.
    Requires an API token for authentication.
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
        self._output_dir = Path(config.output.directory).resolve()
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # Set up HTTP client with auth token
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

    async def get_tools(self, readonly_context=None) -> list:
        """Return the validation tools as FunctionTool instances."""
        tools = [
            FunctionTool(self.validate_instance),
            FunctionTool(self.sign_instance),
            FunctionTool(self.validate_batch),
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
        output_resolved = self._output_dir

        # Check that the resolved path starts with the output directory
        try:
            resolved.relative_to(output_resolved)
        except ValueError:
            raise PermissionError(
                f"Access denied: '{path_str}' is outside the output directory "
                f"'{output_resolved}'. Only files within the output directory "
                "can be validated."
            )
        return resolved

    async def validate_instance(
        self,
        xml_path: str,
        mode: str = "recover",
        package: bool = False,
    ) -> dict:
        """Validate an XML instance against its schema via the VaaS API.

        Args:
            xml_path: Path to the XML instance file (must be within output directory).
            mode: Validation mode — 'strict' or 'recover' (default 'recover').
            package: If True, request an artifact package (.zip) alongside validation.

        Returns:
            Dict with valid, mode, schema info, error counts, and optional
            recovered XML path and package path.
        """
        start = time.monotonic()

        resolved_path = self._check_path(xml_path)
        xml_content = resolved_path.read_text()

        resp = await self._http.post(
            "/api/v1/vaas/validate/",
            params={"mode": mode, "package": str(package).lower()},
            content=xml_content,
            headers={"Content-Type": "application/xml"},
        )
        resp.raise_for_status()

        data = resp.json()

        result = {
            "valid": data.get("valid", False),
            "mode": data.get("mode", mode),
            "schema": data.get("schema", {}),
            "structural_errors": data.get("structural_errors", 0),
            "semantic_errors": data.get("semantic_errors", 0),
            "recovered": data.get("recovered", False),
            "errors": data.get("errors", []),
        }

        # Write recovered XML if provided
        if data.get("recovered_xml"):
            recovered_path = resolved_path.with_suffix(".recovered.xml")
            recovered_path.write_text(data["recovered_xml"])
            result["recovered_path"] = str(recovered_path)

        # Write package if provided
        if package and resp.headers.get("X-Package-Url"):
            pkg_resp = await self._http.get(resp.headers["X-Package-Url"])
            pkg_resp.raise_for_status()
            pkg_path = resolved_path.with_suffix(".pkg.zip")
            pkg_path.write_bytes(pkg_resp.content)
            result["package_path"] = str(pkg_path)
        elif data.get("package_bytes"):
            # Package bytes inline in response (for testing)
            import base64

            pkg_path = resolved_path.with_suffix(".pkg.zip")
            pkg_path.write_bytes(base64.b64decode(data["package_bytes"]))
            result["package_path"] = str(pkg_path)

        self._audit.log(
            agent="validation",
            tool="validate_instance",
            inputs={"xml_path": xml_path, "mode": mode, "package": package},
            outputs=result,
            start_time=start,
        )
        return result

    async def sign_instance(
        self,
        xml_path: str,
        recover: bool = True,
        package: bool = False,
    ) -> dict:
        """Sign an XML instance via the VaaS API.

        Args:
            xml_path: Path to the XML instance file (must be within output directory).
            recover: If True, attempt recovery before signing (default True).
            package: If True, request an artifact package alongside signing.

        Returns:
            Dict with valid, signed, signature metadata, verification info,
            and optional package path.
        """
        start = time.monotonic()

        resolved_path = self._check_path(xml_path)
        xml_content = resolved_path.read_text()

        resp = await self._http.post(
            "/api/v1/vaas/validate/sign/",
            params={
                "recover": str(recover).lower(),
                "package": str(package).lower(),
            },
            content=xml_content,
            headers={"Content-Type": "application/xml"},
        )
        resp.raise_for_status()

        data = resp.json()

        result = {
            "valid": data.get("valid", False),
            "signed": data.get("signed", False),
            "signature": data.get("signature", {}),
            "verification": data.get("verification", {}),
        }

        # Write signed XML if provided
        if data.get("signed_xml"):
            signed_path = resolved_path.with_suffix(".signed.xml")
            signed_path.write_text(data["signed_xml"])
            result["signed_path"] = str(signed_path)

        # Write package if provided
        if data.get("package_bytes"):
            import base64

            pkg_path = resolved_path.with_suffix(".pkg.zip")
            pkg_path.write_bytes(base64.b64decode(data["package_bytes"]))
            result["package_path"] = str(pkg_path)

        self._audit.log(
            agent="validation",
            tool="sign_instance",
            inputs={"xml_path": xml_path, "recover": recover, "package": package},
            outputs=result,
            start_time=start,
        )
        return result

    async def validate_batch(
        self,
        xml_dir: Optional[str] = None,
        sign: bool = False,
        package: bool = True,
    ) -> dict:
        """Validate (and optionally sign) all XML instances in a directory.

        Args:
            xml_dir: Directory containing XML files. Defaults to output directory.
            sign: If True, sign valid instances after validation (default False).
            package: If True, request artifact packages (default True).

        Returns:
            Dict with count, results list, and failed count.
        """
        start = time.monotonic()

        if xml_dir:
            dir_path = self._check_path(xml_dir)
        else:
            dir_path = self._output_dir

        # Find XML files, excluding recovered and signed variants
        xml_files = sorted(
            p for p in dir_path.glob("*.xml")
            if not p.name.endswith(".recovered.xml")
            and not p.name.endswith(".signed.xml")
        )

        results = []
        failed = 0
        for xml_file in xml_files:
            try:
                if sign:
                    r = await self.sign_instance(
                        xml_path=str(xml_file), package=package
                    )
                else:
                    r = await self.validate_instance(
                        xml_path=str(xml_file), package=package
                    )
                entry = {
                    "xml_path": str(xml_file),
                    "valid": r.get("valid", False),
                    "signed": r.get("signed", False),
                    "errors": r.get("errors", []),
                }
                if "package_path" in r:
                    entry["package_path"] = r["package_path"]
                results.append(entry)
                if not r.get("valid", False):
                    failed += 1
            except Exception as exc:
                results.append({
                    "xml_path": str(xml_file),
                    "valid": False,
                    "signed": False,
                    "errors": [{"error": str(exc)}],
                })
                failed += 1

        result = {
            "count": len(results),
            "results": results,
            "failed": failed,
        }

        self._audit.log(
            agent="validation",
            tool="validate_batch",
            inputs={"xml_dir": str(dir_path), "sign": sign, "package": package},
            outputs=result,
            start_time=start,
        )
        return result
