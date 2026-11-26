import logging
import time
from typing import TypeVar

import httpx2
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

logger = logging.getLogger(__name__)

SchemaModel = TypeVar("SchemaModel", bound=BaseModel)


class GeminiProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        self.code = code
        self.safe_message = message
        self.retryable = retryable
        super().__init__(message)


class GeminiJsonGenerator:
    def __init__(self, api_key: str, model: str, timeout_seconds: float) -> None:
        self.model = model
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout_seconds * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    def generate_json(self, prompt: str, schema: type[SchemaModel]) -> str:
        started = time.monotonic()
        try:
            response = self._client.interactions.create(
                model=self.model,
                input=prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": schema.model_json_schema(),
                },
                store=False,
            )
        except httpx2.TimeoutException as exc:
            logger.warning("Gemini request timed out (model=%s)", self.model)
            raise GeminiProviderError(
                "provider_timeout",
                "Gemini content generation timed out.",
                retryable=True,
            ) from exc
        except httpx2.RequestError as exc:
            logger.warning("Gemini connection failed (model=%s)", self.model)
            raise GeminiProviderError(
                "provider_connection",
                "Gemini could not be reached. The request can be retried.",
                retryable=True,
            ) from exc
        except errors.APIError as exc:
            error = self._status_error(exc)
            logger.warning(
                "Gemini request failed (model=%s, status_code=%d, category=%s)",
                self.model,
                exc.code,
                error.code,
            )
            raise error from exc

        output = getattr(response, "output_text", None)
        if not isinstance(output, str) or not output.strip():
            raise GeminiProviderError(
                "empty_response",
                "Gemini returned no structured content.",
                retryable=True,
            )
        logger.info(
            "Gemini request completed (model=%s, elapsed_seconds=%.2f)",
            self.model,
            time.monotonic() - started,
        )
        return output

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _status_error(error: errors.APIError) -> GeminiProviderError:
        status = error.code
        if status in {401, 403}:
            return GeminiProviderError(
                "provider_authentication",
                "Gemini rejected the configured API credentials.",
                retryable=False,
            )
        if status == 429:
            return GeminiProviderError(
                "provider_rate_limit",
                "Gemini rate limits were reached. Content generation can be retried later.",
                retryable=True,
            )
        if status in {408, 409} or status >= 500:
            return GeminiProviderError(
                "provider_unavailable",
                "Gemini content generation is temporarily unavailable.",
                retryable=True,
            )
        return GeminiProviderError(
            "provider_request",
            "Gemini rejected the content generation request.",
            retryable=False,
        )
