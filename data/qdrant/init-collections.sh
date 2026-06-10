#!/usr/bin/env bash
# Qdrant collection initialization via REST API.
# Called after Qdrant container is healthy; creates 5 collections (768-dim, cosine).
set -euo pipefail
QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6333}"

for collection in content_embeddings script_memory knowledge_memory trend_memory audience_profiles; do
  curl -s -X PUT \
    "${QDRANT_URL}/collections/${collection}" \
    -H "Content-Type: application/json" \
    -d '{
      "vectors": {
        "size": 768,
        "distance": "Cosine"
      }
    }' | jq . && echo "✓ ${collection}" || echo "✗ ${collection}"
done
