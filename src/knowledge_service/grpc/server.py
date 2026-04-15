"""gRPC server for Knowledge Service.

Same role as IdentityGrpcService.java in identity-access-service.
All 7 internal RPC methods delegate to the same repository + services
that the REST endpoints use.
"""

from __future__ import annotations

import asyncio
from concurrent import futures

import grpc
import structlog

from knowledge_service import config
from assessorflow.knowledge.v1 import knowledge_pb2, knowledge_pb2_grpc
from knowledge_service.db import repository as repo
from knowledge_service.services import chunking, embedding
from knowledge_service.grpc.interceptor import LoggingInterceptor

logger = structlog.get_logger(__name__)

GRPC_PORT = int(config.SERVICE_PORT) + 1000  # 8030 + 1000 = 9030


class KnowledgeServiceServicer(knowledge_pb2_grpc.KnowledgeServiceServicer):
    """Implements all 7 gRPC RPCs defined in knowledge.proto."""

    # ------------------------------------------------------------------
    # 1. ProcessMaterial
    # ------------------------------------------------------------------
    async def ProcessMaterial(self, request, context):
        logger.info("grpc_process_material", workflow_id=request.workflow_id, source_type=request.source_type)

        if request.source_type == "rubric" and not request.assessment_id:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("assessment_id is required when source_type is 'rubric'")
            return knowledge_pb2.ProcessMaterialResponse()

        chunks = chunking.split_text_into_chunks(request.content_text)
        if not chunks:
            return knowledge_pb2.ProcessMaterialResponse(chunks_created=0, status="success")

        file_hash = chunking.compute_file_hash(request.content_text)
        embeddings = await embedding.embed_texts(chunks)

        def _estimate_tokens(text: str) -> int:
            return len(text) // 4

        created = 0
        for i, (chunk_text, emb) in enumerate(zip(chunks, embeddings)):
            content_hash = chunking.compute_content_hash(chunk_text)

            if request.source_type in ("direct_text", "ocr_extracted"):
                if await repo.check_duplicate_chunk(request.workflow_id, content_hash):
                    continue
                await repo.insert_document_chunk(
                    workflow_id=request.workflow_id,
                    content=chunk_text,
                    embedding=emb,
                    chunk_index=i,
                    source_type=request.source_type,
                    source_file=request.source_file,
                    file_hash=file_hash,
                    content_hash=content_hash,
                    assessor_id=request.assessor_id or None,
                    token_count=_estimate_tokens(chunk_text),
                )

            elif request.source_type == "rubric":
                await repo.insert_policy_chunk(
                    content=chunk_text,
                    embedding=emb,
                    policy_type="rubric",
                    assessment_id=request.assessment_id,
                    workflow_id=request.workflow_id,
                    chunk_index=i,
                    source="assessor_rubric",
                    assessor_id=request.assessor_id or None,
                )

            elif request.source_type == "web_research":
                await repo.insert_enriched_chunk(
                    workflow_id=request.workflow_id,
                    content=chunk_text,
                    embedding=emb,
                    source_url=request.source_url,
                    source_type="web_text",
                    chunk_index=i,
                    assessor_id=request.assessor_id or None,
                )

            created += 1

        return knowledge_pb2.ProcessMaterialResponse(chunks_created=created, status="success")

    # ------------------------------------------------------------------
    # 2. StoreTopics
    # ------------------------------------------------------------------
    async def StoreTopics(self, request, context):
        logger.info("grpc_store_topics", workflow_id=request.workflow_id)

        for topic in request.topics:
            topic_id = await repo.insert_topic(
                workflow_id=request.workflow_id,
                name=topic.name,
                parent_id=None,
            )
            for sub in topic.subtopics:
                await repo.insert_topic(
                    workflow_id=request.workflow_id,
                    name=sub.name,
                    parent_id=topic_id,
                )

        return knowledge_pb2.StoreTopicsResponse(status="stored", workflow_id=request.workflow_id)

    # ------------------------------------------------------------------
    # 3. GetTopics
    # ------------------------------------------------------------------
    async def GetTopics(self, request, context):
        flat = await repo.get_topics_by_workflow(request.workflow_id)

        by_parent: dict[str | None, list] = {}
        for t in flat:
            by_parent.setdefault(t["parent_id"], []).append(t)

        def _build_tree(parent_id: str | None) -> list:
            children = by_parent.get(parent_id, [])
            return [
                knowledge_pb2.Topic(
                    topic_id=c["topic_id"],
                    name=c["name"],
                    subtopics=_build_tree(c["topic_id"]),
                )
                for c in children
            ]

        return knowledge_pb2.GetTopicsResponse(
            workflow_id=request.workflow_id,
            topics=_build_tree(None),
        )

    # ------------------------------------------------------------------
    # 4. SimilaritySearch
    # ------------------------------------------------------------------
    async def SimilaritySearch(self, request, context):
        query_emb = await embedding.embed_single(request.query)
        top_k = request.top_k or 5

        if request.kb_type == "document":
            results = await repo.similarity_search_documents(query_emb, request.workflow_id, top_k)
        elif request.kb_type == "enriched":
            results = await repo.similarity_search_enriched(query_emb, request.workflow_id, top_k)
        elif request.kb_type == "policy":
            results = await repo.similarity_search_policies(query_emb, assessment_id=None, top_k=top_k)
        else:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(f"Unknown kb_type: {request.kb_type}")
            return knowledge_pb2.SimilaritySearchResponse()

        chunks = [_dict_to_chunk_proto(c) for c in results]
        return knowledge_pb2.SimilaritySearchResponse(workflow_id=request.workflow_id, chunks=chunks)

    # ------------------------------------------------------------------
    # 5. SearchPolicies
    # ------------------------------------------------------------------
    async def SearchPolicies(self, request, context):
        query_emb = await embedding.embed_single(request.query)
        assessment_id = request.assessment_id or None
        top_k = request.top_k or 5

        results = await repo.similarity_search_policies(query_emb, assessment_id=assessment_id, top_k=top_k)
        chunks = [_dict_to_chunk_proto(c) for c in results]
        return knowledge_pb2.SearchPoliciesResponse(chunks=chunks)

    # ------------------------------------------------------------------
    # 6. GetChunksByWorkflow
    # ------------------------------------------------------------------
    async def GetChunksByWorkflow(self, request, context):
        results = await repo.get_chunks_by_workflow(request.workflow_id)
        chunks = [_dict_to_chunk_proto(c) for c in results]
        return knowledge_pb2.GetChunksByWorkflowResponse(workflow_id=request.workflow_id, chunks=chunks)

    # ------------------------------------------------------------------
    # 7. GetChunksByIds
    # ------------------------------------------------------------------
    async def GetChunksByIds(self, request, context):
        results = await repo.get_chunks_by_ids(list(request.chunk_ids))
        chunks = [_dict_to_chunk_proto(c) for c in results]
        return knowledge_pb2.GetChunksByIdsResponse(chunks=chunks)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dict_to_chunk_proto(d: dict) -> knowledge_pb2.Chunk:
    """Convert a repository dict to a protobuf Chunk message."""
    metadata = {str(k): str(v) for k, v in (d.get("metadata") or {}).items()}
    return knowledge_pb2.Chunk(
        chunk_id=d.get("chunk_id", ""),
        workflow_id=d.get("workflow_id", ""),
        content=d.get("content", ""),
        source_type=d.get("source_type", ""),
        metadata=metadata,
        score=d.get("score", 0.0) or 0.0,
    )


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

async def start_grpc_server() -> grpc.aio.Server:
    """Start the async gRPC server on GRPC_PORT."""
    server = grpc.aio.server(interceptors=[LoggingInterceptor()])
    knowledge_pb2_grpc.add_KnowledgeServiceServicer_to_server(
        KnowledgeServiceServicer(), server
    )
    server.add_insecure_port(f"0.0.0.0:{GRPC_PORT}")
    await server.start()
    logger.info("grpc_server_started", port=GRPC_PORT)
    return server


async def stop_grpc_server(server: grpc.aio.Server) -> None:
    """Gracefully stop the gRPC server."""
    await server.stop(grace=30)
    logger.info("grpc_server_stopped")
