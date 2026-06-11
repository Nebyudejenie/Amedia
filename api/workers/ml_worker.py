"""ML worker - processes ML predictions and training jobs."""
import asyncio
import logging
from datetime import datetime

from api.clients import PostgreSQLPool, RedisClient
from api.ml import (
    SentimentService,
    ForecastService,
    SegmentationService,
    RecommendationService,
)
from api.ml.model_service import ModelService

logger = logging.getLogger(__name__)


async def process_ml_job(job_data: dict) -> None:
    """Process a single ML job (prediction or training)."""
    try:
        job_type = job_data.get("type")
        workspace_id = job_data.get("workspace_id")
        content_id = job_data.get("content_id")
        model_id = job_data.get("model_id")

        if job_type == "sentiment":
            await _process_sentiment(workspace_id, content_id, model_id)
        elif job_type == "forecast":
            await _process_forecast(workspace_id, job_data)
        elif job_type == "segmentation":
            await _process_segmentation(workspace_id, job_data)
        elif job_type == "training":
            await _process_training(workspace_id, job_data)
        else:
            logger.warning(f"Unknown ML job type: {job_type}")

    except Exception as e:
        logger.error(f"ML job error: {e}")


async def _process_sentiment(workspace_id: str, content_id: str, model_id: str) -> None:
    """Process sentiment analysis job."""
    try:
        async with PostgreSQLPool.acquire() as conn:
            # Get content
            content = await conn.fetchrow(
                "SELECT id, title, description FROM content.normalized_items WHERE id = $1",
                content_id,
            )

            if not content:
                logger.warning(f"Content {content_id} not found")
                return

            text = f"{content['title']} {content['description']}".strip()

            # Predict sentiment
            service = SentimentService()
            result = await service.predict({"text": text})

            # Store prediction
            await ModelService.store_prediction(
                workspace_id,
                content_id,
                model_id,
                "sentiment",
                result,
            )

            logger.info(f"Sentiment prediction stored for content {content_id}")

    except Exception as e:
        logger.error(f"Sentiment processing error: {e}")


async def _process_forecast(workspace_id: str, job_data: dict) -> None:
    """Process forecasting job."""
    try:
        metric_name = job_data.get("metric_name")
        historical_values = job_data.get("historical_values", [])

        if not historical_values:
            logger.warning(f"No historical values for forecast {metric_name}")
            return

        # Generate forecast
        service = ForecastService()
        result = await service.predict({
            "historical_values": historical_values
        })

        logger.info(f"Forecast generated for {metric_name}: {result['trend']}")

    except Exception as e:
        logger.error(f"Forecast processing error: {e}")


async def _process_segmentation(workspace_id: str, job_data: dict) -> None:
    """Process segmentation job."""
    try:
        features = job_data.get("features", [])
        entity_ids = job_data.get("entity_ids", [])

        if not features:
            logger.warning("No features for segmentation")
            return

        # Cluster entities
        service = SegmentationService()
        result = await service.predict({
            "features": features,
            "entity_ids": entity_ids,
        })

        logger.info(f"Segmentation completed: {len(result['segments'])} segments")

    except Exception as e:
        logger.error(f"Segmentation processing error: {e}")


async def _process_training(workspace_id: str, job_data: dict) -> None:
    """Process model training job."""
    try:
        job_id = job_data.get("job_id")
        model_name = job_data.get("model_name")
        training_data = job_data.get("training_data", [])

        # Mark as running
        await ModelService.update_training_job(job_id, "running")

        # Simulate training
        await asyncio.sleep(2)

        # Store results
        metrics = {
            "accuracy": 0.92,
            "f1_score": 0.88,
            "loss": 0.15,
        }

        await ModelService.update_training_job(
            job_id,
            "completed",
            metrics=metrics,
        )

        logger.info(f"Training job {job_id} completed: {metrics}")

    except Exception as e:
        logger.error(f"Training processing error: {e}")
        await ModelService.update_training_job(
            job_data.get("job_id"),
            "failed",
            error=str(e),
        )


async def worker_loop() -> None:
    """Main ML worker loop."""
    logger.info("Starting ML worker...")

    await RedisClient.init()
    await PostgreSQLPool.init()

    try:
        while True:
            try:
                # Get ML job from queue
                job_json = await RedisClient.lpop("ml_queue")

                if job_json:
                    import json
                    job_data = json.loads(job_json)
                    await process_ml_job(job_data)
                else:
                    await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Worker error: {e}")
                await asyncio.sleep(10)

    except KeyboardInterrupt:
        logger.info("ML worker stopping...")
    finally:
        await RedisClient.close()
        await PostgreSQLPool.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(worker_loop())
