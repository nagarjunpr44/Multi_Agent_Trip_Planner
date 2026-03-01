from __future__ import annotations

import json
from typing import Optional

from memory.chroma_store import TripMemoryStore
from memory.embeddings import doc_id_from_text, embed_text


class ContextManager:
    """Manages retrieval and persistence of user travel context via ChromaDB."""

    def __init__(self) -> None:
        self._store = TripMemoryStore()

    async def load_user_context(
        self,
        user_query: str,
        user_id: Optional[str] = None,
        n_results: int = 3,
    ) -> dict:
        """
        Retrieve relevant past trip memories for this query.
        Returns a dict with 'past_trips' and 'preferences' keys.
        """
        try:
            embedding = await embed_text(user_query)
            where = {"user_id": user_id} if user_id else None
            results = await self._store.query(embedding, n_results=n_results, where=where)
            past_trips = [r["document"] for r in results if r["distance"] < 0.6]
            return {"past_trips": past_trips, "preferences": {}}
        except Exception:
            # Non-fatal: return empty context if ChromaDB is unavailable
            return {"past_trips": [], "preferences": {}}

    async def save_trip_summary(
        self,
        session_id: str,
        summary: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Persist a trip summary to ChromaDB for future retrieval."""
        try:
            embedding = await embed_text(summary)
            doc_id = doc_id_from_text(f"{session_id}:{summary[:64]}")
            await self._store.upsert(
                doc_id=doc_id,
                document=summary,
                embedding=embedding,
                metadata=metadata or {},
            )
        except Exception:
            pass  # Non-fatal
