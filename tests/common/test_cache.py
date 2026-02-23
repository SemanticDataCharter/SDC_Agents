"""Tests for the cache manager."""

from __future__ import annotations

from sdc_agents.common.cache import CacheManager


def test_ensure_dirs_creates_subdirs(tmp_cache: CacheManager):
    """ensure_dirs creates all standard subdirectories."""
    for subdir in CacheManager.SUBDIRS:
        assert (tmp_cache.root / subdir).is_dir()


def test_schema_path(tmp_cache: CacheManager):
    """schema_path returns correct path."""
    path = tmp_cache.schema_path("clxyz123abc")
    assert path == tmp_cache.root / "schemas" / "clxyz123abc.json"


def test_ontology_path(tmp_cache: CacheManager):
    """ontology_path returns correct path."""
    path = tmp_cache.ontology_path("clxyz123abc")
    assert path == tmp_cache.root / "ontologies" / "clxyz123abc.rdf"


def test_introspection_path(tmp_cache: CacheManager):
    """introspection_path returns correct path."""
    path = tmp_cache.introspection_path("lab_db")
    assert path == tmp_cache.root / "introspections" / "lab_db.json"


def test_mapping_path(tmp_cache: CacheManager):
    """mapping_path returns correct path."""
    path = tmp_cache.mapping_path("lab-mapping")
    assert path == tmp_cache.root / "mappings" / "lab-mapping.json"


def test_is_cached_false_for_missing(tmp_cache: CacheManager):
    """is_cached returns False for non-existent files."""
    assert not tmp_cache.is_cached(tmp_cache.schema_path("nonexistent"))


def test_is_cached_true_for_existing(tmp_cache: CacheManager):
    """is_cached returns True for existing non-empty files."""
    path = tmp_cache.schema_path("test")
    path.write_text('{"test": true}')
    assert tmp_cache.is_cached(path)


def test_is_cached_false_for_empty(tmp_cache: CacheManager):
    """is_cached returns False for empty files."""
    path = tmp_cache.schema_path("empty")
    path.write_text("")
    assert not tmp_cache.is_cached(path)
