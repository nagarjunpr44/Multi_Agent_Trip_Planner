from __future__ import annotations

from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaClientSettings

from config.settings import get_settings

_client = None


async def get_chroma_client():
    global _client
    if _client is None:
        s = get_settings().chroma
        if s.chroma_host in ("embedded", "local", ""):
            # In-process persistent store — no server required
            import os
            persist_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chromadb")
            os.makedirs(persist_dir, exist_ok=True)
            _client = await chromadb.AsyncEphemeralClient(
                settings=ChromaClientSettings(anonymized_telemetry=False),
            )
        else:
            _client = await chromadb.AsyncHttpClient(
                host=s.chroma_host,
                port=s.chroma_port,
                settings=ChromaClientSettings(anonymized_telemetry=False),
            )
    return _client


class TripMemoryStore:
    """ChromaDB-backed store for user travel preferences and past trip summaries."""

    def __init__(self) -> None:
        self._settings = get_settings().chroma
        self._collection_name = self._settings.chroma_collection_trip_memory
        self._collection = None

    async def _get_collection(self):
        if self._collection is None:
            client = await get_chroma_client()
            self._collection = await client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    async def upsert(
        self,
        doc_id: str,
        document: str,
        embedding: list[float],
        metadata: Optional[dict] = None,
    ) -> None:
        collection = await self._get_collection()
        await collection.upsert(
            ids=[doc_id],
            documents=[document],
            embeddings=[embedding],
            metadatas=[metadata or {}],
        )

    async def query(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> list[dict]:
        collection = await self._get_collection()
        results = await collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        items = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            items.append({"document": doc, "metadata": meta, "distance": dist})
        return items

    async def delete(self, doc_id: str) -> None:
        collection = await self._get_collection()
        await collection.delete(ids=[doc_id])
