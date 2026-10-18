"""Validation Toolset: validate SDC4 instances locally, settle them on the VSL.

Validation is local and free: ``sdcvalidator`` validates an instance against
the model's published XSD 1.1 schema, which the toolset resolves from the
instance's own ``dm-<ct_id>`` identifier and fetches once from the public
catalog into the cache. Settlement is the one network write: the Verifiable
Settlement Layer validates, governs and signs one exchange and returns a
Settlement Receipt (one dollar, 1,000 credits, charged to the API key's
wallet).

Until 4.5.0 this toolset posted to the validation service (``/api/v1/vaas/``),
which SDCStudio retired when the settlement layer replaced it; every call
answered 404. Network access: the public catalog (schemas) and the
settlement endpoint (token auth). No datasource access.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

import httpx
from google.adk.tools import FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.cache import CacheManager
from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.common.exceptions import InsufficientFundsError

#: A model identifier as an instance carries it: ``dm-`` and a 24-character CUID2.
_DM_CT_ID = re.compile(r"dm-([a-z0-9]{24})")

#: Credits per dollar (SDCStudio Terms of Service, section 6).
_CREDITS_PER_USD = 1000


class ValidationToolset(BaseToolset):
    """Scoped toolset for SDC4 instance validation and settlement.

    Validates locally with ``sdcvalidator``; settles through the Verifiable
    Settlement Layer. The API key is needed for settlement only.
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
        self._schema_dir = Path(config.cache.root).resolve() / "schemas"
        self._schema_dir.mkdir(parents=True, exist_ok=True)
        self._audit = AuditLogger(config.audit.path, config.audit.log_level)
        self._output_dir = Path(config.output.directory).resolve()
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._validators: dict[str, object] = {}

        if http_client:
            self._http = http_client
        else:
            headers = {}
            if config.sdcstudio.api_key:
                headers["Authorization"] = f"Token {config.sdcstudio.api_key}"
            self._http = httpx.AsyncClient(base_url=self._base_url, headers=headers)

    async def get_tools(self, readonly_context=None) -> list:
        """Return the validation tools as FunctionTool instances."""
        tools = [
            FunctionTool(self.validate_instance),
            FunctionTool(self.settle_instance),
            FunctionTool(self.validate_batch),
        ]
        if readonly_context and self.tool_filter:
            return [t for t in tools if self._is_tool_selected(t, readonly_context)]
        return tools

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()

    # ------------------------------------------------------------------ paths

    def _check_path(self, path_str: str, *, roots: tuple[Path, ...] = ()) -> Path:
        """Verify a path is within the output directory (or one of ``roots``).

        Raises PermissionError if the path escapes every allowed directory.
        """
        resolved = Path(path_str).resolve()
        for root in (self._output_dir, *roots):
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue
        raise PermissionError(
            f"Access denied: '{path_str}' is outside the output directory "
            f"'{self._output_dir}'. Only files within the output directory "
            "can be validated."
        )

    # ---------------------------------------------------------------- schemas

    async def _resolve_schema(self, xml_text: str, schema_path: str) -> tuple[Path, str]:
        """The XSD to validate against, and the model id it belongs to.

        An explicit ``schema_path`` wins (it must be inside the output directory
        or the schema cache). Otherwise the instance's own ``dm-<ct_id>`` names
        the model; the schema is read from the cache or fetched once from the
        public catalog (``/api/v1/catalog/dm/<ct_id>/xsd/``).
        """
        if schema_path:
            path = self._check_path(schema_path, roots=(self._schema_dir,))
            if not path.is_file():
                raise FileNotFoundError(f"Schema not found: {schema_path}")
            m = _DM_CT_ID.search(path.name) or _DM_CT_ID.search(xml_text)
            return path, (m.group(1) if m else "")

        m = _DM_CT_ID.search(xml_text)
        if not m:
            raise ValueError(
                "The instance names no model (no 'dm-<ct_id>' in the document); "
                "pass schema_path explicitly."
            )
        ct_id = m.group(1)
        cached = self._schema_dir / f"dm-{ct_id}.xsd"
        if not cached.is_file():
            resp = await self._http.get(f"/api/v1/catalog/dm/{ct_id}/xsd/")
            if resp.status_code == 404:
                raise FileNotFoundError(
                    f"No published schema for dm-{ct_id} in the catalog; is the model published?"
                )
            resp.raise_for_status()
            cached.write_bytes(resp.content)
        return cached, ct_id

    def _validator(self, schema: Path):
        """One ``SDC4Validator`` per schema, built on first use."""
        key = str(schema)
        if key not in self._validators:
            from sdcvalidator import SDC4Validator

            self._validators[key] = SDC4Validator(schema)
        return self._validators[key]

    @staticmethod
    def _errors(result) -> list[dict]:
        out = []
        for tier, errors in (
            ("structural", result.structural_errors),
            ("semantic", result.semantic_errors),
        ):
            for e in errors:
                out.append(
                    {
                        "tier": tier,
                        "path": str(getattr(e, "path", "") or ""),
                        "reason": str(getattr(e, "reason", None) or e),
                    }
                )
        return out

    # ------------------------------------------------------------------ tools

    async def validate_instance(
        self,
        xml_path: str,
        schema_path: str = "",
        mode: str = "strict",
    ) -> dict:
        """Validate an SDC4 XML instance locally against its published schema.

        Free and offline once the schema is cached. ``sdcvalidator`` classifies
        errors as structural (wrong shape: reject) or semantic (wrong value:
        report), the two tiers SDC4 defines.

        Args:
            xml_path: Path to the XML instance (inside the output directory).
            schema_path: Optional path to the model's XSD. When omitted, the
                instance's own dm-<ct_id> names the schema, which is read from
                the cache or fetched once from the public catalog.
            mode: 'strict' (default) reports; 'recover' also writes a
                <name>.recovered.xml in which each invalid value is kept and
                flagged with an ExceptionalValue (ISO 21090 null flavor).

        Returns:
            Dict with valid, mode, schema {ct_id, path}, structural_errors,
            semantic_errors, errors [{tier, path, reason}], recovered, and
            recovered_path when a recovered file was written.
        """
        start = time.monotonic()
        if mode not in ("strict", "recover"):
            raise ValueError("mode must be 'strict' or 'recover'")

        resolved_path = self._check_path(xml_path)
        xml_text = resolved_path.read_text(encoding="utf-8")
        schema, ct_id = await self._resolve_schema(xml_text, schema_path)
        validator = self._validator(schema)

        result_obj = validator.validate(resolved_path)
        result = {
            "valid": bool(result_obj.is_valid),
            "mode": mode,
            "schema": {"ct_id": ct_id, "path": str(schema)},
            "structural_errors": len(result_obj.structural_errors),
            "semantic_errors": len(result_obj.semantic_errors),
            "errors": self._errors(result_obj),
            "recovered": False,
        }

        if mode == "recover" and not result_obj.is_valid and not result_obj.structural_errors:
            recovered_path = resolved_path.with_suffix(".recovered.xml")
            validator.validate_with_recovery(resolved_path, output_path=recovered_path)
            result["recovered"] = True
            result["recovered_path"] = str(recovered_path)
            result["recovered_valid"] = bool(validator.validate(recovered_path).is_valid)

        self._audit.log(
            agent="validation",
            tool="validate_instance",
            inputs={"xml_path": xml_path, "schema_path": schema_path, "mode": mode},
            outputs=result,
            start_time=start,
        )
        return result

    async def settle_instance(
        self,
        xml_path: str,
        target_state: str,
        condition: dict,
        parties: list[str],
        previous_receipt_id: str = "",
    ) -> dict:
        """Settle one exchange on the Verifiable Settlement Layer.

        The layer validates the record against its published schema, decides
        the proposed workflow transition with the model's governance (OASIS
        XACML semantics), and signs a Settlement Receipt. Costs 1,000 credits
        (one dollar) from the API key's wallet; the receipt is written beside
        the record as <name>.receipt.json and is verifiable offline with
        `sdcreceipt verify`.

        Args:
            xml_path: Path to the XML instance (inside the output directory).
            target_state: The workflow state the exchange moves the record to;
                the record's own <current-state> is the starting state.
            condition: The release condition (a JSON object). Hashed into the
                receipt, never stored.
            parties: At least two key identifiers the parties control
                (https:// or did:web:).
            previous_receipt_id: Optional id of the prior receipt in the chain.

        Returns:
            Dict with settled, receipt_id, receipt_path, receipt, governance,
            verification and charged (credits).
        """
        start = time.monotonic()
        if not self._config.sdcstudio.api_key:
            raise PermissionError(
                "Settlement needs an API key: set sdcstudio.api_key in your config."
            )

        resolved_path = self._check_path(xml_path)
        payload = resolved_path.read_text(encoding="utf-8")
        body: dict = {
            "payload": payload,
            "target_state": target_state,
            "condition": condition,
            "parties": parties,
        }
        if previous_receipt_id:
            body["previous_receipt_id"] = previous_receipt_id

        resp = await self._http.post("/api/v1/vsl/settle", json=body)
        if resp.status_code == 402:
            data = (
                resp.json()
                if resp.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            cost = data.get("cost", "")
            balance = data.get("balance", "")
            raise InsufficientFundsError(
                message=data.get("error", "Insufficient credits to issue a Settlement Receipt."),
                estimated_cost=cost,
                balance_remaining=balance if balance not in ("", "unknown") else "",
                estimated_cost_credits=int(float(cost) * _CREDITS_PER_USD) if cost else "",
                balance_remaining_credits=(
                    int(float(balance) * _CREDITS_PER_USD)
                    if balance not in ("", "unknown")
                    else ""
                ),
            )
        if resp.status_code in (400, 409, 422):
            # The server says why (an invalid record, a transition governance
            # would not permit, with the transitions it would): surface it whole.
            try:
                detail = resp.json()
            except ValueError:
                detail = {"error": resp.text}
            raise ValueError(f"Settlement refused ({resp.status_code}): {json.dumps(detail)}")
        resp.raise_for_status()

        data = resp.json()
        receipt = data.get("receipt", {})
        receipt_path = resolved_path.with_suffix(".receipt.json")
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        charged = data.get("charged", "")
        result = {
            "settled": True,
            "receipt_id": receipt.get("receipt_id", receipt.get("id", "")),
            "receipt_path": str(receipt_path),
            "receipt": receipt,
            "governance": data.get("governance", {}),
            "verification": data.get("verification", {}),
            "charged_credits": int(float(charged) * _CREDITS_PER_USD) if charged else None,
        }

        self._audit.log(
            agent="validation",
            tool="settle_instance",
            inputs={
                "xml_path": xml_path,
                "target_state": target_state,
                "parties": parties,
                "previous_receipt_id": previous_receipt_id,
            },
            outputs={k: v for k, v in result.items() if k != "receipt"},
            start_time=start,
        )
        return result

    async def validate_batch(
        self,
        xml_dir: str = "",
        schema_path: str = "",
        mode: str = "strict",
    ) -> dict:
        """Validate every XML instance in a directory, locally.

        Args:
            xml_dir: Directory of XML files. Defaults to the output directory.
            schema_path: Optional XSD for every file; otherwise each instance
                names its own model.
            mode: 'strict' or 'recover', as for validate_instance.

        Returns:
            Dict with count, results [{xml_path, valid, errors, ...}], and failed.
        """
        start = time.monotonic()
        dir_path = self._check_path(xml_dir) if xml_dir else self._output_dir
        xml_files = sorted(
            p for p in dir_path.glob("*.xml") if not p.name.endswith(".recovered.xml")
        )

        results = []
        failed = 0
        for xml_file in xml_files:
            try:
                r = await self.validate_instance(
                    xml_path=str(xml_file), schema_path=schema_path, mode=mode
                )
                entry = {"xml_path": str(xml_file), "valid": r["valid"], "errors": r["errors"]}
                if r.get("recovered"):
                    entry["recovered_path"] = r["recovered_path"]
                results.append(entry)
                if not r["valid"]:
                    failed += 1
            except Exception as exc:  # one bad file does not stop the batch
                results.append(
                    {"xml_path": str(xml_file), "valid": False, "errors": [{"error": str(exc)}]}
                )
                failed += 1

        result = {"count": len(results), "results": results, "failed": failed}
        self._audit.log(
            agent="validation",
            tool="validate_batch",
            inputs={"xml_dir": str(dir_path), "schema_path": schema_path, "mode": mode},
            outputs=result,
            start_time=start,
        )
        return result
