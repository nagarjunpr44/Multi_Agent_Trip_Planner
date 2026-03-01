from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Optional

from langchain_openai import OpenAIEmbeddings

from config.settings import get_settings


@lru_cache(maxsize=1)
def _get_embedder() -> OpenAIEmbeddings:
    s = get_settings()
    return OpenAIEmbeddings(
        model="text-embedding-3-small",
        openai_api_key=s.llm.openai_api_key,
    )


async def embed_text(text: str) -> list[float]:
    """Embed a single text string asynchronously."""
    embedder = _get_embedder()
    return await embedder.aembed_query(text)


async def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed multiple documents asynchronously."""
    embedder = _get_embedder()
    return await embedder.aembed_documents(texts)


def doc_id_from_text(text: str) -> str:
    """Deterministic ID from text content (SHA-256 prefix)."""
    return hashlib.sha256(text.encode()).hexdigest()[:32]
