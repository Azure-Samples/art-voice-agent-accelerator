"""
Knowledge Base & RAG Search Tools
==================================

Vector search and knowledge retrieval tools for agent use.
Integrates with Cosmos DB for vector search (RAG pattern).
"""

from __future__ import annotations

from typing import Any

from apps.artagent.backend.registries.toolstore.registry import register_tool
from utils.ml_logging import get_logger

logger = get_logger("agents.tools.knowledge_base")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

search_knowledge_base_schema: dict[str, Any] = {
    "name": "search_knowledge_base",
    "description": (
        "Search the knowledge base for relevant information using semantic search. "
        "Use this to find documentation, FAQs, policies, or product information."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query",
            },
            "collection": {
                "type": "string",
                "enum": ["general", "products", "policies", "faq"],
                "description": "Knowledge base collection to search",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (1-10)",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# RAG RETRIEVER WRAPPER
# ═══════════════════════════════════════════════════════════════════════════════

_retriever_cache: dict[str, Any] = {}


def _get_retriever(collection: str = "general"):
    """Get or create a cached Cosmos vector retriever."""
    cache_key = collection

    if cache_key in _retriever_cache:
        return _retriever_cache[cache_key]

    try:
        # Import the shared RAG retrieval module
        from apps.artagent.backend.src.agents.shared.rag_retrieval import (
            CosmosVectorRetriever,
        )

        retriever = CosmosVectorRetriever.from_env(
            collection=collection,
            appname="unified-agents",
        )
        _retriever_cache[cache_key] = retriever
        return retriever

    except ImportError:
        logger.warning("RAG retrieval module not available - using mock search")
        return None
    except Exception as e:
        logger.warning("Failed to initialize Cosmos retriever: %s", e)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# MOCK KNOWLEDGE BASE (fallback when Cosmos not available)
# ═══════════════════════════════════════════════════════════════════════════════

_MOCK_KB = {
    "general": [
        {
            "title": "Account Security",
            "content": "Always protect your account credentials. Never share your password or MFA codes.",
            "url": "https://docs.example.com/security",
        },
        {
            "title": "Contact Support",
            "content": "For urgent issues, call our 24/7 support line. For general inquiries, use chat or email.",
            "url": "https://docs.example.com/support",
        },
    ],
    "products": [
        {
            "title": "Preferred Rewards Credit Card",
            "content": "Earn 3% cash back on travel and dining, 2% on groceries, 1% on everything else. No annual fee.",
            "url": "https://docs.example.com/cards/preferred",
        },
        {
            "title": "Premium Travel Card",
            "content": "Unlimited lounge access, 5x points on travel, $300 annual travel credit. $550 annual fee.",
            "url": "https://docs.example.com/cards/premium",
        },
    ],
    "policies": [
        {
            "title": "Fraud Protection Policy",
            "content": "Zero liability for unauthorized transactions reported within 60 days.",
            "url": "https://docs.example.com/policies/fraud",
        },
        {
            "title": "Fee Refund Policy",
            "content": "First-time courtesy refund available for most fees. Premium members get unlimited refunds.",
            "url": "https://docs.example.com/policies/fees",
        },
    ],
    "faq": [
        {
            "title": "How do I set up direct deposit?",
            "content": "Get your routing and account numbers from Account Settings, then provide them to your employer's HR.",
            "url": "https://docs.example.com/faq/direct-deposit",
        },
        {
            "title": "How do I report a lost card?",
            "content": "Call our 24/7 line or use the app to immediately lock your card and order a replacement.",
            "url": "https://docs.example.com/faq/lost-card",
        },
    ],
}


def _mock_search(query: str, collection: str, top_k: int) -> list[dict[str, Any]]:
    """Simple keyword-based mock search for when Cosmos is unavailable."""
    query_lower = query.lower()
    results = []

    docs = _MOCK_KB.get(collection, _MOCK_KB["general"])

    for doc in docs:
        # Simple relevance scoring based on keyword matches
        score = 0.0
        title_lower = doc["title"].lower()
        content_lower = doc["content"].lower()

        for word in query_lower.split():
            if word in title_lower:
                score += 0.3
            if word in content_lower:
                score += 0.1

        if score > 0:
            results.append(
                {
                    "title": doc["title"],
                    "content": doc["content"],
                    "url": doc["url"],
                    "score": min(score, 1.0),
                }
            )

    # Sort by score and limit
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTORS
# ═══════════════════════════════════════════════════════════════════════════════


async def search_knowledge_base(args: dict[str, Any]) -> dict[str, Any]:
    """Search the knowledge base for relevant information."""
    query = (args.get("query") or "").strip()
    collection = (args.get("collection") or "general").strip()
    top_k = min(max(int(args.get("top_k", 5)), 1), 10)

    if not query:
        return {
            "success": False,
            "message": "Query is required for knowledge base search.",
            "results": [],
        }

    logger.info("🔍 Searching knowledge base: '%s' in %s", query[:50], collection)

    # Try Cosmos vector search first
    retriever = _get_retriever(collection)

    if retriever:
        try:

            results = retriever.search(query, top_k=top_k)

            formatted_results = []
            for r in results:
                formatted_results.append(
                    {
                        "title": r.url.split("/")[-1] if r.url else "Document",
                        "content": r.content[:500] if r.content else "",
                        "snippet": r.snippet,
                        "url": r.url,
                        "score": r.score,
                        "doc_type": r.doc_type,
                    }
                )

            logger.info("✓ Found %d results from Cosmos vector search", len(formatted_results))

            return {
                "success": True,
                "message": f"Found {len(formatted_results)} relevant results.",
                "results": formatted_results,
                "source": "cosmos_vector",
            }

        except Exception as e:
            logger.warning("Cosmos search failed, falling back to mock: %s", e)

    # Fallback to mock search
    results = _mock_search(query, collection, top_k)

    logger.info("✓ Found %d results from mock search", len(results))

    return {
        "success": True,
        "message": f"Found {len(results)} relevant results.",
        "results": results,
        "source": "mock",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    "search_knowledge_base",
    search_knowledge_base_schema,
    search_knowledge_base,
    tags={"knowledge_base", "search", "rag"},
)
