# Knowledge Service — Production Readiness Audit

> **Auditor:** Claude (paired with Thet Naung Soe)
> **Date:** 2026-04-15
> **Codebase:** `/Users/thetnaungsoe/Desktop/assessor_flow_prod/knowledge-service`
> **Stack:** Python 3.12, FastAPI, asyncpg, pgvector, gRPC, LangChain (text splitters), OpenAI/Model Broker
> **Source of Truth:** `/Users/thetnaungsoe/Desktop/neo-assessor-flow/reference/` (schema.md §3, vector_schema.md, api_contract.md §3)
> **Verdict:** RAG pipeline is functionally complete and well-structured. Critical security issues (exposed API keys, missing .gitignore). Fixable in-place.

---

## Executive Summary

The Knowledge Service correctly implements the RAG pipeline per `vector_schema.md`: document chunking (LangChain `RecursiveCharacterTextSplitter`), embedding (OpenAI/Model Broker), pgvector storage, and cosine similarity search across 3 Knowledge Bases (Document, Policy, Enriched). All 7 gRPC RPCs + 8 REST endpoints match `api_contract.md` §3. Topic hierarchy storage works.

The main gaps are: **OpenAI API key exposed in .env (not gitignored!)**, **zero-vector fallback silently corrupts the vector store**, **no transactions on ProcessMaterial**, and the same patterns from submission service (no auth, reload=True, Dockerfile references grpc-registry, wrong .gitignore).

---

## CRITICAL — Must Fix Before Any Deployment

### ~~C-1. OpenAI API Key Exposed — `.env` NOT Gitignored~~ FIXED

**Files:** `.env` (contains `sk-proj-dCNwu5...`), `.gitignore` (only lists `grpc-stubs/`)

The `.gitignore` does NOT include `.env`, `*.pyc`, `__pycache__/`, or any credential patterns. The OpenAI API key is a live secret that will be committed on `git add .`.

**Fix:**
1. **Immediately rotate the OpenAI key** at platform.openai.com
2. Update `.gitignore`:
   ```
   .env
   __pycache__/
   *.pyc
   grpc-stubs/
   ```
3. If already committed, scrub from git history

---

### ~~C-2. Zero-Vector Fallback Silently Corrupts Vector Store~~ FIXED

**File:** `services/embedding.py:45, 68, 88`

```python
return [[0.0] * config.EMBEDDING_DIMENSION for _ in texts]
```

When OpenAI/Model Broker fails, the service returns 1536-dimensional zero vectors. These get stored in `document_chunks.embedding` and `policy_chunks.embedding`. Every subsequent similarity search returns these zero-vector chunks as results (they have a non-zero cosine similarity to real queries), polluting all search results.

**Impact:** Silent data corruption. Assessments grounded on zero-vector chunks produce garbage Q&A.

**Fix:** Fail fast — raise an exception instead of returning zeros:
```python
except Exception as exc:
    logger.error("openai_embedding_failed", error=str(exc))
    raise RuntimeError(f"Embedding failed: {exc}")
```

The caller (`ProcessMaterial`) should catch this and return an error to the Validator Agent, which will NACK the Pub/Sub message for retry.

---

### ~~C-3. No Transactions on ProcessMaterial~~ FIXED

**File:** `routes/internal.py` — ProcessMaterial endpoint

The ProcessMaterial flow:
1. Chunk text into N pieces
2. Embed chunks in batches of 20
3. Insert each chunk into DB individually

If embedding fails at batch 3 of 5, chunks 1-40 are already stored with real embeddings, but chunks 41-N are lost. The workflow continues with partial data.

**Fix:** Wrap in asyncpg transaction (same pattern as submission service C-4):
```python
async with pool.acquire() as conn:
    async with conn.transaction():
        for chunk, embedding in zip(chunks, embeddings):
            await conn.execute("INSERT INTO document_chunks ...")
```

---

### ~~C-4. Dockerfile References `grpc-registry`~~ FIXED

**File:** `Dockerfile:11`

```dockerfile
COPY grpc-registry/gen/python/ grpc-stubs/
```

Same issue as other services. Depends on the centralized grpc-registry.

**Fix:** Create local `proto/` directory with `knowledge.proto`, generate stubs at build time. Update `build.sh` to use local proto (same pattern as submission service).

---

## HIGH — Should Fix Before Production

### ~~H-1. No Auth on REST or gRPC Endpoints~~ FIXED

Same pattern as submission service. All 8 REST endpoints and 7 gRPC RPCs are unauthenticated.

**Fix:** Add JWT validation FastAPI dependency for REST (same `services/auth.py` as submission service). Add logging interceptor for gRPC.

---

### ~~H-2. `reload=True` in Production Entry Point~~ FIXED

**File:** `main.py:80`

**Fix:** Same as submission service H-6: `reload=os.environ.get("ENV", "prod") == "dev"`

---

### ~~H-3. `ready` Endpoint Returns 200 on Failure~~ FIXED

**File:** `main.py:70`

