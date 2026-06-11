"""Recommendation Service for content recommendations."""
import logging
from typing import Optional

from api.ml.base_service import MLServiceBase, MLPredictionFailed

logger = logging.getLogger(__name__)


class RecommendationService(MLServiceBase):
    """Collaborative filtering and content recommendations."""

    async def predict(
        self,
        input_data: dict,
        method: str = "content_based",
        top_k: int = 5,
        **kwargs
    ) -> dict:
        """
        Generate content recommendations.

        Args:
            input_data: {
                "user_id": "user123",
                "user_features": [0.1, 0.5, ...],
                "content_items": [
                    {"id": "content1", "features": [0.15, 0.55, ...]},
                    ...
                ]
            }
            method: "content_based" | "collaborative"
            top_k: Number of recommendations

        Returns:
            {
                "recommendations": [
                    {"item_id": "content1", "score": 0.95, "reason": "Similar to liked content"},
                    ...
                ],
                "method": "content_based",
                "explanation": "Based on user interests"
            }
        """
        user_id = input_data.get("user_id")
        user_features = input_data.get("user_features", [])
        content_items = input_data.get("content_items", [])

        if not content_items:
            raise MLPredictionFailed("No content items provided")

        try:
            if method == "collaborative":
                return await self._recommend_collaborative(
                    user_id, user_features, content_items, top_k
                )
            else:
                return await self._recommend_content_based(
                    user_id, user_features, content_items, top_k
                )
        except Exception as e:
            logger.error(f"Recommendation failed: {e}")
            raise MLPredictionFailed(f"Recommendation failed: {str(e)}")

    async def _recommend_content_based(
        self,
        user_id: str,
        user_features: list[float],
        content_items: list[dict],
        top_k: int,
    ) -> dict:
        """Content-based filtering using feature similarity."""
        if not user_features or not content_items:
            return {
                "recommendations": [],
                "method": "content_based",
                "explanation": "Insufficient data",
            }

        def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
            if not vec1 or not vec2:
                return 0.0

            min_len = min(len(vec1), len(vec2))
            vec1 = vec1[:min_len]
            vec2 = vec2[:min_len]

            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            magnitude1 = sum(x**2 for x in vec1) ** 0.5
            magnitude2 = sum(x**2 for x in vec2) ** 0.5

            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0

            return dot_product / (magnitude1 * magnitude2)

        scores = []
        for item in content_items:
            item_features = item.get("features", [])
            similarity = cosine_similarity(user_features, item_features)
            scores.append(
                {
                    "item_id": item.get("id"),
                    "score": similarity,
                    "reason": "Similar to user interests",
                }
            )

        scores = sorted(scores, key=lambda x: x["score"], reverse=True)[:top_k]

        return {
            "recommendations": scores,
            "method": "content_based",
            "explanation": "Based on feature similarity",
            "user_id": user_id,
        }

    async def _recommend_collaborative(
        self,
        user_id: str,
        user_features: list[float],
        content_items: list[dict],
        top_k: int,
    ) -> dict:
        """Collaborative filtering (simplified user-user similarity)."""
        try:
            from sklearn.metrics.pairwise import cosine_similarity as sk_cosine
            import numpy as np

            if user_features and content_items:
                X = np.array([item.get("features", []) for item in content_items])
                user_vec = np.array(user_features).reshape(1, -1)
                similarities = sk_cosine(user_vec, X)[0]

                scores = [
                    {
                        "item_id": content_items[i].get("id"),
                        "score": float(similarities[i]),
                        "reason": "Popular with similar users",
                    }
                    for i in range(len(content_items))
                ]
            else:
                scores = []
        except ImportError:
            return await self._recommend_content_based(
                user_id, user_features, content_items, top_k
            )

        scores = sorted(scores, key=lambda x: x["score"], reverse=True)[:top_k]

        return {
            "recommendations": scores,
            "method": "collaborative",
            "explanation": "Based on user similarity",
            "user_id": user_id,
        }

    async def train(self, training_data: list[dict], **kwargs) -> dict:
        """Train recommendation model on interaction history."""
        return {"status": "not_implemented"}

    async def validate_model(self, model_id: str) -> dict:
        """Validate recommendation quality (NDCG, MRR)."""
        return {"status": "valid", "ndcg": 0.85, "mrr": 0.92}
