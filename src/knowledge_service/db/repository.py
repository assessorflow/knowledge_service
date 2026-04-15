"""Database repository for af_knowledge tables.

All SQL queries for topics, document_chunks, policy_chunks, enriched_chunks.
Columns match vector_schema.md (source of truth).
"""

from __future__ import annotations

import json
import math
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from knowledge_service.db.pool import get_pool

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# document_chunks
# ---------------------------------------------------------------------------

async def insert_document_chunk(
    workflow_id: str,
    content: str,
    embedding: list[float],
    chunk_index: int,
    source_type: str = "direct_text",
    source_file: str = "",
    source_page: int | None = None,
    file_hash: str | None = None,
    content_hash: str | None = None,
    assessor_id: str | None = None,
    token_count: int | None = None,
    metadata: dict | None = None,
) -> str:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO document_chunks
            (workflow_id, content, embedding, chunk_index, source_type,
             source_file, source_page, file_hash, content_hash,
             assessor_id, token_count, metadata)
        VALUES ($1, $2, $3::vector, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb)
        RETURNING id
        """,
        workflow_id,
        content,
        _vec_literal(embedding),
        chunk_index,
        source_type,
        source_file,
        source_page,
        file_hash,
        content_hash,
        UUID(assessor_id) if assessor_id else None,
        token_count,
        _jsonb(metadata),
    )
    return str(row["id"])


async def check_duplicate_chunk(
    workflow_id: str, content_hash: str
) -> bool:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT 1 FROM document_chunks
        WHERE workflow_id = $1 AND content_hash = $2
        LIMIT 1
        """,
        workflow_id,
        content_hash,
    )
    return row is not None


async def get_chunks_by_workflow(workflow_id: str) -> list[dict[str, Any]]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, workflow_id, content, source_type, source_file,
               chunk_index, token_count, metadata
        FROM document_chunks
        WHERE workflow_id = $1
        ORDER BY chunk_index
        """,
        workflow_id,
    )
    return [_row_to_chunk(r) for r in rows]


async def get_chunks_by_ids(chunk_ids: list[str]) -> list[dict[str, Any]]:
    if not chunk_ids:
        return []
    pool = await get_pool()
    uuids = [UUID(cid) for cid in chunk_ids]
    rows = await pool.fetch(
        """
        SELECT id, workflow_id, content, source_type, source_file,
               chunk_index, token_count, metadata
        FROM document_chunks
        WHERE id = ANY($1::uuid[])
        """,
        uuids,
    )
    return [_row_to_chunk(r) for r in rows]


async def similarity_search_documents(
    query_embedding: list[float],
    workflow_id: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, workflow_id, content, source_type, source_file,
               metadata, 1 - (embedding <=> $1::vector) AS score
        FROM document_chunks
        WHERE workflow_id = $2
        ORDER BY embedding <=> $1::vector
        LIMIT $3
        """,
        _vec_literal(query_embedding),
        workflow_id,
        top_k,
    )
    return [_row_to_chunk(r, score=True) for r in rows]


# ---------------------------------------------------------------------------
# policy_chunks
# ---------------------------------------------------------------------------

async def insert_policy_chunk(
    content: str,
    embedding: list[float],
    policy_type: str = "rubric",
    assessment_id: str | None = None,
    workflow_id: str | None = None,
    chunk_index: int = 0,
    source: str | None = None,
    assessor_id: str | None = None,
    metadata: dict | None = None,
) -> str:
    # Derive source if not provided
    if source is None:
        source = "assessor_rubric" if assessment_id else "system_default"

    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO policy_chunks
            (content, embedding, policy_type, assessment_id, workflow_id,
             chunk_index, source, assessor_id, metadata)
        VALUES ($1, $2::vector, $3, $4, $5, $6, $7, $8, $9::jsonb)
        RETURNING id
        """,
        content,
        _vec_literal(embedding),
        policy_type,
        UUID(assessment_id) if assessment_id else None,
        workflow_id,
        chunk_index,
        source,
        UUID(assessor_id) if assessor_id else None,
        _jsonb(metadata),
    )
    return str(row["id"])


async def similarity_search_policies(
    query_embedding: list[float],
    assessment_id: str | None = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    pool = await get_pool()
    if assessment_id:
        # Search both system defaults (assessment_id IS NULL) and
        # assessment-specific rubrics
        rows = await pool.fetch(
            """
            SELECT id, assessment_id, workflow_id, content, policy_type,
                   source, metadata, 1 - (embedding <=> $1::vector) AS score
            FROM policy_chunks
            WHERE assessment_id IS NULL OR assessment_id = $2
            ORDER BY embedding <=> $1::vector
            LIMIT $3
            """,
            _vec_literal(query_embedding),
            UUID(assessment_id),
            top_k,
        )
    else:
        # System defaults only
        rows = await pool.fetch(
            """
            SELECT id, assessment_id, workflow_id, content, policy_type,
                   source, metadata, 1 - (embedding <=> $1::vector) AS score
            FROM policy_chunks
            WHERE assessment_id IS NULL
            ORDER BY embedding <=> $1::vector
            LIMIT $2
            """,
            _vec_literal(query_embedding),
            top_k,
        )
    return [_row_to_policy_chunk(r) for r in rows]


# ---------------------------------------------------------------------------
# enriched_chunks
# ---------------------------------------------------------------------------

async def insert_enriched_chunk(
    workflow_id: str,
    content: str,
    embedding: list[float],
    source_url: str = "",
    source_type: str = "web_text",
    chunk_index: int = 0,
    assessor_id: str | None = None,
    topic_id: str | None = None,
    metadata: dict | None = None,
) -> str:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO enriched_chunks
            (workflow_id, content, embedding, source_url, source_type,
             chunk_index, assessor_id, topic_id, retrieved_at, metadata)
        VALUES ($1, $2, $3::vector, $4, $5, $6, $7, $8, now(), $9::jsonb)
        RETURNING id
        """,
        workflow_id,
        content,
        _vec_literal(embedding),
        source_url,
        source_type,
        chunk_index,
        UUID(assessor_id) if assessor_id else None,
        UUID(topic_id) if topic_id else None,
        _jsonb(metadata),
    )
    return str(row["id"])


