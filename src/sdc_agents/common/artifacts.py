"""Fetch a catalog artifact, following the storage pointer production returns.

``/api/v1/catalog/dm/<ct_id>/<xsd|ttl|...>/`` streams the file when SDCStudio
keeps artifacts on local disk, and on the production deployment, where they
live in cloud storage, answers ``{"download_url": ..., "filename": ...,
"storage": "gcs"}`` instead. A caller that saved the response body as the
artifact saved that JSON (SDC_Agents 4.5.0, found by validating a record
against production). The second request goes to the storage host without the
SDCStudio API key.
"""

from __future__ import annotations

import httpx


async def fetch_artifact_bytes(http: httpx.AsyncClient, path: str) -> bytes:
    """GET ``path`` on the SDCStudio client; follow a storage pointer if one comes back."""
    resp = await http.get(path)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            data = resp.json()
        except ValueError:
            data = None
        if isinstance(data, dict) and data.get("download_url"):
            request = http.build_request("GET", data["download_url"])
            # The storage host is not SDCStudio: never send it the API key.
            request.headers.pop("authorization", None)
            stored = await http.send(request, follow_redirects=True)
            stored.raise_for_status()
            return stored.content
    return resp.content
