"""Internal API routes — called by agents via HTTP (future: gRPC).

8 endpoints matching KnowledgeServicePort + admin policy endpoint.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import structlog

from knowledge_service.db import repository as repo
from knowledge_service.services import chunking, embedding
from knowledge_service.services.material_processor import process_material as _process_material
from knowledge_service.services.embedding import EmbeddingError
from knowledge_service.services.auth import UserContext, get_current_user

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
    - "direct_text" / "ocr_extracted" -> document_chunks
    - "rubric"                        -> policy_chunks (requires assessment_id)
    - "web_research"                  -> enriched_chunks

    Uses shared material_processor (C-3 transactional, C-2 fail-fast on embedding, H-5 shared logic).
    """
    if req.source_type == "rubric" and not req.assessment_id:
        raise HTTPException(400, "assessment_id is required when source_type is 'rubric'")

    try:
        result = await _process_material(
            workflow_id=req.workflow_id,
            content_text=req.content_text,
            source_type=req.source_type,
            source_file=req.source_file,
            source_url=req.source_url,
            assessor_id=req.assessor_id,
            assessment_id=req.assessment_id,
        )
        return ProcessMaterialResponse(**result)
    except EmbeddingError as e:
        raise HTTPException(502, f"Embedding failed: {e}")
    except ValueError as e:
        raise HTTPException(400, str(e))


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
async def admin_add_policy(req: AdminPolicyRequest, user: UserContext = Depends(get_current_user)):
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
