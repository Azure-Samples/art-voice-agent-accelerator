"""
RAG Retrieval Utilities (Cosmos-backed)
---------------------------------------

Lightweight placeholder that mirrors the staging RAG retrieval API without
pulling in legacy vlagent/artagent dependencies. If Cosmos configuration is
missing, the retriever will simply return no results, allowing callers to
fall back to their own mock logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from utils.ml_logging import get_logger

logger = get_logger("agents.shared.rag_retrieval")


@dataclass
class RetrievalResult:
    content: str
    snippet: str | None = None
    url: str | None = None
    score: float = 0.0
    doc_type: str | None = None


class CosmosVectorRetriever:
    """Thin stub for Cosmos vector retrieval."""

    def __init__(
        self,
        *,
        collection: str,
        appname: str = "unified-agents",
    ) -> None:
        self.collection = collection
        self.appname = appname
        self.endpoint = os.getenv("AZURE_COSMOS_ENDPOINT")
        self.key = os.getenv("AZURE_COSMOS_KEY")
        self.database = os.getenv("AZURE_COSMOS_DATABASE_NAME")
        self.container = os.getenv("AZURE_COSMOS_USERS_COLLECTION_NAME")
        if not all([self.endpoint, self.key, self.database, self.container]):
            logger.info(
                "Cosmos RAG retriever not fully configured; falling back to empty results",
                extra={"collection": collection, "app": appname},
            )

    @classmethod
    def from_env(cls, *, collection: str, appname: str = "unified-agents") -> CosmosVectorRetriever:
        """Create retriever using environment configuration."""
        return cls(collection=collection, appname=appname)

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievalResult]:
        """
        Execute a vector search. Returns an empty list if not configured.

        This stub preserves the interface expected by knowledge_base tools
        while avoiding dependency on legacy implementations.
        """
        if not all([self.endpoint, self.key, self.database, self.container]):
            return []

        logger.warning(
            "Cosmos vector search not implemented in this stub; returning empty results",
            extra={"collection": self.collection, "app": self.appname},
        )
        return []


__all__ = ["CosmosVectorRetriever", "RetrievalResult"]
