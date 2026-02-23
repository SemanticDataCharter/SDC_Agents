"""Cache manager for SDC Agents.

Provides path helpers and existence checks for cached artifacts
stored under the .sdc-cache/ directory tree.
"""

from __future__ import annotations

from pathlib import Path


class CacheManager:
    """Manages the .sdc-cache directory structure and file lookups."""

    SUBDIRS = ("schemas", "ontologies", "introspections", "mappings")

    def __init__(self, root: str | Path = ".sdc-cache"):
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def ensure_dirs(self) -> None:
        """Create the cache root and all standard subdirectories."""
        for subdir in self.SUBDIRS:
            (self._root / subdir).mkdir(parents=True, exist_ok=True)

    def schema_path(self, ct_id: str) -> Path:
        """Path where a schema JSON file would be cached."""
        return self._root / "schemas" / f"{ct_id}.json"

    def ontology_path(self, ct_id: str) -> Path:
        """Path where an ontology file would be cached."""
        return self._root / "ontologies" / f"{ct_id}.rdf"

    def introspection_path(self, datasource_name: str) -> Path:
        """Path where introspection results would be cached."""
        return self._root / "introspections" / f"{datasource_name}.json"

    def mapping_path(self, name: str) -> Path:
        """Path where a mapping config would be cached."""
        return self._root / "mappings" / f"{name}.json"

    def is_cached(self, path: Path) -> bool:
        """Check whether a cached file exists and is non-empty."""
        return path.is_file() and path.stat().st_size > 0
