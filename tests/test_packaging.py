"""
Packaging invariants.

Both of these were real: __init__.py said 4.3.3 while pyproject and PyPI said
4.4.0, and `pip install -e ".[dev]"` produced a suite that could not fully pass
because the BigQuery tests need an extra that dev did not pull.
"""
import importlib.metadata as md
import tomllib
from pathlib import Path

import pytest

import sdc_agents

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _pyproject():
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)


def test_version_matches_the_installed_distribution():
    assert sdc_agents.__version__ == md.version("sdc-agents")


def test_version_matches_pyproject():
    """pyproject is the source of truth; __init__ derives from the install."""
    assert sdc_agents.__version__ == _pyproject()["project"]["version"]


def test_version_is_not_hardcoded_in_init():
    """
    A literal here is how the drift happened. It must be derived so the two
    cannot disagree again.
    """
    src = (Path(sdc_agents.__file__)).read_text()
    assert "importlib.metadata" in src, "__version__ must be derived, not written out"
    assert '__version__ = "4' not in src, "__version__ is hardcoded again"


def test_dev_extra_can_run_the_whole_suite():
    """The BigQuery introspection tests are in the suite, so dev must cover them."""
    dev = _pyproject()["project"]["optional-dependencies"]["dev"]
    assert any("bigquery" in d for d in dev), (
        'pip install -e ".[dev]" must be able to run every test'
    )


def test_bigquery_is_actually_importable():
    pytest.importorskip("google.cloud.bigquery")
