"""Unit tests for ML services."""
import pytest
from uuid import uuid4

from ml import (
    SentimentService,
    ForecastService,
    SegmentationService,
    RecommendationService,
)
from ml.base_service import MLPredictionFailed


class TestSentimentService:
    """Test sentiment analysis service."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sentiment_positive_text(self):
        """Test sentiment analysis on positive text."""
        service = SentimentService()

        result = await service.predict({"text": "This is amazing! I love it!"})

        assert result["sentiment"] in ["positive", "neutral", "negative"]
        assert 0 <= result["confidence"] <= 1.0
        assert -1.0 <= result["score"] <= 1.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sentiment_negative_text(self):
        """Test sentiment analysis on negative text."""
        service = SentimentService()

        result = await service.predict({"text": "This is terrible and awful!"})

        assert result["sentiment"] in ["positive", "neutral", "negative"]
        assert result["score"] <= 0.5  # Should lean negative

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sentiment_neutral_text(self):
        """Test sentiment analysis on neutral text."""
        service = SentimentService()

        result = await service.predict({"text": "The sky is blue."})

        assert result["sentiment"] in ["positive", "neutral", "negative"]
        assert "confidence" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sentiment_empty_text_fails(self):
        """Test that empty text raises error."""
        service = SentimentService()

        with pytest.raises(MLPredictionFailed):
            await service.predict({"text": ""})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sentiment_long_text(self):
        """Test sentiment on long text."""
        service = SentimentService()
        long_text = "This is good. " * 100

        result = await service.predict({"text": long_text})

        assert "sentiment" in result
        assert "confidence" in result


class TestForecastService:
    """Test forecasting service."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_forecast_uptrend(self):
        """Test forecast on uptrending data."""
        service = ForecastService()
        historical = [0.1, 0.15, 0.2, 0.25, 0.3]

        result = await service.predict(
            {"historical_values": historical},
            forecast_days=7,
        )

        assert len(result["forecast"]) == 7
        assert result["trend"] in ["up", "down", "stable"]
        assert result["rmse"] >= 0
        assert len(result["confidence_interval"]) == 7

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_forecast_downtrend(self):
        """Test forecast on downtrending data."""
        service = ForecastService()
        historical = [0.5, 0.4, 0.3, 0.2, 0.1]

        result = await service.predict(
            {"historical_values": historical},
            forecast_days=5,
        )

        assert result["trend"] == "down"
        assert all(v >= 0 for v in result["forecast"])

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_forecast_insufficient_data_fails(self):
        """Test that insufficient data raises error."""
        service = ForecastService()

        with pytest.raises(MLPredictionFailed):
            await service.predict({"historical_values": [0.1]})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_forecast_custom_days(self):
        """Test forecast with custom number of days."""
        service = ForecastService()
        historical = [0.1, 0.15, 0.2, 0.25]

        for days in [1, 7, 14, 30]:
            result = await service.predict(
                {"historical_values": historical},
                forecast_days=days,
            )
            assert len(result["forecast"]) == days


class TestSegmentationService:
    """Test segmentation service."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_segmentation_basic(self):
        """Test basic K-means clustering."""
        service = SegmentationService()

        features = [
            [0.1, 0.2],
            [0.15, 0.25],
            [0.9, 0.8],
            [0.85, 0.75],
        ]
        entity_ids = ["user1", "user2", "user3", "user4"]

        result = await service.predict(
            {"features": features, "entity_ids": entity_ids},
            n_clusters=2,
        )

        assert "segments" in result
        assert len(result["segments"]) == 2
        assert all(s["size"] >= 0 for s in result["segments"])
        assert result["silhouette_score"] >= -1.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_segmentation_single_cluster(self):
        """Test single cluster."""
        service = SegmentationService()

        features = [[0.1, 0.2], [0.15, 0.25], [0.2, 0.3]]

        result = await service.predict(
            {"features": features},
            n_clusters=1,
        )

        assert len(result["segments"]) == 1
        assert result["segments"][0]["size"] == 3

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_segmentation_insufficient_data_fails(self):
        """Test that insufficient data raises error."""
        service = SegmentationService()

        with pytest.raises(MLPredictionFailed):
            await service.predict(
                {"features": [[0.1]]},
                n_clusters=5,
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_segmentation_entity_ids_mismatch(self):
        """Test with mismatched entity IDs."""
        service = SegmentationService()

        features = [[0.1, 0.2], [0.15, 0.25]]
        entity_ids = ["user1"]  # Only one ID for two features

        result = await service.predict(
            {"features": features, "entity_ids": entity_ids},
            n_clusters=1,
        )

        # Should auto-generate IDs
        assert "segments" in result


class TestRecommendationService:
    """Test recommendation service."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_recommendation_content_based(self):
        """Test content-based recommendations."""
        service = RecommendationService()

        user_features = [0.5, 0.6, 0.4]
        content_items = [
            {"id": "content1", "features": [0.5, 0.6, 0.4]},  # Exact match
            {"id": "content2", "features": [0.1, 0.2, 0.1]},  # Very different
            {"id": "content3", "features": [0.5, 0.5, 0.5]},  # Somewhat similar
        ]

        result = await service.predict(
            {
                "user_id": "user1",
                "user_features": user_features,
                "content_items": content_items,
            },
            method="content_based",
            top_k=2,
        )

        assert len(result["recommendations"]) <= 2
        assert all(0 <= r["score"] <= 1 for r in result["recommendations"])

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_recommendation_top_k(self):
        """Test top_k parameter."""
        service = RecommendationService()

        user_features = [0.5, 0.5]
        content_items = [
            {"id": f"content{i}", "features": [0.1 * i, 0.1 * i]}
            for i in range(10)
        ]

        result = await service.predict(
            {
                "user_id": "user1",
                "user_features": user_features,
                "content_items": content_items,
            },
            top_k=5,
        )

        assert len(result["recommendations"]) <= 5

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_recommendation_no_items_fails(self):
        """Test that no content items raises error."""
        service = RecommendationService()

        with pytest.raises(MLPredictionFailed):
            await service.predict(
                {
                    "user_id": "user1",
                    "user_features": [0.5, 0.5],
                    "content_items": [],
                }
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_recommendation_sorted_by_score(self):
        """Test that results are sorted by score descending."""
        service = RecommendationService()

        user_features = [0.5, 0.5]
        content_items = [
            {"id": "content1", "features": [0.1, 0.1]},
            {"id": "content2", "features": [0.5, 0.5]},
            {"id": "content3", "features": [0.9, 0.9]},
        ]

        result = await service.predict(
            {
                "user_id": "user1",
                "user_features": user_features,
                "content_items": content_items,
            }
        )

        scores = [r["score"] for r in result["recommendations"]]
        assert scores == sorted(scores, reverse=True)
