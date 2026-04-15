#!/bin/bash
# Build script for Knowledge Service
# Generates Python gRPC stubs from grpc-registry, then builds Docker image

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GRPC_REGISTRY="$SCRIPT_DIR/../grpc-registry"
PROTO_DIR="$GRPC_REGISTRY/proto"
GEN_DIR="$GRPC_REGISTRY/gen/python"

# Step 1: Generate Python stubs from .proto files (like mvn compile for Java)
echo "Generating Python gRPC stubs from proto files..."
mkdir -p "$GEN_DIR"
docker run --rm \
  -v "$PROTO_DIR:/proto" \
  -v "$GEN_DIR:/out" \
  python:3.12-slim bash -c "
    pip install -q grpcio-tools protobuf &&
    python -m grpc_tools.protoc \
      -I/proto \
      --python_out=/out \
      --grpc_python_out=/out \
      assessorflow/identity/v1/identity.proto \
      assessorflow/knowledge/v1/knowledge.proto
  "

# Add __init__.py files for Python imports
find "$GEN_DIR" -type d -exec touch {}/__init__.py \;

echo "Stubs generated at: $GEN_DIR"

# Step 2: Copy stubs into Docker build context
echo "Copying stubs into build context..."
rm -rf "$SCRIPT_DIR/grpc-stubs"
cp -r "$GEN_DIR" "$SCRIPT_DIR/grpc-stubs"

# Step 3: Build Docker image
echo "Building Docker image..."
docker build -t knowledge-service "$SCRIPT_DIR"

# Cleanup build context copy
rm -rf "$SCRIPT_DIR/grpc-stubs"

echo ""
echo "Done. Run with:"
echo "  docker run -d --name knowledge-service -p 8030:8030 -p 9030:9030 --env-file .env -e KS_DB_HOST=host.docker.internal knowledge-service"
