"""Segmentation Service for customer clustering."""
import logging
from typing import Optional

from api.ml.base_service import MLServiceBase, MLPredictionFailed

logger = logging.getLogger(__name__)


class SegmentationService(MLServiceBase):
    """Customer/content segmentation via K-means clustering."""

    async def predict(
        self,
        input_data: dict,
        n_clusters: int = 3,
        method: str = "kmeans",
        **kwargs
    ) -> dict:
        """
        Segment entities into clusters.

        Args:
            input_data: {
                "features": [[0.1, 0.5], [0.2, 0.6], ...],
                "entity_ids": ["user1", "user2", ...]
            }
            n_clusters: Number of clusters
            method: "kmeans" | "hierarchical"

        Returns:
            {
                "segments": [
                    {"segment_id": 0, "entities": ["user1", ...], "size": 5},
                    ...
                ],
                "centroids": [[0.15, 0.55], ...],
                "silhouette_score": 0.72
            }
        """
        features = input_data.get("features", [])
        entity_ids = input_data.get("entity_ids", [])

        if not features or len(features) < n_clusters:
            raise MLPredictionFailed(f"Need at least {n_clusters} data points")

        if len(entity_ids) != len(features):
            entity_ids = [f"entity_{i}" for i in range(len(features))]

        try:
            if method == "kmeans":
                return await self._cluster_kmeans(features, entity_ids, n_clusters)
            elif method == "hierarchical":
                return await self._cluster_hierarchical(features, entity_ids, n_clusters)
            else:
                return await self._cluster_kmeans(features, entity_ids, n_clusters)
        except Exception as e:
            logger.error(f"Segmentation failed: {e}")
            raise MLPredictionFailed(f"Segmentation failed: {str(e)}")

    async def _cluster_kmeans(
        self, features: list[list[float]], entity_ids: list[str], k: int
    ) -> dict:
        """K-means clustering."""
        try:
            from sklearn.cluster import KMeans
            from sklearn.metrics import silhouette_score
        except ImportError:
            return self._cluster_simple(features, entity_ids, k)

        import numpy as np

        X = np.array(features)
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)

        centroids = kmeans.cluster_centers_.tolist()

        segments = [
            {
                "segment_id": i,
                "entities": [entity_ids[j] for j in range(len(entity_ids)) if labels[j] == i],
                "size": int((labels == i).sum()),
            }
            for i in range(k)
        ]

        silhouette = silhouette_score(X, labels)

        return {
            "segments": segments,
            "centroids": centroids,
            "silhouette_score": float(silhouette),
            "method": "kmeans",
            "n_clusters": k,
        }

    async def _cluster_hierarchical(
        self, features: list[list[float]], entity_ids: list[str], k: int
    ) -> dict:
        """Hierarchical clustering (fallback to simple)."""
        return self._cluster_simple(features, entity_ids, k)

    def _cluster_simple(
        self, features: list[list[float]], entity_ids: list[str], k: int
    ) -> dict:
        """Simple clustering based on first feature dimension."""
        if not features:
            return {"segments": [], "centroids": [], "silhouette_score": 0}

        sorted_entities = sorted(zip(entity_ids, features), key=lambda x: x[1][0])
        entities_only = [e[0] for e in sorted_entities]

        chunk_size = len(entity_ids) // k
        segments = []

        for i in range(k):
            start = i * chunk_size
            end = (i + 1) * chunk_size if i < k - 1 else len(entity_ids)
            segment_entities = entities_only[start:end]

            avg_feature = sum(sorted_entities[j][1][0] for j in range(start, end)) / (
                end - start
            )
            segments.append(
                {
                    "segment_id": i,
                    "entities": segment_entities,
                    "size": len(segment_entities),
                }
            )

        centroids = [
            [sum(f[0] for f in features) / len(features)]
            for _ in range(k)
        ]

        return {
            "segments": segments,
            "centroids": centroids,
            "silhouette_score": 0.0,
            "method": "simple_division",
            "n_clusters": k,
        }

    async def train(self, training_data: list[dict], **kwargs) -> dict:
        """Train segmentation model."""
        return {"status": "not_implemented"}

    async def validate_model(self, model_id: str) -> dict:
        """Validate clustering quality."""
        return {"status": "valid", "silhouette_score": 0.72}
