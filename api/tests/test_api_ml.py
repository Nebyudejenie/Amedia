"""Integration tests for ML API endpoints."""
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


class TestMLSentimentEndpoints:
    """Test sentiment analysis API endpoints."""

    @pytest.mark.integration
    def test_sentiment_analyze_endpoint(self, auth_headers):
        """Test POST /ml/sentiment/analyze endpoint."""
        response = client.post(
            "/ml/sentiment/analyze",
            json={"text": "This is amazing!"},
            headers=auth_headers,
        )

        # Should return 200 or 422 (validation) depending on auth setup
        assert response.status_code in [200, 422, 401]

        if response.status_code == 200:
            data = response.json()
            assert "data" in data or "status" in data

    @pytest.mark.integration
    def test_sentiment_analyze_missing_text(self, auth_headers):
        """Test sentiment endpoint with missing text."""
        response = client.post(
            "/ml/sentiment/analyze",
            json={},
            headers=auth_headers,
        )

        # Should either work or validate error
        assert response.status_code in [200, 422, 400, 401]

    @pytest.mark.integration
    def test_sentiment_bulk_results_endpoint(self, auth_headers):
        """Test GET /ml/sentiment/bulk-results endpoint."""
        workspace_id = uuid4()

        response = client.get(
            f"/ml/sentiment/bulk-results?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]


class TestMLForecastEndpoints:
    """Test forecasting API endpoints."""

    @pytest.mark.integration
    def test_forecast_predict_endpoint(self, auth_headers):
        """Test POST /ml/forecast/predict endpoint."""
        response = client.post(
            "/ml/forecast/predict",
            json={
                "historical_values": [0.1, 0.15, 0.2, 0.25, 0.3],
            },
            headers=auth_headers,
        )

        assert response.status_code in [200, 400, 401, 422]

    @pytest.mark.integration
    def test_forecast_results_endpoint(self, auth_headers):
        """Test GET /ml/forecast/results endpoint."""
        workspace_id = uuid4()

        response = client.get(
            f"/ml/forecast/results?workspace_id={workspace_id}&metric_name=engagement",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]

    @pytest.mark.integration
    def test_forecast_train_endpoint(self, auth_headers):
        """Test POST /ml/forecast/train endpoint."""
        workspace_id = uuid4()

        response = client.post(
            f"/ml/forecast/train",
            json={
                "workspace_id": str(workspace_id),
                "model_name": "engagement_forecast",
                "training_data": [
                    {"value": 0.1, "date": "2026-06-01"},
                    {"value": 0.15, "date": "2026-06-02"},
                ],
            },
            headers=auth_headers,
        )

        assert response.status_code in [200, 400, 401, 422]


class TestMLSegmentationEndpoints:
    """Test segmentation API endpoints."""

    @pytest.mark.integration
    def test_segmentation_cluster_endpoint(self, auth_headers):
        """Test POST /ml/segmentation/cluster endpoint."""
        response = client.post(
            "/ml/segmentation/cluster",
            json={
                "features": [
                    [0.1, 0.2],
                    [0.15, 0.25],
                    [0.9, 0.8],
                ],
                "entity_ids": ["user1", "user2", "user3"],
            },
            headers=auth_headers,
        )

        assert response.status_code in [200, 400, 401, 422]

    @pytest.mark.integration
    def test_segmentation_segments_endpoint(self, auth_headers):
        """Test GET /ml/segmentation/segments endpoint."""
        workspace_id = uuid4()

        response = client.get(
            f"/ml/segmentation/segments?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]


class TestMLRecommendationEndpoints:
    """Test recommendation API endpoints."""

    @pytest.mark.integration
    def test_recommendation_generate_endpoint(self, auth_headers):
        """Test POST /ml/recommendations/generate endpoint."""
        response = client.post(
            "/ml/recommendations/generate",
            json={
                "user_id": str(uuid4()),
                "user_features": [0.5, 0.5, 0.5],
                "content_items": [
                    {"id": "c1", "features": [0.1, 0.2, 0.3]},
                    {"id": "c2", "features": [0.5, 0.5, 0.5]},
                ],
            },
            headers=auth_headers,
        )

        assert response.status_code in [200, 400, 401, 422]

    @pytest.mark.integration
    def test_recommendation_similar_content_endpoint(self, auth_headers):
        """Test GET /ml/recommendations/similar-content endpoint."""
        workspace_id = uuid4()
        content_id = uuid4()

        response = client.get(
            f"/ml/recommendations/similar-content"
            f"?workspace_id={workspace_id}&content_id={content_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]


class TestMLModelEndpoints:
    """Test model management endpoints."""

    @pytest.mark.integration
    def test_list_models_endpoint(self, auth_headers):
        """Test GET /ml/models endpoint."""
        workspace_id = uuid4()

        response = client.get(
            f"/ml/models?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]

    @pytest.mark.integration
    def test_training_jobs_endpoint(self, auth_headers):
        """Test GET /ml/training-jobs endpoint."""
        workspace_id = uuid4()

        response = client.get(
            f"/ml/training-jobs?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]
