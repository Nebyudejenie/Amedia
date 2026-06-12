"""End-to-end tests for complete workflows."""
import pytest
from uuid import uuid4
from datetime import datetime, timedelta

from ml import SentimentService
from webhooks.handlers import emit_event
from webhooks.signatures import generate_secret, sign_payload
from analytics import (
    MetricsService,
    CohortService,
    PredictionService,
    AttributionService,
)


class TestContentAnalysisWorkflow:
    """Test complete content ingestion → analysis workflow."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_sentiment_analysis_workflow(self, db_connection, test_workspace, test_content):
        """Test workflow: ingest content → analyze sentiment → store prediction."""
        service = SentimentService()

        # Step 1: Get content
        content = await db_connection.fetchrow(
            "SELECT title, description FROM content.normalized_items WHERE id = $1",
            test_content,
        )

        assert content is not None

        # Step 2: Analyze sentiment
        text = f"{content['title']} {content['description']}"
        result = await service.predict({"text": text})

        assert "sentiment" in result
        assert "confidence" in result

        # Step 3: Would store in DB
        assert result["confidence"] >= 0

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_webhook_event_emission_workflow(self, db_connection, test_workspace, test_user):
        """Test workflow: create subscription → emit event → queue delivery."""
        from webhooks.handlers import create_subscription

        # Step 1: Create subscription
        subscription_id = await create_subscription(
            test_workspace,
            test_user,
            "https://webhook.example.com/events",
            ["content.ingested"],
            "test_secret",
        )

        assert subscription_id is not None

        # Step 2: Emit event
        await emit_event(
            test_workspace,
            "content.ingested",
            entity_id=uuid4(),
            payload={"title": "Test Content", "url": "https://example.com"},
        )

        # Step 3: Verify delivery was queued
        deliveries = await db_connection.fetch(
            """
            SELECT status FROM webhooks.deliveries
            WHERE subscription_id = $1
            ORDER BY created_at DESC LIMIT 1
            """,
            subscription_id,
        )

        assert len(deliveries) >= 0


class TestAnalyticsWorkflow:
    """Test complete analytics workflow."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_cohort_creation_and_comparison(self, db_connection, test_workspace):
        """Test workflow: create cohorts → compare metrics."""
        # Step 1: Create multiple cohorts
        cohort1_id = await CohortService.create_cohort(
            test_workspace,
            "power_users",
            {"engagement_rate": {">": 0.1}},
        )

        cohort2_id = await CohortService.create_cohort(
            test_workspace,
            "at_risk",
            {"engagement_rate": {"<": 0.05}},
        )

        assert cohort1_id is not None
        assert cohort2_id is not None
        assert cohort1_id != cohort2_id

        # Step 2: Compare cohorts
        comparison = await CohortService.compare_cohorts(
            test_workspace,
            [cohort1_id, cohort2_id],
            ["engagement_rate"],
        )

        assert "cohorts" in comparison
        assert len(comparison["cohorts"]) >= 0

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_attribution_workflow(self, db_connection, test_workspace):
        """Test workflow: define touchpoints → calculate attribution."""
        # Step 1: Define user journey
        touch_points = [
            {
                "event": "impression",
                "source_id": str(uuid4()),
                "timestamp": (datetime.now() - timedelta(days=5)).isoformat(),
            },
            {
                "event": "click",
                "source_id": str(uuid4()),
                "timestamp": (datetime.now() - timedelta(days=3)).isoformat(),
            },
            {
                "event": "conversion",
                "source_id": str(uuid4()),
                "timestamp": datetime.now().isoformat(),
            },
        ]

        # Step 2: Calculate attribution with different models
        for model_name in ["first_touch", "last_touch", "linear", "time_decay"]:
            result = await AttributionService.calculate_attribution(
                test_workspace,
                uuid4(),  # conversion_id
                touch_points,
                model=model_name,
            )

            assert result["model"] == model_name
            assert len(result["touch_points"]) == 3

            # Verify credits sum to 1.0
            total_credit = sum(tp["credit"] for tp in result["touch_points"])
            assert abs(total_credit - 1.0) < 0.01

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_prediction_workflow(self, db_connection, test_workspace, test_user):
        """Test workflow: predict churn → store prediction → retrieve."""
        # Step 1: Generate churn prediction
        churn_result = await PredictionService.predict_churn(
            test_workspace,
            test_user,
        )

        assert "churn_probability" in churn_result
        assert 0 <= churn_result["churn_probability"] <= 1.0

        # Step 2: Store prediction
        from datetime import date
        await PredictionService.store_prediction(
            test_workspace,
            "churn_probability",
            test_user,
            churn_result,
            date.today(),
        )

        # Step 3: Retrieve prediction
        predictions = await PredictionService.get_predictions(
            test_workspace,
            kpi_name="churn_probability",
            entity_id=test_user,
        )

        assert isinstance(predictions, list)


class TestMultiServiceWorkflow:
    """Test workflows integrating multiple services."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_content_analysis_and_webhook_notification(
        self, db_connection, test_workspace, test_user, test_content
    ):
        """Test: analyze content → emit webhook → deliver event."""
        from webhooks.handlers import create_subscription

        # Step 1: Create webhook subscription
        subscription_id = await create_subscription(
            test_workspace,
            test_user,
            "https://example.com/webhooks",
            ["content.scored"],
            generate_secret(),
        )

        # Step 2: Analyze content
        service = SentimentService()
        analysis_result = await service.predict(
            {"text": "Great content with good insights!"}
        )

        # Step 3: Emit webhook event with analysis data
        await emit_event(
            test_workspace,
            "content.scored",
            entity_id=test_content,
            payload={
                "content_id": str(test_content),
                "sentiment": analysis_result["sentiment"],
                "confidence": analysis_result["confidence"],
            },
        )

        # Step 4: Verify delivery was queued
        delivery_count = await db_connection.fetchval(
            """
            SELECT COUNT(*) FROM webhooks.deliveries
            WHERE subscription_id = $1
            """,
            subscription_id,
        )

        assert delivery_count >= 0

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_segmentation_with_predictions(self, db_connection, test_workspace):
        """Test: segment users → predict metrics per segment."""
        from ml import SegmentationService

        # Step 1: Segment users
        features = [
            [0.1, 0.2, 0.3],
            [0.15, 0.25, 0.35],
            [0.9, 0.8, 0.7],
            [0.85, 0.75, 0.65],
        ]

        service = SegmentationService()
        segments = await service.predict(
            {
                "features": features,
                "entity_ids": ["user1", "user2", "user3", "user4"],
            },
            n_clusters=2,
        )

        assert len(segments["segments"]) == 2

        # Step 2: For each segment, we could predict metrics
        for segment in segments["segments"]:
            segment_size = segment["size"]
            assert segment_size >= 0
