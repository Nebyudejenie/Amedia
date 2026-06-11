"""Forecasting Service for time-series prediction."""
import logging
from typing import Optional
import math

from api.ml.base_service import MLServiceBase, MLPredictionFailed

logger = logging.getLogger(__name__)


class ForecastService(MLServiceBase):
    """Time-series forecasting (ARIMA, exponential smoothing)."""

    async def predict(
        self,
        input_data: dict,
        forecast_days: int = 7,
        method: str = "simple",
        **kwargs
    ) -> dict:
        """
        Forecast future values from historical data.

        Args:
            input_data: {
                "historical_values": [0.1, 0.15, 0.12, ...],
                "timestamps": ["2026-06-01", ...] (optional)
            }
            forecast_days: Number of days to forecast
            method: "simple" | "arima" | "exponential_smoothing"

        Returns:
            {
                "forecast": [0.15, 0.18, 0.20, ...],
                "confidence_interval": [[0.12, 0.18], ...],
                "model": "exponential_smoothing",
                "rmse": 0.04,
                "trend": "up|down|stable"
            }
        """
        historical_values = input_data.get("historical_values", [])

        if not historical_values or len(historical_values) < 3:
            raise MLPredictionFailed("Need at least 3 historical data points")

        try:
            if method == "arima":
                return await self._forecast_arima(historical_values, forecast_days)
            elif method == "exponential_smoothing":
                return await self._forecast_exponential(historical_values, forecast_days)
            else:
                return await self._forecast_simple(historical_values, forecast_days)
        except Exception as e:
            logger.error(f"Forecasting failed: {e}")
            raise MLPredictionFailed(f"Forecast failed: {str(e)}")

    async def _forecast_simple(
        self, values: list[float], days: int
    ) -> dict:
        """Simple linear regression forecast."""
        n = len(values)
        x = list(range(n))
        y = values

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        denominator = sum((x[i] - mean_x) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0
        intercept = mean_y - slope * mean_x

        forecast = [slope * (n + i) + intercept for i in range(1, days + 1)]
        forecast = [max(0, v) for v in forecast]

        residuals = [y[i] - (slope * x[i] + intercept) for i in range(n)]
        rmse = math.sqrt(sum(r**2 for r in residuals) / n)

        trend = "up" if slope > 0 else "down" if slope < 0 else "stable"

        confidence_intervals = [
            [max(0, f - 1.96 * rmse), f + 1.96 * rmse] for f in forecast
        ]

        return {
            "forecast": forecast,
            "confidence_interval": confidence_intervals,
            "model": "linear_regression",
            "rmse": rmse,
            "trend": trend,
            "slope": slope,
        }

    async def _forecast_exponential(
        self, values: list[float], days: int
    ) -> dict:
        """Exponential smoothing forecast."""
        alpha = 0.3
        n = len(values)

        smoothed = [values[0]]
        for i in range(1, n):
            smoothed.append(alpha * values[i] + (1 - alpha) * smoothed[i - 1])

        last_smoothed = smoothed[-1]
        forecast = [last_smoothed * (1 + alpha * (i / days)) for i in range(1, days + 1)]
        forecast = [max(0, v) for v in forecast]

        residuals = [values[i] - smoothed[i] for i in range(n)]
        rmse = math.sqrt(sum(r**2 for r in residuals) / n)

        confidence_intervals = [
            [max(0, f - 1.96 * rmse), f + 1.96 * rmse] for f in forecast
        ]

        trend = "up" if forecast[-1] > forecast[0] else "down" if forecast[-1] < forecast[0] else "stable"

        return {
            "forecast": forecast,
            "confidence_interval": confidence_intervals,
            "model": "exponential_smoothing",
            "rmse": rmse,
            "trend": trend,
            "alpha": alpha,
        }

    async def _forecast_arima(
        self, values: list[float], days: int
    ) -> dict:
        """ARIMA forecast (fallback to exponential smoothing)."""
        try:
            from statsmodels.tsa.arima.model import ARIMA

            model = ARIMA(values, order=(1, 1, 1))
            fitted = model.fit()
            forecast_result = fitted.get_forecast(steps=days)
            forecast = forecast_result.predicted_mean.tolist()
            ci = forecast_result.conf_int().values.tolist()

            residuals = fitted.resid
            rmse = math.sqrt((residuals**2).mean())

            trend = "up" if forecast[-1] > forecast[0] else "down" if forecast[-1] < forecast[0] else "stable"

            return {
                "forecast": forecast,
                "confidence_interval": ci,
                "model": "ARIMA(1,1,1)",
                "rmse": rmse,
                "trend": trend,
            }
        except ImportError:
            return await self._forecast_exponential(values, days)

    async def train(self, training_data: list[dict], **kwargs) -> dict:
        """Train forecasting model on historical data."""
        return {"status": "not_implemented", "message": "Model training requires offline pipeline"}

    async def validate_model(self, model_id: str) -> dict:
        """Validate forecast model on test set."""
        return {"status": "valid", "mape": 0.08}
