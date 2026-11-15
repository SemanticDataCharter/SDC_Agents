"""F-B: the generator writes only inside the output directory.

``schema_ct_id`` comes from a cached mapping file and ``mapping_name`` from
the agent; both used to be joined into file paths unchecked. Names are now
single path components, checked in CacheManager, and the generator's output
path must resolve inside the output directory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sdc_agents.common.cache import CacheManager, check_inside, check_name
from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.generator import GeneratorToolset
from sdc_agents.toolsets.mapping import MappingToolset

BAD_NAMES = [
    "../../OUTSIDE/pwned",
    "../x",
    "..",
    ".",
    "",
    "   ",
    "a/b",
    "a\\b",
    "C:evil",
    "/etc/passwd",
    "..hidden",
    "nul\0byte",
]


@pytest.fixture
def layout(tmp_path: Path):
    cache = tmp_path / ".sdc-cache"
    out = tmp_path / "nested" / "output"
    (cache / "mappings").mkdir(parents=True)
    (cache / "schemas").mkdir(parents=True)
    out.mkdir(parents=True)
    config = SDCAgentsConfig(
        cache={"root": str(cache)},
        output={"directory": str(out)},
        audit={"path": str(tmp_path / "audit.jsonl")},
    )
    return config, cache, out, tmp_path


def _xml_files(tmp_path: Path) -> set[Path]:
    return {p.resolve() for p in tmp_path.rglob("*.xml")}


async def test_assessment_case_is_refused(layout):
    """The 4.5.1 assessment's exact setup: ct_id '../../OUTSIDE/pwned'."""
    config, cache, out, tmp_path = layout
    ct = "../../OUTSIDE/pwned"
    (cache / "mappings" / "m.json").write_text(json.dumps({"schema_ct_id": ct}))
    skeleton = cache / "schemas" / f"{ct}_skeleton.xml"
    skeleton.parent.mkdir(parents=True, exist_ok=True)
    skeleton.write_text("<root/>")
    (cache / "schemas" / f"{ct}_field_mapping.json").write_text("{}")
    (tmp_path / "nested" / "OUTSIDE").mkdir(parents=True)

    before = _xml_files(tmp_path)
    toolset = GeneratorToolset(config=config)
    with pytest.raises(PermissionError, match="schema_ct_id"):
        await toolset.generate_instance("m", record={})
    with pytest.raises(PermissionError, match="schema_ct_id"):
        await toolset.generate_batch("m", limit=3)
    assert not (tmp_path / "nested" / "OUTSIDE" / "pwned_0.xml").exists()
    assert _xml_files(tmp_path) == before  # nothing written anywhere


@pytest.mark.parametrize("name", BAD_NAMES)
async def test_bad_mapping_names_are_refused(layout, name):
    config, cache, out, tmp_path = layout
    toolset = GeneratorToolset(config=config)
    with pytest.raises(PermissionError):
        await toolset.generate_instance(name, record={})


@pytest.mark.parametrize("name", BAD_NAMES)
async def test_mapping_confirm_refuses_bad_names(layout, name):
    config, cache, out, tmp_path = layout
    toolset = MappingToolset(config=config)
    mappings = [{"column_name": "a", "component_ct_id": "c1", "component_type": "XdString"}]
    with pytest.raises(PermissionError):
        await toolset.mapping_confirm(name, mappings, "clgood", "ds")
    if name.strip():  # an empty schema_ct_id means "not given" and is allowed
        with pytest.raises(PermissionError):
            await toolset.mapping_confirm("good", mappings, name, "ds")
    assert not (cache / "mappings" / "good.json").exists()


async def test_symlinked_output_file_is_refused(layout):
    """A symlink planted in the output dir can't redirect the write elsewhere."""
    config, cache, out, tmp_path = layout
    ct = "clsym"
    (cache / "mappings" / "m.json").write_text(json.dumps({"schema_ct_id": ct}))
    (cache / "schemas" / f"{ct}_skeleton.xml").write_text("<root/>")
    (cache / "schemas" / f"{ct}_field_mapping.json").write_text("{}")
    target = tmp_path / "victim.xml"
    target.write_text("original")
    try:
        os.symlink(target, out / f"{ct}_0.xml")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")

    with pytest.raises(PermissionError, match="output file"):
        await GeneratorToolset(config=config).generate_instance("m", record={})
    assert target.read_text() == "original"


async def test_good_names_still_generate(layout):
    config, cache, out, tmp_path = layout
    ct = "clabc123"
    (cache / "mappings" / "lab-mapping.v2.json").write_text(json.dumps({"schema_ct_id": ct}))
    (cache / "schemas" / f"{ct}_skeleton.xml").write_text("<root/>")
    (cache / "schemas" / f"{ct}_field_mapping.json").write_text("{}")
    result = await GeneratorToolset(config=config).generate_instance("lab-mapping.v2", record={})
    assert Path(result["xml_path"]) == out / f"{ct}_0.xml"
    assert (out / f"{ct}_0.xml").read_text() == "<root/>"


@pytest.mark.parametrize(
    "helper",
    [
        "schema_path",
        "ontology_path",
        "introspection_path",
        "mapping_path",
        "skeleton_path",
        "field_mapping_path",
        "knowledge_path",
    ],
)
@pytest.mark.parametrize("name", BAD_NAMES)
def test_every_cache_helper_refuses_bad_names(tmp_path: Path, helper, name):
    cache = CacheManager(tmp_path / ".sdc-cache")
    with pytest.raises(PermissionError):
        getattr(cache, helper)(name)


def test_cache_helper_refuses_symlinked_subdir_escape(tmp_path: Path):
    cache = CacheManager(tmp_path / ".sdc-cache")
    cache.ensure_dirs()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = cache.root / "mappings" / "evil.json"
    try:
        os.symlink(outside / "x.json", link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    with pytest.raises(PermissionError):
        cache.mapping_path("evil")


@pytest.mark.parametrize("name", ["clxyz123abc", "lab_db", "lab-mapping", "v1.2", "Lab DB"])
def test_ordinary_names_pass(name):
    assert check_name(name) == name


def test_check_inside(tmp_path: Path):
    assert check_inside(tmp_path / "a" / "b", tmp_path) == tmp_path / "a" / "b"
    with pytest.raises(PermissionError):
        check_inside(tmp_path / ".." / "x", tmp_path)
