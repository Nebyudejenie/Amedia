"""Analytics API endpoints."""
from uuid import UUID
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user, TokenData, require_role
from analytics import (
    MetricsService,
    CohortService,
    AttributionService,
    PredictionService,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


# ============================================================================
# Custom Metrics
# ============================================================================


@router.get("/metrics")
async def list_metrics(
    workspace_id: UUID,
    token: TokenData = Depends(get_current_user),
):
    """List custom metrics."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    return {"metrics": []}


@router.post("/metrics")
async def create_metric(
    workspace_id: UUID,
    name: str,
    definition: str,
    metric_type: str,
    dimension: Optional[str] = None,
    token: TokenData = Depends(require_role("owner", "admin")),
):
    """Create custom metric."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        metric_id = await MetricsService.create_metric(
            UUID(token.workspace_id),
            name,
            definition,
            metric_type,
            dimension,
        )
        return {"metric_id": metric_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/{metric_id}/data")
async def get_metric_data(
    workspace_id: UUID,
    metric_id: UUID,
    start_date: date,
    end_date: date,
    dimension: Optional[str] = None,
    token: TokenData = Depends(get_current_user),
):
    """Get metric data with filters."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        result = await MetricsService.calculate_metric(
            UUID(token.workspace_id),
            metric_id,
            start_date,
            end_date,
            dimension=dimension,
        )
        return {"metric": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/metrics/{metric_id}")
async def delete_metric(
    workspace_id: UUID,
    metric_id: UUID,
    token: TokenData = Depends(require_role("owner", "admin")),
):
    """Delete metric."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        await MetricsService.delete_metric(UUID(token.workspace_id), metric_id)
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Cohort Analysis
# ============================================================================


@router.get("/cohorts")
async def list_cohorts(
    workspace_id: UUID,
    token: TokenData = Depends(get_current_user),
):
    """List user cohorts."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        cohorts = await CohortService.list_cohorts(UUID(token.workspace_id))
        return {"cohorts": cohorts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cohorts")
async def create_cohort(
    workspace_id: UUID,
    name: str,
    criteria: dict,
    token: TokenData = Depends(get_current_user),
):
    """Create cohort based on criteria."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        cohort_id = await CohortService.create_cohort(
            UUID(token.workspace_id),
            name,
            criteria,
        )
        return {"cohort_id": cohort_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cohorts/{cohort_id}/metrics")
async def get_cohort_metrics(
    workspace_id: UUID,
    cohort_id: UUID,
    metric_names: list[str],
    token: TokenData = Depends(get_current_user),
):
    """Get cohort performance vs baseline."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        result = await CohortService.compare_cohorts(
            UUID(token.workspace_id),
            [cohort_id],
            metric_names,
        )
        return {"comparison": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/cohorts/{cohort_id}")
async def update_cohort(
    workspace_id: UUID,
    cohort_id: UUID,
    name: Optional[str] = None,
    criteria: Optional[dict] = None,
    token: TokenData = Depends(require_role("owner", "admin")),
):
    """Update cohort."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        await CohortService.update_cohort(
            UUID(token.workspace_id),
            cohort_id,
            name=name,
            criteria=criteria,
        )
        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Attribution
# ============================================================================


@router.get("/attribution")
async def get_attribution_report(
    workspace_id: UUID,
    conversion_id: UUID,
    token: TokenData = Depends(get_current_user),
):
    """Multi-touch attribution report."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        attribution = await AttributionService.get_attribution(
            UUID(token.workspace_id),
            conversion_id,
        )
        return {"attribution": attribution}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/attribution/model")
async def change_attribution_model(
    workspace_id: UUID,
    conversion_id: UUID,
    model: str,
    token: TokenData = Depends(get_current_user),
):
    """Change attribution model."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    if model not in AttributionService.MODELS:
        raise HTTPException(status_code=400, detail="Unknown model")

    try:
        models = await AttributionService.compare_models(
            UUID(token.workspace_id),
            conversion_id,
        )
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Predictions
# ============================================================================


@router.get("/predictions")
async def get_predictions(
    workspace_id: UUID,
    kpi_name: Optional[str] = None,
    limit: int = 50,
    token: TokenData = Depends(get_current_user),
):
    """Get predictive KPI forecasts."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        predictions = await PredictionService.get_predictions(
            UUID(token.workspace_id),
            kpi_name=kpi_name,
            limit=limit,
        )
        return {"predictions": predictions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictions/churn")
async def predict_churn(
    workspace_id: UUID,
    user_id: UUID,
    token: TokenData = Depends(get_current_user),
):
    """Predict churn risk."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        prediction = await PredictionService.predict_churn(
            UUID(token.workspace_id),
            user_id,
        )
        return {"prediction": prediction}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictions/ltv")
async def predict_ltv(
    workspace_id: UUID,
    user_id: UUID,
    token: TokenData = Depends(get_current_user),
):
    """Predict lifetime value."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        prediction = await PredictionService.predict_ltv(
            UUID(token.workspace_id),
            user_id,
        )
        return {"prediction": prediction}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Dashboard
# ============================================================================


@router.get("/dashboard")
async def get_dashboard(
    workspace_id: UUID,
    token: TokenData = Depends(get_current_user),
):
    """Get all metrics for dashboard (cached)."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    return {
        "metrics": [],
        "cohorts": [],
        "predictions": [],
        "cached_at": None,
    }


@router.post("/dashboard/refresh")
async def refresh_dashboard(
    workspace_id: UUID,
    token: TokenData = Depends(require_role("owner", "admin")),
):
    """Force recompute dashboard metrics."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    return {"status": "refreshing"}
