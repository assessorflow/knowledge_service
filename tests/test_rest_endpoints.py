"""REST endpoint tests for Knowledge Service.

Uses real PostgreSQL+pgvector, mocked embeddings.
"""

import pytest
from httpx import AsyncClient


# ===========================================================================
# Health
# ===========================================================================


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_ready(client: AsyncClient):
    resp = await client.get("/ready")
    assert resp.status_code == 200


# ===========================================================================
# Store Topics
# ===========================================================================


@pytest.mark.asyncio
async def test_store_topics(client: AsyncClient):
    resp = await client.post(
        "/api/v1/internal/store-topics",
        json={
            "workflow_id": "wf_test001",
            "topics": [
                {
                    "name": "Object-Oriented Programming",
                    "subtopics": [
                        {"name": "Encapsulation"},
                        {"name": "Polymorphism"},
                    ],
                }
            ],
        },
    )
    assert resp.status_code == 200


# ===========================================================================
# Get Topics
# ===========================================================================


@pytest.mark.asyncio
async def test_get_topics(client: AsyncClient):
    # Store first
    await client.post(
        "/api/v1/internal/store-topics",
        json={
            "workflow_id": "wf_topics001",
            "topics": [
                {
                    "name": "Data Structures",
                    "subtopics": [{"name": "Arrays"}, {"name": "Trees"}],
                }
            ],
        },
    )

    resp = await client.post(
        "/api/v1/internal/get-topics",
        json={
            "workflow_id": "wf_topics001",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["topics"]) >= 1


@pytest.mark.asyncio
async def test_get_topics_empty(client: AsyncClient):
    resp = await client.post(
        "/api/v1/internal/get-topics",
        json={
            "workflow_id": "wf_nonexistent",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["topics"] == []


# ===========================================================================
# Process Material
# ===========================================================================


@pytest.mark.asyncio
async def test_process_material_document(client: AsyncClient):
    resp = await client.post(
        "/api/v1/internal/process-material",
        json={
            "workflow_id": "wf_mat001",
            "content_text": "This is a test document about Object-Oriented Programming. "
            "Encapsulation bundles data with methods. Polymorphism allows "
            "objects of different classes to respond to the same method. " * 10,
            "source_type": "direct_text",
            "source_file": "test_doc.pdf",
            "assessor_id": "550e8400-e29b-41d4-a716-446655440000",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["chunks_created"] >= 1


@pytest.mark.asyncio
async def test_process_material_enriched(client: AsyncClient):
    resp = await client.post(
        "/api/v1/internal/process-material",
        json={
            "workflow_id": "wf_enrich001",
            "content_text": "Web research content about algorithms and data structures. "
            * 10,
            "source_type": "web_text",
            "source_file": "web_research.md",
            "assessor_id": "550e8400-e29b-41d4-a716-446655440000",
            "source_url": "https://example.com/algorithms",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["chunks_created"] >= 1


@pytest.mark.asyncio
async def test_process_material_rubric(client: AsyncClient):
    resp = await client.post(
        "/api/v1/internal/process-material",
        json={
            "workflow_id": "wf_rubric001",
            "content_text": "Award full marks for identifying at least 3 key differences. "
            "Partial marks for incomplete but correct answers. " * 5,
            "source_type": "rubric",
            "source_file": "rubric.pdf",
            "assessor_id": "550e8400-e29b-41d4-a716-446655440000",
            "assessment_id": "660e8400-e29b-41d4-a716-446655440001",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["chunks_created"] >= 1


@pytest.mark.asyncio
async def test_process_material_empty(client: AsyncClient):
    resp = await client.post(
        "/api/v1/internal/process-material",
        json={
            "workflow_id": "wf_empty001",
            "content_text": "",
            "source_type": "direct_text",
            "source_file": "empty.pdf",
            "assessor_id": "550e8400-e29b-41d4-a716-446655440000",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["chunks_created"] == 0


# ===========================================================================
# Similarity Search
# ===========================================================================


@pytest.mark.asyncio
async def test_similarity_search(client: AsyncClient):
    # Store some chunks first
    await client.post(
        "/api/v1/internal/process-material",
        json={
            "workflow_id": "wf_search001",
            "content_text": "Encapsulation is one of the four OOP pillars. " * 10,
            "source_type": "direct_text",
            "source_file": "oop.pdf",
            "assessor_id": "550e8400-e29b-41d4-a716-446655440000",
        },
    )

    resp = await client.post(
        "/api/v1/internal/similarity-search",
        json={
            "query": "What is encapsulation?",
            "workflow_id": "wf_search001",
            "kb_type": "document",
            "top_k": 3,
        },
    )
    assert resp.status_code == 200
    assert "chunks" in resp.json()


@pytest.mark.asyncio
async def test_similarity_search_empty_results(client: AsyncClient):
    resp = await client.post(
        "/api/v1/internal/similarity-search",
        json={
            "query": "quantum physics",
            "workflow_id": "wf_nonexistent",
            "kb_type": "document",
            "top_k": 3,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["chunks"] == []


# ===========================================================================
# Search Policies
# ===========================================================================


@pytest.mark.asyncio
async def test_search_policies(client: AsyncClient):
    # Store a policy first
    await client.post(
        "/api/v1/internal/process-material",
        json={
            "workflow_id": "wf_pol001",
            "content_text": "Award marks based on completeness and accuracy. " * 5,
            "source_type": "rubric",
            "source_file": "rubric.pdf",
            "assessor_id": "550e8400-e29b-41d4-a716-446655440000",
            "assessment_id": "770e8400-e29b-41d4-a716-446655440002",
        },
    )

    resp = await client.post(
        "/api/v1/internal/search-policies",
        json={
            "query": "How to award marks?",
            "assessment_id": "770e8400-e29b-41d4-a716-446655440002",
            "top_k": 3,
        },
    )
    assert resp.status_code == 200
    assert "chunks" in resp.json()


# ===========================================================================
# Chunks by Workflow
# ===========================================================================


@pytest.mark.asyncio
async def test_chunks_by_workflow(client: AsyncClient):
    await client.post(
        "/api/v1/internal/process-material",
        json={
            "workflow_id": "wf_bywork001",
            "content_text": "Test content for chunk retrieval by workflow. " * 10,
            "source_type": "direct_text",
            "source_file": "test.pdf",
            "assessor_id": "550e8400-e29b-41d4-a716-446655440000",
        },
    )

    resp = await client.post(
        "/api/v1/internal/chunks-by-workflow",
        json={
            "workflow_id": "wf_bywork001",
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()["chunks"]) >= 1


@pytest.mark.asyncio
async def test_chunks_by_workflow_empty(client: AsyncClient):
    resp = await client.post(
        "/api/v1/internal/chunks-by-workflow",
        json={
            "workflow_id": "wf_nonexistent",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["chunks"] == []


# ===========================================================================
# Chunks by IDs
# ===========================================================================


@pytest.mark.asyncio
async def test_chunks_by_ids(client: AsyncClient):
    # Store material, then get workflow chunks to find IDs
    await client.post(
        "/api/v1/internal/process-material",
        json={
            "workflow_id": "wf_byid001",
            "content_text": "Test content for chunk retrieval by ID. " * 10,
            "source_type": "direct_text",
            "source_file": "test.pdf",
            "assessor_id": "550e8400-e29b-41d4-a716-446655440000",
        },
    )

    wf_resp = await client.post(
        "/api/v1/internal/chunks-by-workflow",
        json={
            "workflow_id": "wf_byid001",
        },
    )
    chunk_ids = [c["chunk_id"] for c in wf_resp.json()["chunks"]]

    resp = await client.post(
        "/api/v1/internal/chunks-by-ids",
        json={
            "chunk_ids": chunk_ids[:2],
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()["chunks"]) >= 1


@pytest.mark.asyncio
async def test_chunks_by_ids_empty(client: AsyncClient):
    resp = await client.post(
        "/api/v1/internal/chunks-by-ids",
        json={
            "chunk_ids": [],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["chunks"] == []


# ===========================================================================
# Get Chunk Detail (External — Frontend)
# ===========================================================================


@pytest.mark.asyncio
async def test_get_chunk_detail(client: AsyncClient):
    # Store + retrieve IDs
    await client.post(
        "/api/v1/internal/process-material",
        json={
            "workflow_id": "wf_detail001",
            "content_text": "Detailed chunk content for frontend grounding. " * 10,
            "source_type": "direct_text",
            "source_file": "detail.pdf",
            "assessor_id": "550e8400-e29b-41d4-a716-446655440000",
        },
    )
    wf_resp = await client.post(
        "/api/v1/internal/chunks-by-workflow",
        json={
            "workflow_id": "wf_detail001",
        },
    )
    chunk_id = wf_resp.json()["chunks"][0]["chunk_id"]

    resp = await client.get(f"/api/v1/knowledge/chunks/{chunk_id}")
    assert resp.status_code == 200
    assert resp.json()["chunk_id"] == chunk_id
    assert "content" in resp.json()


@pytest.mark.asyncio
async def test_get_chunk_detail_not_found(client: AsyncClient):
    resp = await client.get(
        "/api/v1/knowledge/chunks/00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 404
