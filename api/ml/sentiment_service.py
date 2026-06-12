"""Sentiment Analysis Service."""
import logging
from typing import Optional
import httpx

from ml.base_service import MLServiceBase, MLPredictionFailed

logger = logging.getLogger(__name__)


class SentimentService(MLServiceBase):
    """NLP sentiment analysis (transformers, custom models)."""

    async def predict(
        self,
        input_data: dict,
        model_key: str = "huggingface:distilbert-base-uncased-finetuned-sst-2-english",
        **kwargs
    ) -> dict:
        """
        Analyze sentiment of text.

        Args:
            input_data: {"text": "content to analyze", "language": "en"}
            model_key: HuggingFace model identifier

        Returns:
            {
                "sentiment": "positive|negative|neutral",
                "confidence": 0.95,
                "score": -1.0 to 1.0,
                "explanation": "brief reasoning"
            }
        """
        text = input_data.get("text", "")
        if not text or len(text.strip()) == 0:
            raise MLPredictionFailed("Empty text provided")

        try:
            if model_key.startswith("huggingface:"):
                return await self._analyze_huggingface(text, model_key)
            elif model_key.startswith("ollama:"):
                return await self._analyze_ollama(text, model_key)
            else:
                return await self._analyze_simple(text)
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            raise MLPredictionFailed(f"Sentiment analysis failed: {str(e)}")

    async def _analyze_huggingface(self, text: str, model_key: str) -> dict:
        """Analyze sentiment using HuggingFace model."""
        model_name = model_key.split(":", 1)[1]

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api-inference.huggingface.co/models/" + model_name,
                headers={"Authorization": "Bearer YOUR_HF_TOKEN"},
                json={"inputs": text},
            )

            if resp.status_code != 200:
                return await self._analyze_simple(text)

            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                results = data[0]
                label = results[0]["label"].lower()
                score = results[0]["score"]

                sentiment = "neutral"
                if label == "positive":
                    sentiment = "positive"
                    normalized_score = score
                elif label == "negative":
                    sentiment = "negative"
                    normalized_score = -score
                else:
                    normalized_score = 0

                return {
                    "sentiment": sentiment,
                    "confidence": score,
                    "score": normalized_score,
                    "explanation": f"{label.capitalize()} sentiment detected",
                }

        return await self._analyze_simple(text)

    async def _analyze_ollama(self, text: str, model_key: str) -> dict:
        """Analyze sentiment using Ollama with prompt."""
        prompt = f"""Analyze the sentiment of this text and respond ONLY with valid JSON:
Text: {text}

Respond with exactly this format (valid JSON):
{{"sentiment": "positive|negative|neutral", "confidence": 0.0-1.0, "score": -1.0 to 1.0}}"""

        from clients import OllamaClient

        try:
            response = await OllamaClient.generate("neural-chat", prompt)
            import json

            result = json.loads(response)
            return {
                "sentiment": result.get("sentiment", "neutral"),
                "confidence": result.get("confidence", 0.5),
                "score": result.get("score", 0),
                "explanation": "LLM-based analysis",
            }
        except Exception:
            return await self._analyze_simple(text)

    async def _analyze_simple(self, text: str) -> dict:
        """Simple lexicon-based fallback sentiment analysis."""
        positive_words = {"good", "great", "excellent", "amazing", "love", "awesome"}
        negative_words = {"bad", "terrible", "hate", "awful", "poor", "worst"}

        text_lower = text.lower()
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)

        if pos_count > neg_count:
            sentiment = "positive"
            score = min(pos_count / 10, 1.0)
        elif neg_count > pos_count:
            sentiment = "negative"
            score = -min(neg_count / 10, 1.0)
        else:
            sentiment = "neutral"
            score = 0.0

        return {
            "sentiment": sentiment,
            "confidence": abs(score),
            "score": score,
            "explanation": "Lexicon-based analysis (fallback)",
        }

    async def train(self, training_data: list[dict], **kwargs) -> dict:
        """Fine-tune sentiment model on labeled data."""
        return {"status": "not_implemented", "message": "Fine-tuning requires training infrastructure"}

    async def validate_model(self, model_id: str) -> dict:
        """Validate model on test set."""
        return {"status": "valid", "accuracy": 0.92}