**Fix:** Return 503 on failure (same as submission service M-4).

---

### ~~H-4. No Graceful gRPC Shutdown~~ FIXED

**File:** `grpc/server.py`

**Fix:** Change `server.stop(grace=5)` to `server.stop(grace=30)`.

---

### ~~H-5. Inconsistent Logic Between REST and gRPC~~ FIXED

**File:** `routes/internal.py` vs `grpc/server.py`

REST ProcessMaterial sanitizes null bytes (`content_text.replace("\x00", "")`), gRPC ProcessMaterial does not. The logic is duplicated with subtle differences.

**Fix:** Extract shared business logic into `services/material_processor.py`. Both REST and gRPC call the same function.

---

### ~~H-6. No Metrics or Observability~~ FIXED

No Prometheus metrics. Can't answer: "How many chunks were created today?" or "What's the embedding API p99 latency?"

**Fix:** Add `prometheus-fastapi-instrumentator` (same as submission service M-3).

---

## MEDIUM — Code Quality & Maintainability

### ~~M-1. No Structured Error Responses~~ FIXED

REST errors use raw `HTTPException`. No consistent error format.

**Fix:** Add error handlers in `main.py` (same pattern as submission service M-1).

---

### ~~M-2. `SIMILARITY_THRESHOLD` Defined But Never Used~~ DEFERRED

**File:** `config.py:29`

The threshold is configured but never applied in queries. All results are returned regardless of score.

**Fix:** Filter results in `similarity_search_documents()`:
```python
WHERE 1 - (embedding <=> $1::vector) >= $threshold
```

---

### ~~M-3. No Pagination on `get_chunks_by_workflow()`~~ DEFERRED

Returns ALL chunks for a workflow. Could be thousands.

**Fix:** Add `limit`/`offset` parameters.

---

### ~~M-4. Token Count Estimation is Crude~~ ACCEPTED

**File:** `repository.py` — `len(text) // 4`

Not accurate. Different models use different tokenizers.

**Fix:** Use `tiktoken` for OpenAI models, or accept the estimation and document the limitation.

---

### ~~M-5. `assessor_id` Nullable in `document_chunks`~~ DEFERRED

Per `vector_schema.md` §1, `assessor_id` should be `NOT NULL`. Code allows null:
```python
UUID(assessor_id) if assessor_id else None
```

**Fix:** Enforce NOT NULL. If `assessor_id` is not provided, look it up from `assessment_configs` via `workflow_id`.

---

### ~~M-6. Deduplication Strategy is Inconsistent~~ DEFERRED

Both `content_hash` (per-chunk) and `file_hash` (per-file) exist, but only `content_hash` is checked for deduplication. Two files with the same content but different names will create duplicate chunks.

**Fix:** Check `file_hash` first (skip entire file if already processed), then `content_hash` per chunk.

---

## LOW — Nice to Have

### ~~L-1. No Embedding Version Tracking~~ DEFERRED
Per `vector_schema.md`, embedding model version should be tracked. Not implemented.

### ~~L-2. No Semantic Cache~~ DEFERRED
`vector_schema.md` mentions a semantic cache for repeated queries. Not implemented.

### ~~L-3. No KB Re-Ranking Across Tables~~ DEFERRED
Each KB is searched separately. No cross-KB merge and re-rank as described in `vector_schema.md` RAG Query Flow.

### ~~L-4. Tests Only Cover Integration~~ DEFERRED
No unit tests for chunking, embedding, or repository functions.

---

## Priority Order for Implementation

| Priority | Items | Effort |
|----------|-------|--------|
| **Do first** | C-1 (.gitignore + rotate key), C-2 (fail on embedding error) | 30 min |
| **Do second** | C-3 (transactions), C-4 (inline proto), H-1 (auth) | 3 hours |
| **Do third** | H-2 (reload), H-3 (ready 503), H-4 (graceful shutdown), H-5 (shared logic) | 2 hours |
| **Do fourth** | H-6 (metrics), M-1 (error responses), M-2 (threshold), M-5 (assessor_id) | 2 hours |
| **Do last** | M-3 (pagination), M-4 (token count), M-6 (dedup), L-* | 2 hours |

---

## What's Already Good

- **RAG pipeline complete** — chunk → embed → store → search works end-to-end
- **3 Knowledge Bases** correctly separated: Document, Policy, Enriched per `vector_schema.md`
- **pgvector cosine similarity** with IVFFlat indexing
- **LangChain RecursiveCharacterTextSplitter** — production-grade chunking with markdown-aware separators
- **Dual embedding provider** — OpenAI for dev, Model Broker for prod
- **Batch embedding** — processes 20 chunks at a time (avoids API rate limits)
- **Content deduplication** via SHA-256 content hash
- **Topic hierarchy** — 2-level storage (main topic → subtopics) per `schema.md` §3
- **Dual API surface** — REST + gRPC with matching functionality
- **Structlog** for structured logging
- **Async throughout** — asyncpg, httpx, grpc.aio
- **Configurable chunking** — target/max/min sizes via env vars
