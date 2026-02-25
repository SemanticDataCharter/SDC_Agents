"""Tests for the Knowledge toolset."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.toolsets.knowledge import KnowledgeToolset

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def knowledge_config(tmp_path: Path) -> SDCAgentsConfig:
    """Config with knowledge sources pointing to test fixture files."""
    return SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        knowledge={
            "vector_store": "chroma",
            "vector_store_path": str(tmp_path / "chroma"),
            "sources": {
                "glossary": {
                    "type": "json",
                    "path": str(FIXTURES / "sample_data" / "glossary.json"),
                },
                "vocab": {
                    "type": "ttl",
                    "path": str(FIXTURES / "sample_data" / "vocab.ttl"),
                },
                "data_dictionary": {
                    "type": "markdown",
                    "path": str(FIXTURES / "sample_data" / "data_dictionary.md"),
                },
            },
        },
    )


@pytest.fixture
def csv_knowledge_config(tmp_path: Path) -> SDCAgentsConfig:
    """Config with a CSV knowledge source."""
    csv_file = tmp_path / "terms.csv"
    csv_file.write_text("term,definition\npatient_id,Unique patient ID\ntest_name,Lab test name\n")
    return SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        knowledge={
            "vector_store": "chroma",
            "vector_store_path": str(tmp_path / "chroma"),
            "sources": {
                "terms": {
                    "type": "csv",
                    "path": str(csv_file),
                },
            },
        },
    )


def _mock_collection():
    """Create a mock Chroma collection."""
    coll = MagicMock()
    coll.add = MagicMock()
    coll.get = MagicMock(return_value={"ids": []})
    coll.query = MagicMock(
        return_value={
            "documents": [["patient identifier text", "MRN definition"]],
            "metadatas": [[{"source": "glossary"}, {"source": "glossary"}]],
            "distances": [[0.15, 0.30]],
        }
    )
    return coll


def _mock_chroma_client(collection):
    """Create a mock Chroma PersistentClient."""
    client = MagicMock()
    client.get_or_create_collection = MagicMock(return_value=collection)
    return client


async def test_get_tools_returns_three(knowledge_config):
    """Knowledge toolset exposes exactly 3 tools."""
    toolset = KnowledgeToolset(config=knowledge_config)
    tools = await toolset.get_tools()
    assert len(tools) == 3
    names = {t.name for t in tools}
    assert names == {"ingest_knowledge_source", "query_knowledge", "list_indexed_sources"}


async def test_ingest_json_source(knowledge_config):
    """Ingest a JSON knowledge source with mocked Chroma."""
    collection = _mock_collection()
    mock_client = _mock_chroma_client(collection)

    toolset = KnowledgeToolset(config=knowledge_config)

    with patch("sdc_agents.toolsets.knowledge.chromadb") as mock_chromadb:
        mock_chromadb.PersistentClient = MagicMock(return_value=mock_client)
        result = await toolset.ingest_knowledge_source("glossary")

    assert result["source_name"] == "glossary"
    assert result["type"] == "json"
    assert result["status"] == "ready"
    assert result["chunks_indexed"] > 0
    collection.add.assert_called_once()


async def test_ingest_csv_source(csv_knowledge_config):
    """Ingest a CSV knowledge source with mocked Chroma."""
    collection = _mock_collection()
    mock_client = _mock_chroma_client(collection)

    toolset = KnowledgeToolset(config=csv_knowledge_config)

    with patch("sdc_agents.toolsets.knowledge.chromadb") as mock_chromadb:
        mock_chromadb.PersistentClient = MagicMock(return_value=mock_client)
        result = await toolset.ingest_knowledge_source("terms")

    assert result["source_name"] == "terms"
    assert result["type"] == "csv"
    assert result["status"] == "ready"
    assert result["chunks_indexed"] == 2  # 2 data rows
    collection.add.assert_called_once()


async def test_ingest_ttl_source(knowledge_config):
    """Ingest a TTL knowledge source with mocked Chroma."""
    collection = _mock_collection()
    mock_client = _mock_chroma_client(collection)

    toolset = KnowledgeToolset(config=knowledge_config)

    with patch("sdc_agents.toolsets.knowledge.chromadb") as mock_chromadb:
        mock_chromadb.PersistentClient = MagicMock(return_value=mock_client)
        result = await toolset.ingest_knowledge_source("vocab")

    assert result["source_name"] == "vocab"
    assert result["type"] == "ttl"
    assert result["status"] == "ready"
    assert result["chunks_indexed"] > 0
    collection.add.assert_called_once()


async def test_ingest_markdown_source(knowledge_config):
    """Ingest a Markdown knowledge source with mocked Chroma."""
    collection = _mock_collection()
    mock_client = _mock_chroma_client(collection)

    toolset = KnowledgeToolset(config=knowledge_config)

    with patch("sdc_agents.toolsets.knowledge.chromadb") as mock_chromadb:
        mock_chromadb.PersistentClient = MagicMock(return_value=mock_client)
        result = await toolset.ingest_knowledge_source("data_dictionary")

    assert result["source_name"] == "data_dictionary"
    assert result["type"] == "markdown"
    assert result["status"] == "ready"
    assert result["chunks_indexed"] > 0
    collection.add.assert_called_once()


async def test_ingest_unknown_source(knowledge_config):
    """Unknown source name raises KeyError."""
    toolset = KnowledgeToolset(config=knowledge_config)
    with pytest.raises(KeyError, match="Unknown knowledge source 'nonexistent'"):
        await toolset.ingest_knowledge_source("nonexistent")


async def test_query_knowledge(knowledge_config):
    """Query returns results with expected shape."""
    collection = _mock_collection()
    mock_client = _mock_chroma_client(collection)

    toolset = KnowledgeToolset(config=knowledge_config)

    with patch("sdc_agents.toolsets.knowledge.chromadb") as mock_chromadb:
        mock_chromadb.PersistentClient = MagicMock(return_value=mock_client)
        result = await toolset.query_knowledge("patient identifier", limit=5)

    assert result["query"] == "patient identifier"
    assert result["result_count"] == 2
    assert len(result["results"]) == 2
    for r in result["results"]:
        assert "source" in r
        assert "text" in r
        assert "score" in r


async def test_list_indexed_sources(knowledge_config, tmp_path):
    """List returns metadata for cached source files."""
    toolset = KnowledgeToolset(config=knowledge_config)

    # Write some metadata files
    knowledge_dir = tmp_path / ".sdc-cache" / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "source_name": "glossary",
        "type": "json",
        "chunks_indexed": 5,
        "status": "ready",
    }
    (knowledge_dir / "glossary.json").write_text(json.dumps(meta))

    sources = await toolset.list_indexed_sources()
    assert len(sources) == 1
    assert sources[0]["source_name"] == "glossary"
    assert sources[0]["type"] == "json"
    assert sources[0]["chunks_indexed"] == 5
    assert sources[0]["status"] == "ready"


# --- PDF/DOCX support ---


@pytest.fixture
def pdf_knowledge_config(tmp_path: Path) -> SDCAgentsConfig:
    """Config with a PDF knowledge source."""
    pdf_file = tmp_path / "policy.pdf"
    pdf_file.write_bytes(b"fake pdf content")  # Will be mocked
    return SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        knowledge={
            "vector_store": "chroma",
            "vector_store_path": str(tmp_path / "chroma"),
            "sources": {
                "policy": {
                    "type": "pdf",
                    "path": str(pdf_file),
                },
            },
        },
    )


@pytest.fixture
def docx_knowledge_config(tmp_path: Path) -> SDCAgentsConfig:
    """Config with a DOCX knowledge source."""
    docx_file = tmp_path / "requirements.docx"
    docx_file.write_bytes(b"fake docx content")  # Will be mocked
    return SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / "audit.jsonl")},
        knowledge={
            "vector_store": "chroma",
            "vector_store_path": str(tmp_path / "chroma"),
            "sources": {
                "requirements": {
                    "type": "docx",
                    "path": str(docx_file),
                },
            },
        },
    )


async def test_ingest_pdf_source(pdf_knowledge_config):
    """Ingest a PDF knowledge source with mocked pymupdf and Chroma."""
    collection = _mock_collection()
    mock_client = _mock_chroma_client(collection)

    # Mock pymupdf page objects
    mock_page1 = MagicMock()
    mock_page1.get_text.return_value = "Chapter 1: Data Governance Policy. "
    mock_page2 = MagicMock()
    mock_page2.get_text.return_value = "Chapter 2: Data Quality Standards."

    mock_doc = MagicMock()
    mock_doc.__iter__ = MagicMock(return_value=iter([mock_page1, mock_page2]))
    mock_doc.close = MagicMock()

    mock_pymupdf = MagicMock()
    mock_pymupdf.open.return_value = mock_doc

    toolset = KnowledgeToolset(config=pdf_knowledge_config)

    with (
        patch("sdc_agents.toolsets.knowledge.pymupdf", mock_pymupdf),
        patch("sdc_agents.toolsets.knowledge.chromadb") as mock_chromadb,
    ):
        mock_chromadb.PersistentClient = MagicMock(return_value=mock_client)
        result = await toolset.ingest_knowledge_source("policy")

    assert result["source_name"] == "policy"
    assert result["type"] == "pdf"
    assert result["status"] == "ready"
    assert result["chunks_indexed"] > 0
    collection.add.assert_called_once()
    mock_doc.close.assert_called_once()


async def test_ingest_docx_source(docx_knowledge_config):
    """Ingest a DOCX knowledge source with mocked python-docx and Chroma."""
    collection = _mock_collection()
    mock_client = _mock_chroma_client(collection)

    # Mock python-docx Document with paragraphs
    mock_para1 = MagicMock()
    mock_para1.text = "Section 1: Requirements Overview"
    mock_para2 = MagicMock()
    mock_para2.text = "Section 2: Functional Requirements"
    mock_para_empty = MagicMock()
    mock_para_empty.text = ""

    mock_doc = MagicMock()
    mock_doc.paragraphs = [mock_para1, mock_para_empty, mock_para2]

    mock_python_docx = MagicMock()
    mock_python_docx.Document.return_value = mock_doc

    toolset = KnowledgeToolset(config=docx_knowledge_config)

    with (
        patch("sdc_agents.toolsets.knowledge.python_docx", mock_python_docx),
        patch("sdc_agents.toolsets.knowledge.chromadb") as mock_chromadb,
    ):
        mock_chromadb.PersistentClient = MagicMock(return_value=mock_client)
        result = await toolset.ingest_knowledge_source("requirements")

    assert result["source_name"] == "requirements"
    assert result["type"] == "docx"
    assert result["status"] == "ready"
    assert result["chunks_indexed"] > 0
    collection.add.assert_called_once()


async def test_pdf_missing_pymupdf_raises(pdf_knowledge_config):
    """Missing pymupdf raises ImportError with install message."""
    toolset = KnowledgeToolset(config=pdf_knowledge_config)

    with patch("sdc_agents.toolsets.knowledge.pymupdf", None):
        with pytest.raises(ImportError, match="pymupdf is required"):
            await toolset.ingest_knowledge_source("policy")


async def test_docx_missing_python_docx_raises(docx_knowledge_config):
    """Missing python-docx raises ImportError with install message."""
    toolset = KnowledgeToolset(config=docx_knowledge_config)

    with patch("sdc_agents.toolsets.knowledge.python_docx", None):
        with pytest.raises(ImportError, match="python-docx is required"):
            await toolset.ingest_knowledge_source("requirements")
