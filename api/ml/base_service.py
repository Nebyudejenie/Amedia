"""Abstract base class for all ML services."""
from abc import ABC, abstractmethod
from typing import Any
import logging

logger = logging.getLogger(__name__)


class MLServiceError(Exception):
    """Base exception for ML service errors."""


class MLModelNotFound(MLServiceError):
    """Model not found in registry."""


class MLPredictionFailed(MLServiceError):
    """Prediction failed."""


class MLTrainingFailed(MLServiceError):
    """Training failed."""


class MLServiceBase(ABC):
    """Abstract base for all ML services."""

    @abstractmethod
    async def predict(self, input_data: dict, **kwargs) -> dict:
        """
        Generate prediction from input data.

        Args:
            input_data: Model input (text, values, etc.)
            **kwargs: Service-specific parameters

        Returns:
            dict with prediction results and metadata
        """

    @abstractmethod
    async def train(self, training_data: list[dict], **kwargs) -> dict:
        """
        Train or fine-tune model on data.

        Args:
            training_data: List of training examples
            **kwargs: Training hyperparameters

        Returns:
            dict with training metrics
        """

    @abstractmethod
    async def validate_model(self, model_id: str) -> dict:
        """Validate model performance on test set."""

    async def get_model_info(self, model_id: str) -> dict:
        """Get model metadata and configuration."""
        return {}

    async def list_models(self, workspace_id: str) -> list[dict]:
        """List all available models for workspace."""
        return []
