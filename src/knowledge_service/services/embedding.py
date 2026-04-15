"""Embedding service.

Supports two providers via EMBEDDING_PROVIDER env var:
- "openai"        -> Direct OpenAI API (text-embedding-3-small). For testing now.
- "model_broker"  -> Model Broker service (production, Invariant #6). Switch when ready.

IMPORTANT: Fails fast on error — never returns zero vectors (C-2 fix).
Zero vectors corrupt the vector store and poison all similarity searches.
"""

from __future__ import annotations

import structlog
import httpx

from knowledge_service import config

logger = structlog.get_logger(__name__)


class EmbeddingError(Exception):
    """Raised when embedding generation fails. Caller should NOT store chunks."""
    pass


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts. Routes to provider based on config.

    Raises EmbeddingError on failure — never returns zero vectors.
    """
    if not texts:
        return []

    if config.EMBEDDING_PROVIDER == "openai":
        return await _embed_openai(texts)
    elif config.EMBEDDING_PROVIDER == "model_broker":
        return await _embed_model_broker(texts)
    else:
        raise EmbeddingError(f"Unknown embedding provider: {config.EMBEDDING_PROVIDER}")


async def embed_single(text: str) -> list[float]:
    """Embed a single text string. Raises EmbeddingError on failure."""
    results = await embed_texts([text])
    if not results:
        raise EmbeddingError("Embedding returned empty result")
    return results[0]


async def _embed_openai(texts: list[str]) -> list[list[float]]:
    if not config.OPENAI_API_KEY:
        raise EmbeddingError("OPENAI_API_KEY not configured")

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
    except httpx.HTTPStatusError as exc:
        raise EmbeddingError(f"OpenAI API error {exc.response.status_code}: {exc.response.text}")
    except Exception as exc:
        raise EmbeddingError(f"OpenAI embedding failed: {exc}")


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
            if not embeddings:
                raise EmbeddingError("Model Broker returned empty embeddings")
            logger.info("model_broker_embedding_success", count=len(embeddings))
            return embeddings
    except httpx.HTTPStatusError as exc:
        raise EmbeddingError(f"Model Broker API error {exc.response.status_code}: {exc.response.text}")
    except EmbeddingError:
        raise
    except Exception as exc:
        raise EmbeddingError(f"Model Broker embedding failed: {exc}")
