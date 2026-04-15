"""Internal API routes — called by agents via HTTP (future: gRPC).

8 endpoints matching KnowledgeServicePort + admin policy endpoint.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import structlog

from knowledge_service.db import repository as repo
from knowledge_service.services import chunking, embedding

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ProcessMaterialRequest(BaseModel):
    workflow_id: str
    content_text: str
    source_type: str = "direct_text"  # "direct_text" | "ocr_extracted" → document_chunks
                                       # "rubric" → policy_chunks
                                       # "web_research" → enriched_chunks
    source_file: str = ""
    source_url: str = ""              # For web research content
    assessor_id: str | None = None
    assessment_id: str | None = None  # Required for rubric storage


class ProcessMaterialResponse(BaseModel):
    chunks_created: int
    status: str


class ChunksByWorkflowRequest(BaseModel):
    workflow_id: str


class ChunksByIdsRequest(BaseModel):
    chunk_ids: list[str]


class SimilaritySearchRequest(BaseModel):
    query: str
    workflow_id: str
    kb_type: str = "document"  # "document" | "policy" | "enriched"
    top_k: int = 5


class SearchPoliciesRequest(BaseModel):
    query: str
    assessment_id: str | None = None
    top_k: int = 5


class SubtopicItem(BaseModel):
    name: str


class TopicItem(BaseModel):
    name: str
    subtopics: list[SubtopicItem] = []


class StoreTopicsRequest(BaseModel):
    workflow_id: str
    topics: list[TopicItem]


class GetTopicsRequest(BaseModel):
    workflow_id: str


class AdminPolicyRequest(BaseModel):
    content: str
    policy_type: str = "rubric"
    assessment_id: str | None = None  # NULL = system-wide, UUID = per-assessment rubric
    workflow_id: str | None = None
    source: str | None = None  # "system_default" | "assessor_rubric" | "auto_generated" (auto-derived if not set)
    assessor_id: str | None = None
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# 1. POST /api/v1/internal/process-material
# ---------------------------------------------------------------------------

@router.post("/internal/process-material", response_model=ProcessMaterialResponse)
async def process_material(req: ProcessMaterialRequest):
    """Receive extracted text, chunk it, embed it, store in the appropriate table.

    Routes based on source_type:
    - "direct_text" / "ocr_extracted" → document_chunks
    - "rubric"                        → policy_chunks (requires assessment_id)
    - "web_research"                  → enriched_chunks
    """
    logger.info(
        "process_material",
        workflow_id=req.workflow_id,
        source_type=req.source_type,
        content_length=len(req.content_text),
    )

    # Validate rubric requires assessment_id
    if req.source_type == "rubric" and not req.assessment_id:
        raise HTTPException(400, "assessment_id is required when source_type is 'rubric'")

    # Sanitize text — remove null bytes that break PostgreSQL UTF-8 encoding
    clean_text = req.content_text.replace("\x00", "")

    # Chunk the text
    chunks = chunking.split_text_into_chunks(clean_text)
    if not chunks:
        return ProcessMaterialResponse(chunks_created=0, status="success")

    # Sanitize each chunk too
    chunks = [c.replace("\x00", "") for c in chunks]

    # Compute file hash for dedup
    file_hash = chunking.compute_file_hash(clean_text)

    # Embed chunks in batches (OpenAI has per-request limits)
    EMBED_BATCH_SIZE = 20
    embeddings: list[list[float]] = []
    for batch_start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[batch_start:batch_start + EMBED_BATCH_SIZE]
        batch_embeddings = await embedding.embed_texts(batch)
        embeddings.extend(batch_embeddings)

    # Estimate token count (~4 chars per token)
    def _estimate_tokens(text: str) -> int:
        return len(text) // 4

    # Route to correct table based on source_type
    created = 0
    for i, (chunk_text, emb) in enumerate(zip(chunks, embeddings)):
        content_hash = chunking.compute_content_hash(chunk_text)

        if req.source_type in ("direct_text", "ocr_extracted"):
            # Document KB
            if await repo.check_duplicate_chunk(req.workflow_id, content_hash):
                logger.debug("chunk_dedup_skip", workflow_id=req.workflow_id, index=i)
                continue
            await repo.insert_document_chunk(
                workflow_id=req.workflow_id,
                content=chunk_text,
                embedding=emb,
                chunk_index=i,
                source_type=req.source_type,
                file_hash=file_hash,
                content_hash=content_hash,
                assessor_id=req.assessor_id,
                token_count=_estimate_tokens(chunk_text),
                metadata={"source_file": req.source_file} if req.source_file else None,
            )

        elif req.source_type == "rubric":
            # Policy KB — per-assessment rubric
            await repo.insert_policy_chunk(
                content=chunk_text,
                embedding=emb,
                policy_type="rubric",
                assessment_id=req.assessment_id,
                workflow_id=req.workflow_id,
                chunk_index=i,
                source="assessor_rubric",
                assessor_id=req.assessor_id,
                metadata={"source_file": req.source_file} if req.source_file else None,
            )

        elif req.source_type == "web_research":
            # Enriched KB
            await repo.insert_enriched_chunk(
                workflow_id=req.workflow_id,
                content=chunk_text,
                embedding=emb,
                source_url=req.source_url,
                source_type="web_text",
                chunk_index=i,
                assessor_id=req.assessor_id,
                metadata={"source_file": req.source_file} if req.source_file else None,
            )

        else:
            raise HTTPException(400, f"Unknown source_type: {req.source_type}")

        created += 1

    logger.info(
        "process_material_done",
        workflow_id=req.workflow_id,
        total_chunks=len(chunks),
        created=created,
        deduped=len(chunks) - created,
    )

    return ProcessMaterialResponse(chunks_created=created, status="success")


# ---------------------------------------------------------------------------
# 2. POST /api/v1/internal/store-topics
# ---------------------------------------------------------------------------

@router.post("/internal/store-topics")
async def store_topics(req: StoreTopicsRequest):
    """Store topic hierarchy from Classification Agent.

    Enforces max 2 levels: main topic → subtopics. No deeper nesting.
    """
    logger.info("store_topics", workflow_id=req.workflow_id, count=len(req.topics))

    for topic in req.topics:
        # Level 1: main topic (parent_id = NULL)
        topic_id = await repo.insert_topic(
            workflow_id=req.workflow_id,
            name=topic.name,
            parent_id=None,
        )
        # Level 2: subtopics (parent_id = main topic)
        for sub in topic.subtopics:
            await repo.insert_topic(
                workflow_id=req.workflow_id,
                name=sub.name,
                parent_id=topic_id,
            )

    return {"status": "stored", "workflow_id": req.workflow_id}


# ---------------------------------------------------------------------------
# 3. POST /api/v1/internal/get-topics
# ---------------------------------------------------------------------------

@router.post("/internal/get-topics")
async def get_topics(req: GetTopicsRequest):
    """Return topics for a workflow."""
    flat = await repo.get_topics_by_workflow(req.workflow_id)

    # Build hierarchy: group by parent_id
    by_parent: dict[str | None, list] = {}
    for t in flat:
        by_parent.setdefault(t["parent_id"], []).append(t)

    def _build_tree(parent_id: str | None) -> list[dict]:
        children = by_parent.get(parent_id, [])
        return [
            {
                "topic_id": c["topic_id"],
                "name": c["name"],
                "subtopics": _build_tree(c["topic_id"]),
            }
            for c in children
        ]

    return {"topics": _build_tree(None), "workflow_id": req.workflow_id}


# ---------------------------------------------------------------------------
# 4. POST /api/v1/internal/similarity-search
# ---------------------------------------------------------------------------

@router.post("/internal/similarity-search")
async def similarity_search(req: SimilaritySearchRequest):
    """Vector similarity search across document/policy/enriched KBs."""
    query_emb = await embedding.embed_single(req.query)

    if req.kb_type == "document":
        chunks = await repo.similarity_search_documents(
            query_emb, req.workflow_id, req.top_k
        )
    elif req.kb_type == "enriched":
        chunks = await repo.similarity_search_enriched(
            query_emb, req.workflow_id, req.top_k
        )
    elif req.kb_type == "policy":
        chunks = await repo.similarity_search_policies(
            query_emb, assessment_id=None, top_k=req.top_k
        )
    else:
        raise HTTPException(400, f"Unknown kb_type: {req.kb_type}")

    return {"chunks": chunks, "workflow_id": req.workflow_id}


# ---------------------------------------------------------------------------
# 5. POST /api/v1/internal/search-policies
# ---------------------------------------------------------------------------

@router.post("/internal/search-policies")
async def search_policies(req: SearchPoliciesRequest):
    """Search policy_chunks for rubric/grading criteria."""
    query_emb = await embedding.embed_single(req.query)
    chunks = await repo.similarity_search_policies(
        query_emb, assessment_id=req.assessment_id, top_k=req.top_k
    )
    return {"chunks": chunks}


# ---------------------------------------------------------------------------
# 6. POST /api/v1/internal/chunks-by-workflow
# ---------------------------------------------------------------------------

@router.post("/internal/chunks-by-workflow")
async def chunks_by_workflow(req: ChunksByWorkflowRequest):
    """Get all document chunks for a workflow."""
    chunks = await repo.get_chunks_by_workflow(req.workflow_id)
    return {"chunks": chunks, "workflow_id": req.workflow_id}


# ---------------------------------------------------------------------------
# 7. POST /api/v1/internal/chunks-by-ids
# ---------------------------------------------------------------------------

@router.post("/internal/chunks-by-ids")
async def chunks_by_ids(req: ChunksByIdsRequest):
    """Get specific chunks by ID."""
    chunks = await repo.get_chunks_by_ids(req.chunk_ids)
    return {"chunks": chunks}


# ---------------------------------------------------------------------------
# 8. POST /api/v1/admin/policies
# ---------------------------------------------------------------------------

@router.post("/admin/policies")
async def admin_add_policy(req: AdminPolicyRequest):
    """Upload policy document — system-wide or per-assessment."""
    chunks = chunking.split_text_into_chunks(req.content)
    if not chunks:
        return {"status": "no_content", "chunks_created": 0}

    embeddings = await embedding.embed_texts(chunks)

    created = 0
    for i, (chunk_text, emb) in enumerate(zip(chunks, embeddings)):
        await repo.insert_policy_chunk(
            content=chunk_text,
            embedding=emb,
            policy_type=req.policy_type,
            assessment_id=req.assessment_id,
            workflow_id=req.workflow_id,
            chunk_index=i,
            source=req.source,
            assessor_id=req.assessor_id,
            metadata=req.metadata,
        )
        created += 1

    return {"status": "success", "chunks_created": created}
