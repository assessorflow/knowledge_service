"""Configuration for the Knowledge Service."""

import os


# Database (af_knowledge)
DB_HOST = os.environ.get("KS_DB_HOST", "localhost")
DB_PORT = int(os.environ.get("KS_DB_PORT", "15433"))
DB_NAME = os.environ.get("KS_DB_NAME", "af_knowledge")
DB_USER = os.environ.get("KS_DB_USER", "assessorflow")
DB_PASSWORD = os.environ.get("KS_DB_PASSWORD", "assessorflow_prod")

# Embedding provider: "openai" (direct) or "model_broker" (production)
EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "openai")

# OpenAI (used when EMBEDDING_PROVIDER=openai)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_EMBEDDING_MODEL = os.environ.get(
    "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
)

# Model Broker (used when EMBEDDING_PROVIDER=model_broker)
MODEL_BROKER_URL = os.environ.get("MODEL_BROKER_URL", "http://localhost:8050")

# Chunking
CHUNK_TARGET_SIZE = int(os.environ.get("CHUNK_TARGET_SIZE", "800"))
CHUNK_MAX_SIZE = int(os.environ.get("CHUNK_MAX_SIZE", "1200"))
CHUNK_MIN_SIZE = int(os.environ.get("CHUNK_MIN_SIZE", "100"))

# Similarity search
SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "0.85"))
DEFAULT_TOP_K = int(os.environ.get("DEFAULT_TOP_K", "5"))

# Embedding
EMBEDDING_DIMENSION = 1536

# Identity Service (for JWT validation)
IDENTITY_JWKS_URL = os.environ.get(
    "IDENTITY_JWKS_URL", "http://localhost:8081/.well-known/jwks.json"
)
JWT_ISSUER = os.environ.get("JWT_ISSUER", "assessorflow")
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE", "assessorflow-api")

# Server
SERVICE_PORT = int(os.environ.get("KS_PORT", "8030"))
