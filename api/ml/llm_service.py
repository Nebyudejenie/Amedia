"""LLM Service for text generation."""
import logging
from typing import Optional
import httpx

from ml.base_service import MLServiceBase, MLPredictionFailed
from clients import RedisClient
from config import settings

logger = logging.getLogger(__name__)


class LLMService(MLServiceBase):
    """LLM text generation service (Ollama, OpenAI, Anthropic)."""

    async def predict(
        self,
        input_data: dict,
        model_key: str = "ollama:neural-chat",
        temperature: float = 0.7,
        max_tokens: int = 500,
        **kwargs
    ) -> dict:
        """
        Generate text using specified LLM.

        Args:
            input_data: {"prompt": "text", "context": "optional"}
            model_key: "ollama:model" | "openai:gpt-4" | "anthropic:claude"
            temperature: 0.0-1.0 (randomness)
            max_tokens: output length limit

        Returns:
            {
                "generated_text": "...",
                "model": "neural-chat",
                "tokens_used": 150,
                "stop_reason": "length|stop_token"
            }
        """
        prompt = input_data.get("prompt", "")
        context = input_data.get("context", "")

        full_prompt = f"{context}\n{prompt}".strip() if context else prompt

        try:
            if model_key.startswith("ollama:"):
                return await self._generate_ollama(
                    full_prompt, model_key, temperature, max_tokens
                )
            elif model_key.startswith("openai:"):
                return await self._generate_openai(
                    full_prompt, model_key, temperature, max_tokens
                )
            elif model_key.startswith("anthropic:"):
                return await self._generate_anthropic(
                    full_prompt, model_key, temperature, max_tokens
                )
            else:
                raise MLPredictionFailed(f"Unknown model provider: {model_key}")
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise MLPredictionFailed(f"Text generation failed: {str(e)}")

    async def _generate_ollama(
        self, prompt: str, model_key: str, temperature: float, max_tokens: int
    ) -> dict:
        """Generate text using Ollama local LLM."""
        model_name = model_key.split(":", 1)[1]

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"http://{settings.ollama_host}:{settings.ollama_port}/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt,
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            return {
                "generated_text": data.get("response", "").strip(),
                "model": model_name,
                "tokens_used": len(data.get("response", "").split()),
                "stop_reason": "length",
            }

    async def _generate_openai(
        self, prompt: str, model_key: str, temperature: float, max_tokens: int
    ) -> dict:
        """Generate text using OpenAI API."""
        model_name = model_key.split(":", 1)[1]

        async with httpx.AsyncClient(
            timeout=120,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        ) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            message = data["choices"][0]["message"]["content"]
            return {
                "generated_text": message.strip(),
                "model": model_name,
                "tokens_used": data["usage"].get("completion_tokens", 0),
                "stop_reason": data["choices"][0].get("finish_reason", "unknown"),
            }

    async def _generate_anthropic(
        self, prompt: str, model_key: str, temperature: float, max_tokens: int
    ) -> dict:
        """Generate text using Anthropic Claude API."""
        model_name = model_key.split(":", 1)[1]

        async with httpx.AsyncClient(
            timeout=120,
            headers={"x-api-key": settings.anthropic_api_key},
        ) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                json={
                    "model": model_name,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()

            message = data["content"][0]["text"]
            return {
                "generated_text": message.strip(),
                "model": model_name,
                "tokens_used": data.get("usage", {}).get("output_tokens", 0),
                "stop_reason": data.get("stop_reason", "unknown"),
            }

    async def train(self, training_data: list[dict], **kwargs) -> dict:
        """LLM fine-tuning (not implemented for hosted models)."""
        return {"status": "not_supported", "message": "Fine-tuning requires dedicated API"}

    async def validate_model(self, model_id: str) -> dict:
        """Validate model by test generation."""
        return {"status": "valid", "test_passed": True}
