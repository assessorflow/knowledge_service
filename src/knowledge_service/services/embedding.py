"""Embedding service.

Supports two providers via EMBEDDING_PROVIDER env var:
- "openai"        → Direct OpenAI API (text-embedding-3-small). For testing now.
- "model_broker"  → Model Broker service (production, Invariant #6). Switch when ready.
"""

from __future__ import annotations

import structlog
import httpx

from knowledge_service import config

logger = structlog.get_logger(__name__)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts. Routes to provider based on config."""
    if not texts:
        return []

    if config.EMBEDDING_PROVIDER == "openai":
        return await _embed_openai(texts)
    elif config.EMBEDDING_PROVIDER == "model_broker":
        return await _embed_model_broker(texts)
    else:
        logger.warning("unknown_embedding_provider", provider=config.EMBEDDING_PROVIDER)
        return [[0.0] * config.EMBEDDING_DIMENSION for _ in texts]


async def embed_single(text: str) -> list[float]:
    """Embed a single text string."""
    results = await embed_texts([text])
    return results[0] if results else [0.0] * config.EMBEDDING_DIMENSION


# ---------------------------------------------------------------------------
# OpenAI provider (for testing — switch to Model Broker when ready)
# ---------------------------------------------------------------------------

async def _embed_openai(texts: list[str]) -> list[list[float]]:
    if not config.OPENAI_API_KEY:
        logger.error("openai_api_key_missing")
        return [[0.0] * config.EMBEDDING_DIMENSION for _ in texts]

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                json={
                    "model": config.OPENAI_EMBEDDING_MODEL,
                    "input": texts,
                },
            )
            response.raise_for_status()
            data = response.json()
            embeddings = [item["embedding"] for item in data["data"]]
            logger.info(
                "openai_embedding_success",
                count=len(embeddings),
                model=config.OPENAI_EMBEDDING_MODEL,
            )
            return embeddings
    except Exception as exc:
        logger.error("openai_embedding_failed", error=str(exc))
        return [[0.0] * config.EMBEDDING_DIMENSION for _ in texts]


# ---------------------------------------------------------------------------
# Model Broker provider (production)
# ---------------------------------------------------------------------------

async def _embed_model_broker(texts: list[str]) -> list[list[float]]:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{config.MODEL_BROKER_URL}/api/v1/embed",
                json={"texts": texts},
            )
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("embeddings", [])
            logger.info("model_broker_embedding_success", count=len(embeddings))
            return embeddings
    except Exception as exc:
        logger.warning("model_broker_embedding_failed", error=str(exc))
        return [[0.0] * config.EMBEDDING_DIMENSION for _ in texts]
