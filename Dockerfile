FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY proto/ proto/

# Upgrade pip + install dependencies
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

# Generate gRPC stubs from local proto files
RUN mkdir -p grpc-stubs \
    && python -m grpc_tools.protoc \
    -Iproto \
    --python_out=grpc-stubs \
    --grpc_python_out=grpc-stubs \
    assessorflow/knowledge/v1/knowledge.proto \
    && find grpc-stubs -type d -exec touch {}/__init__.py \;

ENV PYTHONPATH=/app/src:/app/grpc-stubs
EXPOSE 8030 9030

HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD curl -f http://localhost:8030/health || exit 1

CMD ["uvicorn", "knowledge_service.main:app", "--host", "0.0.0.0", "--port", "8030"]
