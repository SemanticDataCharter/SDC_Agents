"""Integration tests for MCP Toolbox integration.

These tests require a running Toolbox server and are skipped
if the toolbox-adk package is not installed or the server is unreachable.
"""

from __future__ import annotations

import pytest

# Skip the entire module if toolbox-adk is not installed
try:
    from toolbox_adk import ToolboxToolset  # noqa: F401

    HAS_TOOLBOX = True
except ImportError:
    HAS_TOOLBOX = False

pytestmark = pytest.mark.skipif(
    not HAS_TOOLBOX,
    reason="toolbox-adk not installed",
)


@pytest.fixture
def toolbox_url():
    """Toolbox server URL for integration testing."""
    return "http://localhost:5000"


async def test_toolbox_import():
    """ToolboxToolset can be imported."""
    from toolbox_adk import ToolboxToolset

    assert ToolboxToolset is not None


async def test_toolbox_connection(toolbox_url: str):
    """ToolboxToolset can connect to a running server.

    This test is expected to fail/skip if no server is running.
    """
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{toolbox_url}/health", timeout=2.0)
            assert resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        pytest.skip("Toolbox server not running")
