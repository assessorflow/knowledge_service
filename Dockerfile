FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY knowledge-service/pyproject.toml .
COPY knowledge-service/src/ src/

# Copy gRPC stubs from grpc-registry
COPY grpc-registry/gen/python/ grpc-stubs/

RUN pip install --no-cache-dir .

ENV PYTHONPATH=/app/src:/app/grpc-stubs
EXPOSE 8030 9030

HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD curl -f http://localhost:8030/health || exit 1

CMD ["uvicorn", "knowledge_service.main:app", "--host", "0.0.0.0", "--port", "8030"]
