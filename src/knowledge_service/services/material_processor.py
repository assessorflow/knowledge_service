"""Shared ProcessMaterial business logic for REST and gRPC (H-5 + C-3 fix).

Handles: sanitize -> chunk -> embed -> deduplicate -> store (transactionally).
"""

from __future__ import annotations

from typing import Any

import structlog

from knowledge_service.db.pool import get_pool
from knowledge_service.db import repository as repo
from knowledge_service.services import chunking, embedding
from knowledge_service.services.embedding import EmbeddingError

logger = structlog.get_logger(__name__)

EMBED_BATCH_SIZE = 20


async def process_material(
    workflow_id: str,
    content_text: str,
    source_type: str,
    source_file: str = "",
    source_url: str = "",
    assessor_id: str | None = None,
    assessment_id: str | None = None,
) -> dict[str, Any]:
    """Process material text: sanitize, chunk, embed, store transactionally.

    Routes to correct KB table based on source_type:
    - "direct_text" / "ocr_extracted" -> document_chunks
    - "rubric" -> policy_chunks (requires assessment_id)
    - "web_research" -> enriched_chunks

    Raises EmbeddingError if embedding fails (C-2: never stores zero vectors).
    All DB inserts are wrapped in a transaction (C-3: all-or-nothing).
    """
    # Sanitize text
    clean_text = content_text.replace("\x00", "")

    # Chunk
    chunks = chunking.split_text_into_chunks(clean_text)
    if not chunks:
        return {"chunks_created": 0, "status": "success"}

    chunks = [c.replace("\x00", "") for c in chunks]

    # Compute file hash for dedup
    file_hash = chunking.compute_file_hash(clean_text)

    # Embed in batches — fails fast on error (C-2)
    embeddings: list[list[float]] = []
    for batch_start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[batch_start:batch_start + EMBED_BATCH_SIZE]
        batch_embeddings = await embedding.embed_texts(batch)
        embeddings.extend(batch_embeddings)

    # Store transactionally (C-3)
    pool = await get_pool()
    created = 0

    async with pool.acquire() as conn:
        async with conn.transaction():
            for i, (chunk_text, emb) in enumerate(zip(chunks, embeddings)):
                content_hash = chunking.compute_content_hash(chunk_text)
                token_count = len(chunk_text) // 4

                if source_type in ("direct_text", "ocr_extracted"):
                    # Dedup check
                    dup = await conn.fetchrow(
                        "SELECT 1 FROM document_chunks WHERE workflow_id = $1 AND content_hash = $2 LIMIT 1",
                        workflow_id, content_hash,
                    )
                    if dup:
                        continue

                    await conn.execute(
                        """
                        INSERT INTO document_chunks
                            (workflow_id, content, embedding, chunk_index, source_type,
                             source_file, file_hash, content_hash, assessor_id, token_count, metadata)
                        VALUES ($1, $2, $3::vector, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
                        """,
                        workflow_id, chunk_text, _vec_literal(emb), i, source_type,
                        source_file, file_hash, content_hash,
                        repo._to_uuid(assessor_id), token_count,
                        repo._jsonb({"source_file": source_file} if source_file else None),
                    )

                elif source_type == "rubric":
                    await conn.execute(
                        """
                        INSERT INTO policy_chunks
                            (content, embedding, policy_type, assessment_id, source, chunk_index, metadata)
                        VALUES ($1, $2::vector, $3, $4, $5, $6, $7::jsonb)
                        """,
                        chunk_text, _vec_literal(emb), "rubric",
                        repo._to_uuid(assessment_id), "assessor_rubric", i,
                        repo._jsonb({"source_file": source_file} if source_file else None),
                    )

                elif source_type == "web_research":
                    await conn.execute(
                        """
                        INSERT INTO enriched_chunks
                            (workflow_id, content, embedding, source_url, source_type, assessor_id, metadata)
                        VALUES ($1, $2, $3::vector, $4, $5, $6, $7::jsonb)
                        """,
                        workflow_id, chunk_text, _vec_literal(emb),
                        source_url, "web_text", repo._to_uuid(assessor_id),
                        repo._jsonb({"source_file": source_file} if source_file else None),
                    )

                created += 1

    logger.info(
        "process_material_done",
        workflow_id=workflow_id,
        source_type=source_type,
        total_chunks=len(chunks),
        created=created,
        deduped=len(chunks) - created,
    )

    return {"chunks_created": created, "status": "success"}


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vec) + "]"
