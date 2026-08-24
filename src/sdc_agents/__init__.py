"""SDC Agents: Purpose-scoped ADK agents for SDC4 data operations."""

from importlib.metadata import PackageNotFoundError, version

# Derived from the installed distribution rather than written out here, so it
# cannot drift from pyproject.toml. It already had: this file said 4.3.3 while
# pyproject and PyPI said 4.4.0.
try:
    __version__ = version("sdc-agents")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
