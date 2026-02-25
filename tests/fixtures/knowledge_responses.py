"""Test fixtures for Knowledge Agent responses."""

from __future__ import annotations


def make_knowledge_ingest_result(
    source_name: str = "glossary",
    source_type: str = "json",
    path: str = "tests/fixtures/sample_data/glossary.json",
    chunks_indexed: int = 5,
) -> dict:
    """Sample ingest output as returned by ingest_knowledge_source."""
    return {
        "source_name": source_name,
        "type": source_type,
        "path": path,
        "chunks_indexed": chunks_indexed,
        "status": "ready",
    }


def make_knowledge_query_result(
    query: str = "patient identifier",
    results: list[dict] | None = None,
) -> dict:
    """Sample query result with scored matches."""
    if results is None:
        results = [
            {
                "source": "glossary",
                "text": '{"patient_id": "A unique identifier assigned to each patient"}',
                "score": 0.8721,
            },
            {
                "source": "data_dictionary",
                "text": "## Patient ID\nPrimary key for patient records, UUID v4.",
                "score": 0.7543,
            },
            {
                "source": "glossary",
                "text": '{"mrn": "Medical Record Number — facility-specific patient identifier"}',
                "score": 0.6912,
            },
        ]
    return {
        "query": query,
        "results": results,
        "result_count": len(results),
    }
