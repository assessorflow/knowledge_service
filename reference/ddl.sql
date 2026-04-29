-- Knowledge Service — DDL
-- Database: af_knowledge
-- Source of truth: schema.md Section 3 + vector_schema.md
-- PostgreSQL 16+ with pgvector 0.8+

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================================
-- topics (schema.md Section 3)
-- ============================================================================

CREATE TABLE topics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id VARCHAR(50) NOT NULL,
    parent_id UUID REFERENCES topics(id),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_topics_workflow ON topics(workflow_id);
CREATE INDEX idx_topics_parent ON topics(parent_id);

-- ============================================================================
-- document_chunks (vector_schema.md Section 1)
-- ============================================================================

CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id VARCHAR(50) NOT NULL,
    assessor_id UUID NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1536) NOT NULL,
    source_file VARCHAR(255) NOT NULL,
    source_page INTEGER,
    source_type VARCHAR(50) NOT NULL DEFAULT 'direct_text',
    chunk_index INTEGER NOT NULL,
    token_count INTEGER,
    file_hash VARCHAR(64),
    content_hash VARCHAR(64),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_document_chunks_workflow ON document_chunks(workflow_id);
CREATE INDEX idx_document_chunks_assessor ON document_chunks(assessor_id);

-- ============================================================================
-- policy_chunks (vector_schema.md Section 2)
-- ============================================================================

CREATE TABLE policy_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    assessment_id UUID DEFAULT NULL,
    policy_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1536) NOT NULL,
    source VARCHAR(255) NOT NULL DEFAULT 'system_default',
    workflow_id VARCHAR(50),
    assessor_id UUID,
    chunk_index INTEGER,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_policy_chunks_type ON policy_chunks(policy_type);
CREATE INDEX idx_policy_chunks_assessment ON policy_chunks(assessment_id);

-- ============================================================================
-- enriched_chunks (vector_schema.md Section 3)
-- ============================================================================

CREATE TABLE enriched_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id VARCHAR(50) NOT NULL,
    assessor_id UUID NOT NULL,
    topic_id UUID REFERENCES topics(id),
    content TEXT NOT NULL,
    embedding VECTOR(1536) NOT NULL,
    source_url VARCHAR(1024),
    source_type VARCHAR(50) NOT NULL DEFAULT 'web_text',
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_enriched_chunks_workflow ON enriched_chunks(workflow_id);
CREATE INDEX idx_enriched_chunks_topic ON enriched_chunks(topic_id);
CREATE INDEX idx_enriched_chunks_assessor ON enriched_chunks(assessor_id);

-- Note: IVFFlat indexes for vector similarity search require data to be present
-- before creation (they need training data). Create them after initial data load:
--
-- CREATE INDEX idx_document_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
-- CREATE INDEX idx_policy_chunks_embedding ON policy_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
-- CREATE INDEX idx_enriched_chunks_embedding ON enriched_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
