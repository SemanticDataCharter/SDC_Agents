"""Knowledge toolset — ingest and query customer contextual resources.

Indexes data dictionaries, glossaries, ontologies, and other text-based
resources into a local Chroma vector store for semantic context matching.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from google.adk.tools import FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.cache import CacheManager
from sdc_agents.common.config import SDCAgentsConfig

try:
    import chromadb
except ImportError:
    chromadb = None  # type: ignore[assignment]

try:
    import pymupdf
except ImportError:
    pymupdf = None  # type: ignore[assignment]

try:
    import docx as python_docx
except ImportError:
    python_docx = None  # type: ignore[assignment]


class KnowledgeToolset(BaseToolset):
    """Toolset for ingesting and querying customer knowledge sources."""

    def __init__(
        self,
        config: SDCAgentsConfig,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._config = config
        self._cache = CacheManager(config.cache.root)
        self._cache.ensure_dirs()
        self._audit = AuditLogger(config.audit.path, config.audit.log_level)
        self._knowledge_config = config.knowledge

    async def get_tools(self) -> list[FunctionTool]:
        return [
            FunctionTool(self.ingest_knowledge_source),
            FunctionTool(self.query_knowledge),
            FunctionTool(self.list_indexed_sources),
        ]

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """Split text into overlapping chunks."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start = end - overlap
        return [c.strip() for c in chunks if c.strip()]

    def _read_source(self, source_path: str, source_type: str) -> list[str]:
        """Read a source file and return text chunks for indexing."""
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"Knowledge source not found: {source_path}")

        # Binary formats — must be handled before read_text()
        if source_type == "pdf":
            if pymupdf is None:
                raise ImportError(
                    "pymupdf is required for PDF knowledge sources. "
                    "Install it with: pip install sdc-agents[knowledge]"
                )
            doc = pymupdf.open(source_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return self._chunk_text(text)

        if source_type == "docx":
            if python_docx is None:
                raise ImportError(
                    "python-docx is required for DOCX knowledge sources. "
                    "Install it with: pip install sdc-agents[knowledge]"
                )
            doc = python_docx.Document(source_path)
            text = "\n\n".join(para.text for para in doc.paragraphs if para.text.strip())
            return self._chunk_text(text)

        content = path.read_text(encoding="utf-8")

        if source_type == "csv":
            # Each row as a chunk
            lines = content.strip().splitlines()
            if len(lines) <= 1:
                return lines
            header = lines[0]
            return [f"{header}\n{line}" for line in lines[1:] if line.strip()]

        if source_type == "json":
            data = json.loads(content)
            if isinstance(data, list):
                return [json.dumps(record, ensure_ascii=False) for record in data]
            if isinstance(data, dict):
                # Flatten dict entries as individual chunks
                return [json.dumps({k: v}, ensure_ascii=False) for k, v in data.items()]
            return [content]

        if source_type == "ttl":
            # Chunk Turtle text by paragraphs (double newlines)
            paragraphs = content.split("\n\n")
            chunks = []
            for para in paragraphs:
                para = para.strip()
                if para:
                    chunks.extend(self._chunk_text(para))
            return chunks if chunks else [content]

        # markdown and txt — chunk by text segments
        return self._chunk_text(content)

    async def ingest_knowledge_source(self, source_name: str, force_refresh: bool = False) -> dict:
        """Ingest a configured knowledge source into the vector store.

        Args:
            source_name: Name of the source defined in config.knowledge.sources.
            force_refresh: If True, re-index even if already cached.

        Returns:
            Dict with source_name, type, path, chunks_indexed, and status.
        """
        import time

        start_time = time.monotonic()

        if source_name not in self._knowledge_config.sources:
            raise KeyError(
                f"Unknown knowledge source '{source_name}'. "
                f"Configured: {', '.join(self._knowledge_config.sources.keys()) or '(none)'}"
            )

        source = self._knowledge_config.sources[source_name]
        meta_path = self._cache.knowledge_path(source_name)

        # Check if already indexed
        if not force_refresh and self._cache.is_cached(meta_path):
            metadata = json.loads(meta_path.read_text())
            self._audit.log(
                agent="knowledge",
                tool="ingest_knowledge_source",
                inputs={"source_name": source_name, "force_refresh": force_refresh},
                outputs=metadata,
                start_time=start_time,
            )
            return metadata

        # Read and chunk source
        chunks = self._read_source(source.path, source.type)

        # Index into Chroma
        if chromadb is None:
            raise ImportError(
                "chromadb is required for the Knowledge Agent. "
                "Install it with: pip install sdc-agents[knowledge]"
            )

        persist_dir = self._knowledge_config.vector_store_path
        client = await asyncio.to_thread(
            chromadb.PersistentClient,
            path=persist_dir,
        )

        collection = await asyncio.to_thread(
            client.get_or_create_collection,
            name="sdc-knowledge",
        )

        # Delete existing documents for this source if refreshing
        if force_refresh:
            existing = await asyncio.to_thread(
                collection.get,
                where={"source": source_name},
            )
            if existing["ids"]:
                await asyncio.to_thread(
                    collection.delete,
                    ids=existing["ids"],
                )

        # Add chunks with metadata
        ids = [f"{source_name}_{i}" for i in range(len(chunks))]
        metadatas = [{"source": source_name, "type": source.type} for _ in chunks]

        await asyncio.to_thread(
            collection.add,
            ids=ids,
            documents=chunks,
            metadatas=metadatas,
        )

        result = {
            "source_name": source_name,
            "type": source.type,
            "path": source.path,
            "chunks_indexed": len(chunks),
            "status": "ready",
        }

        # Cache metadata
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(result, indent=2))

        self._audit.log(
            agent="knowledge",
            tool="ingest_knowledge_source",
            inputs={"source_name": source_name, "force_refresh": force_refresh},
            outputs=result,
            start_time=start_time,
        )
        return result

    async def query_knowledge(self, query_text: str, limit: int = 5) -> dict:
        """Query the knowledge vector store for relevant context.

        Args:
            query_text: Natural language query to search for.
            limit: Maximum number of results to return.

        Returns:
            Dict with query, results list (source, text, score), and result_count.
        """
        import time

        start_time = time.monotonic()

        if chromadb is None:
            raise ImportError(
                "chromadb is required for the Knowledge Agent. "
                "Install it with: pip install sdc-agents[knowledge]"
            )

        persist_dir = self._knowledge_config.vector_store_path
        client = await asyncio.to_thread(
            chromadb.PersistentClient,
            path=persist_dir,
        )

        collection = await asyncio.to_thread(
            client.get_or_create_collection,
            name="sdc-knowledge",
        )

        query_result = await asyncio.to_thread(
            collection.query,
            query_texts=[query_text],
            n_results=limit,
        )

        results = []
        if query_result["documents"] and query_result["documents"][0]:
            docs = query_result["documents"][0]
            metadatas = query_result["metadatas"][0] if query_result["metadatas"] else []
            distances = query_result["distances"][0] if query_result["distances"] else []

            for i, doc in enumerate(docs):
                source = metadatas[i].get("source", "unknown") if i < len(metadatas) else "unknown"
                score = round(1.0 - distances[i], 4) if i < len(distances) else 0.0
                results.append({"source": source, "text": doc, "score": score})

        output = {
            "query": query_text,
            "results": results,
            "result_count": len(results),
        }

        self._audit.log(
            agent="knowledge",
            tool="query_knowledge",
            inputs={"query_text": query_text, "limit": limit},
            outputs=output,
            start_time=start_time,
        )
        return output

    async def list_indexed_sources(self) -> list[dict]:
        """List all indexed knowledge sources from cache metadata.

        Returns:
            List of dicts with source_name, type, chunks_indexed, and status.
        """
        import time

        start_time = time.monotonic()

        knowledge_dir = self._cache.root / "knowledge"
        sources = []
        if knowledge_dir.exists():
            for meta_file in sorted(knowledge_dir.glob("*.json")):
                try:
                    metadata = json.loads(meta_file.read_text())
                    sources.append(
                        {
                            "source_name": metadata.get("source_name", meta_file.stem),
                            "type": metadata.get("type", "unknown"),
                            "chunks_indexed": metadata.get("chunks_indexed", 0),
                            "status": metadata.get("status", "unknown"),
                        }
                    )
                except (json.JSONDecodeError, KeyError):
                    continue

        self._audit.log(
            agent="knowledge",
            tool="list_indexed_sources",
            inputs={},
            outputs={"count": len(sources)},
            start_time=start_time,
        )
        return sources
