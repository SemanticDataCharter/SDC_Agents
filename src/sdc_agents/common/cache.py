"""Cache manager for SDC Agents.

Provides path helpers and existence checks for cached artifacts
stored under the .sdc-cache/ directory tree.

Names passed to the helpers (ct_ids, mapping, datasource and source names)
often come from an agent or from a cached file, so they are checked: a name
is a single path component, and the path it builds must stay inside its
subdirectory. Anything else raises PermissionError.
"""

from __future__ import annotations

from pathlib import Path

# Characters that would let a name act as a path: separators on POSIX and
# Windows, the Windows drive colon, and NUL.
_FORBIDDEN_NAME_CHARS = frozenset("/\\:\0")


def check_name(name: str, what: str = "name") -> str:
    """Return ``name`` if it is safe to use as one path component.

    Rejects empty names, ``.`` and ``..``, names starting with ``..``, and
    names containing a path separator, a colon or NUL.
    """
    if not isinstance(name, str) or not name.strip():
        raise PermissionError(f"Invalid {what}: must be a non-empty string.")
    if name in (".", "..") or name.startswith("..") or set(name) & _FORBIDDEN_NAME_CHARS:
        raise PermissionError(
            f"Invalid {what} {name!r}: it must be a single name, with no path "
            "separators, colons or leading '..'."
        )
    return name


def check_inside(path: Path, root: Path, what: str = "path") -> Path:
    """Return ``path`` if it resolves (following symlinks) to somewhere inside ``root``."""
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise PermissionError(f"Access denied: {what} '{path}' is outside '{root}'.") from None
    return path


class CacheManager:
    """Manages the .sdc-cache directory structure and file lookups."""

    SUBDIRS = ("schemas", "ontologies", "introspections", "mappings", "knowledge")

    def __init__(self, root: str | Path = ".sdc-cache"):
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def ensure_dirs(self) -> None:
        """Create the cache root and all standard subdirectories."""
        for subdir in self.SUBDIRS:
            (self._root / subdir).mkdir(parents=True, exist_ok=True)

    def _entry(self, subdir: str, name: str, suffix: str, what: str) -> Path:
        """``<root>/<subdir>/<name><suffix>``, after checking ``name`` and containment."""
        check_name(name, what)
        base = self._root / subdir
        return check_inside(base / f"{name}{suffix}", base, what)

    def schema_path(self, ct_id: str) -> Path:
        """Path where a schema JSON file would be cached."""
        return self._entry("schemas", ct_id, ".json", "ct_id")

    def ontology_path(self, ct_id: str) -> Path:
        """Path where an ontology file would be cached."""
        return self._entry("ontologies", ct_id, ".rdf", "ct_id")

    def introspection_path(self, datasource_name: str) -> Path:
        """Path where introspection results would be cached."""
        return self._entry("introspections", datasource_name, ".json", "datasource name")

    def mapping_path(self, name: str) -> Path:
        """Path where a mapping config would be cached."""
        return self._entry("mappings", name, ".json", "mapping name")

    def skeleton_path(self, ct_id: str) -> Path:
        """Path where a skeleton XML instance would be cached."""
        return self._entry("schemas", ct_id, "_skeleton.xml", "ct_id")

    def field_mapping_path(self, ct_id: str) -> Path:
        """Path where a field mapping JSON would be cached."""
        return self._entry("schemas", ct_id, "_field_mapping.json", "ct_id")

    def knowledge_path(self, source_name: str) -> Path:
        """Path where knowledge source metadata would be cached."""
        return self._entry("knowledge", source_name, ".json", "source name")

    def is_cached(self, path: Path) -> bool:
        """Check whether a cached file exists and is non-empty."""
        return path.is_file() and path.stat().st_size > 0
