"""ML Services API endpoints."""
from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_current_user, TokenData, require_role
from api.ml import (
    LLMService,
    ForecastService,
    SegmentationService,
    SentimentService,
    RecommendationService,
)
from api.ml.model_service import ModelService
from api.ml.base_service import MLServiceError, MLPredictionFailed

router = APIRouter(prefix="/ml", tags=["ML Services"])


class PredictionRequest:
    pass


# ============================================================================
# Sentiment Analysis
# ============================================================================


@router.post("/sentiment/analyze")
async def analyze_sentiment(
    input_data: dict,
    model_key: str = "huggingface:distilbert-base-uncased-finetuned-sst-2-english",
    token: TokenData = Depends(get_current_user),
):
    """Analyze sentiment of text."""
    try:
        service = SentimentService()
        result = await service.predict(input_data, model_key=model_key)
        return {"data": result, "status": "success"}
    except MLPredictionFailed as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ML service error: {str(e)}")


@router.get("/sentiment/bulk-results")
async def get_bulk_sentiment_results(
    workspace_id: UUID,
    limit: int = 50,
    offset: int = 0,
    token: TokenData = Depends(get_current_user),
):
    """Retrieve cached sentiment predictions."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    return {"data": [], "total": 0, "limit": limit, "offset": offset}


# ============================================================================
# Forecasting
# ============================================================================


@router.post("/forecast/predict")
async def forecast_values(
    input_data: dict,
    forecast_days: int = 7,
    method: str = "simple",
    token: TokenData = Depends(get_current_user),
):
    """Generate time-series forecast."""
    try:
        service = ForecastService()
        result = await service.predict(
            input_data, forecast_days=forecast_days, method=method
        )
        return {"data": result, "status": "success"}
    except MLPredictionFailed as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ML service error: {str(e)}")


@router.get("/forecast/results")
async def get_forecast_results(
    workspace_id: UUID,
    metric_name: str,
    days: int = 30,
    token: TokenData = Depends(get_current_user),
):
    """Retrieve forecast results."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    return {"metric": metric_name, "days": days, "forecast": []}


@router.post("/forecast/train")
async def train_forecast_model(
    workspace_id: UUID,
    model_name: str,
    training_data: list[dict],
    token: TokenData = Depends(require_role("owner", "admin")),
):
    """Start forecast model training job."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        job_id = await ModelService.create_training_job(
            UUID(token.workspace_id), model_name, {"method": "arima"}
        )
        return {"job_id": job_id, "status": "queued"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Segmentation
# ============================================================================


@router.post("/segmentation/cluster")
async def cluster_entities(
    input_data: dict,
    n_clusters: int = 3,
    method: str = "kmeans",
    token: TokenData = Depends(get_current_user),
):
    """Cluster entities into segments."""
    try:
        service = SegmentationService()
        result = await service.predict(
            input_data, n_clusters=n_clusters, method=method
        )
        return {"data": result, "status": "success"}
    except MLPredictionFailed as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ML service error: {str(e)}")


@router.get("/segmentation/segments")
async def list_segments(
    workspace_id: UUID,
    token: TokenData = Depends(get_current_user),
):
    """List user segments."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    return {"segments": []}


@router.put("/segmentation/segments/{segment_id}")
async def update_segment(
    workspace_id: UUID,
    segment_id: str,
    segment_data: dict,
    token: TokenData = Depends(require_role("owner", "admin")),
):
    """Update segment configuration."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    return {"segment_id": segment_id, "status": "updated"}


# ============================================================================
# Recommendations
# ============================================================================


@router.post("/recommendations/generate")
async def generate_recommendations(
    input_data: dict,
    method: str = "content_based",
    top_k: int = 5,
    token: TokenData = Depends(get_current_user),
):
    """Generate content recommendations."""
    try:
        service = RecommendationService()
        result = await service.predict(
            input_data, method=method, top_k=top_k
        )
        return {"data": result, "status": "success"}
    except MLPredictionFailed as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ML service error: {str(e)}")


@router.get("/recommendations/similar-content")
async def get_similar_content(
    workspace_id: UUID,
    content_id: UUID,
    limit: int = 5,
    token: TokenData = Depends(get_current_user),
):
    """Find similar content items."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    return {"content_id": content_id, "similar": []}


# ============================================================================
# Model Management
# ============================================================================


@router.get("/models")
async def list_models(
    workspace_id: UUID,
    model_type: Optional[str] = None,
    token: TokenData = Depends(get_current_user),
):
    """List available models."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        models = await ModelService.list_models(
            UUID(token.workspace_id), model_type=model_type
        )
        return {"models": models, "count": len(models)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/{model_id}")
async def get_model(
    workspace_id: UUID,
    model_id: UUID,
    token: TokenData = Depends(get_current_user),
):
    """Get model details."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        model = await ModelService.get_model(UUID(token.workspace_id), model_id)
        return {"model": model}
    except MLServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/{model_id}/validate")
async def validate_model(
    workspace_id: UUID,
    model_id: UUID,
    token: TokenData = Depends(require_role("owner", "admin")),
):
    """Validate model performance."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        service = SentimentService()
        result = await service.validate_model(str(model_id))
        return {"validation": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/models/{model_id}")
async def delete_model(
    workspace_id: UUID,
    model_id: UUID,
    token: TokenData = Depends(require_role("owner", "admin")),
):
    """Deprecate model."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        await ModelService.deprecate_model(UUID(token.workspace_id), model_id)
        return {"status": "deprecated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Training Jobs
# ============================================================================


@router.get("/training-jobs")
async def list_training_jobs(
    workspace_id: UUID,
    token: TokenData = Depends(get_current_user),
):
    """List training jobs."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    return {"jobs": []}


@router.post("/training-jobs")
async def create_training_job(
    workspace_id: UUID,
    model_name: str,
    training_data: list[dict],
    token: TokenData = Depends(require_role("owner", "admin")),
):
    """Create new training job."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        job_id = await ModelService.create_training_job(
            UUID(token.workspace_id), model_name, {}
        )
        return {"job_id": job_id, "status": "queued"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/training-jobs/{job_id}")
async def get_training_job(
    workspace_id: UUID,
    job_id: UUID,
    token: TokenData = Depends(get_current_user),
):
    """Get training job status."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    return {"job_id": job_id, "status": "running"}
