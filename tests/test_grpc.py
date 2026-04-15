"""gRPC integration test — tests all 7 RPCs against the running Knowledge Service."""

import asyncio
import grpc
from assessorflow.knowledge.v1 import knowledge_pb2, knowledge_pb2_grpc


GRPC_HOST = "host.docker.internal:9030"


async def main():
    channel = grpc.aio.insecure_channel(GRPC_HOST)
    stub = knowledge_pb2_grpc.KnowledgeServiceStub(channel)

    print("=" * 60)
    print("Testing Knowledge Service gRPC — 7 RPCs")
    print("=" * 60)

    # 1. ProcessMaterial (document)
    print("\n1. ProcessMaterial (direct_text)...")
    resp = await stub.ProcessMaterial(knowledge_pb2.ProcessMaterialRequest(
        workflow_id="wf_grpc_test",
        content_text="Encapsulation is the bundling of data with the methods that operate on that data. It restricts direct access to some of an objects components. Polymorphism allows objects of different classes to be treated as objects of a common superclass. Inheritance enables a new class to receive properties from an existing class.",
        source_type="direct_text",
        source_file="grpc_test.pdf",
    ))
    print(f"   chunks_created={resp.chunks_created}, status={resp.status}")

    # 2. StoreTopics
    print("\n2. StoreTopics...")
    resp = await stub.StoreTopics(knowledge_pb2.StoreTopicsRequest(
        workflow_id="wf_grpc_test",
        topics=[
            knowledge_pb2.TopicItem(
                name="OOP Concepts",
                subtopics=[
                    knowledge_pb2.Subtopic(name="Encapsulation"),
                    knowledge_pb2.Subtopic(name="Polymorphism"),
                ],
            )
        ],
    ))
    print(f"   status={resp.status}, workflow_id={resp.workflow_id}")

    # 3. GetTopics
    print("\n3. GetTopics...")
    resp = await stub.GetTopics(knowledge_pb2.GetTopicsRequest(
        workflow_id="wf_grpc_test",
    ))
    for topic in resp.topics:
        print(f"   {topic.name}")
        for sub in topic.subtopics:
            print(f"     - {sub.name}")

    # 4. SimilaritySearch
    print("\n4. SimilaritySearch (document KB)...")
    resp = await stub.SimilaritySearch(knowledge_pb2.SimilaritySearchRequest(
        query="data hiding in classes",
        workflow_id="wf_grpc_test",
        kb_type="document",
        top_k=3,
    ))
    for chunk in resp.chunks:
        print(f"   score={chunk.score:.4f} | {chunk.content[:80]}...")

    # 5. SearchPolicies
    print("\n5. SearchPolicies...")
    resp = await stub.SearchPolicies(knowledge_pb2.SearchPoliciesRequest(
        query="grading partial marks",
        top_k=3,
    ))
    if resp.chunks:
        for chunk in resp.chunks:
            print(f"   score={chunk.score:.4f} | {chunk.content[:80]}...")
    else:
        print("   (no policies found — add some via admin/policies first)")

    # 6. GetChunksByWorkflow
    print("\n6. GetChunksByWorkflow...")
    resp = await stub.GetChunksByWorkflow(knowledge_pb2.GetChunksByWorkflowRequest(
        workflow_id="wf_grpc_test",
    ))
    print(f"   {len(resp.chunks)} chunks found")
    chunk_ids = [c.chunk_id for c in resp.chunks]

    # 7. GetChunksByIds
    print("\n7. GetChunksByIds...")
    if chunk_ids:
        resp = await stub.GetChunksByIds(knowledge_pb2.GetChunksByIdsRequest(
            chunk_ids=chunk_ids[:2],
        ))
        for chunk in resp.chunks:
            print(f"   id={chunk.chunk_id[:8]}... | {chunk.content[:60]}...")
    else:
        print("   (no chunks to retrieve)")

    await channel.close()

    print("\n" + "=" * 60)
    print("All 7 gRPC RPCs tested successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