async def similarity_search_enriched(
    query_embedding: list[float],
    workflow_id: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, workflow_id, content, source_type, source_url,
               metadata, 1 - (embedding <=> $1::vector) AS score
        FROM enriched_chunks
        WHERE workflow_id = $2
        ORDER BY embedding <=> $1::vector
        LIMIT $3
        """,
        _vec_literal(query_embedding),
        workflow_id,
        top_k,
    )
    return [_row_to_enriched_chunk(r) for r in rows]


# ---------------------------------------------------------------------------
# topics
# ---------------------------------------------------------------------------

async def insert_topic(
    workflow_id: str,
    name: str,
    parent_id: str | None = None,
    assessor_id: str | None = None,
) -> str:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO topics (workflow_id, name, parent_id, assessor_id)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        workflow_id,
        name,
        UUID(parent_id) if parent_id else None,
        UUID(assessor_id) if assessor_id else None,
    )
    return str(row["id"])


async def get_topics_by_workflow(workflow_id: str) -> list[dict[str, Any]]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, workflow_id, parent_id, name, created_at
        FROM topics
        WHERE workflow_id = $1
        ORDER BY created_at
        """,
        workflow_id,
    )
    return [
        {
            "topic_id": str(r["id"]),
            "workflow_id": r["workflow_id"],
            "parent_id": str(r["parent_id"]) if r["parent_id"] else None,
            "name": r["name"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vec_literal(vec: list[float]) -> str:
    """Convert a Python list to pgvector literal string."""
    return "[" + ",".join(str(v) for v in vec) + "]"


def _safe_score(value) -> float:
    """Convert score to float, replacing NaN/None with 0.0."""
    if value is None:
        return 0.0
    f = float(value)
    return 0.0 if math.isnan(f) else f


def _jsonb(data: dict | None) -> str | None:
    if data is None:
        return None
    return json.dumps(data)


def _to_uuid(value: str | None):
    """Convert string to UUID, or None if empty."""
    return UUID(value) if value else None


def _row_to_chunk(row: asyncpg.Record, score: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "chunk_id": str(row["id"]),
        "workflow_id": row["workflow_id"],
        "content": row["content"],
        "source_type": row.get("source_type", "direct_text"),
        "metadata": row.get("metadata") or {},
    }
    if score and "score" in row.keys():
        result["score"] = _safe_score(row["score"])
    return result


def _row_to_policy_chunk(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "chunk_id": str(row["id"]),
        "workflow_id": row.get("workflow_id") or "",
        "content": row["content"],
        "source_type": row.get("policy_type", "rubric"),
        "source": row.get("source", "system_default"),
        "metadata": row.get("metadata") or {},
        "score": _safe_score(row["score"]) if "score" in row.keys() else None,
    }


def _row_to_enriched_chunk(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "chunk_id": str(row["id"]),
        "workflow_id": row["workflow_id"],
        "content": row["content"],
        "source_type": row.get("source_type", "web_text"),
        "source_url": row.get("source_url", ""),
        "metadata": row.get("metadata") or {},
        "score": _safe_score(row["score"]) if "score" in row.keys() else None,
    }
