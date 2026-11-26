import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path

from groq import APIConnectionError, APIError, APIStatusError, APITimeoutError, Groq

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    segments: list[dict[str, object]]
    detected_language: str | None
    duration_seconds: float | None


class TranscriptionError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        self.code = code
        self.safe_message = message
        self.retryable = retryable
        super().__init__(message)


class GroqTranscriber:
    def __init__(self, api_key: str, model: str, timeout_seconds: float) -> None:
        self.model = model
        self._client = Groq(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        started = time.monotonic()
        try:
            with audio_path.open("rb") as audio_file:
                response = self._client.audio.transcriptions.create(
                    file=audio_file,
                    model=self.model,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                    temperature=0.0,
                )
        except OSError as exc:
            raise TranscriptionError(
                "audio_unavailable",
                "The stored audio could not be opened for transcription.",
                retryable=False,
            ) from exc
        except APITimeoutError as exc:
            logger.warning("Groq transcription timed out (model=%s)", self.model)
            raise TranscriptionError(
                "provider_timeout",
                "Groq transcription timed out.",
                retryable=True,
            ) from exc
        except APIConnectionError as exc:
            logger.warning("Groq transcription connection failed (model=%s)", self.model)
            raise TranscriptionError(
                "provider_connection",
                "Groq could not be reached. The transcription can be retried.",
                retryable=True,
            ) from exc
        except APIStatusError as exc:
            error = self._status_error(exc)
            logger.warning(
                "Groq transcription request failed (model=%s, status_code=%d, category=%s)",
                self.model,
                exc.status_code,
                error.code,
            )
            raise error from exc
        except APIError as exc:
            logger.warning(
                "Groq transcription request failed (model=%s, error_type=%s)",
                self.model,
                type(exc).__name__,
            )
            raise TranscriptionError(
                "provider_error",
                "Groq could not complete the transcription request.",
                retryable=True,
            ) from exc

        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            logger.warning("Groq returned an empty transcript (model=%s)", self.model)
            raise TranscriptionError(
                "empty_transcript",
                "Groq returned an empty transcript.",
                retryable=False,
            )

        segments = _extract_segments(getattr(response, "segments", None))
        language = getattr(response, "language", None)
        duration = getattr(response, "duration", None)
        logger.info(
            "Groq transcription completed (model=%s, elapsed_seconds=%.2f)",
            self.model,
            time.monotonic() - started,
        )
        return TranscriptionResult(
            text=text,
            segments=segments,
            detected_language=language if isinstance(language, str) else None,
            duration_seconds=(
                float(duration)
                if isinstance(duration, (int, float))
                and math.isfinite(float(duration))
                else None
            ),
        )

    @staticmethod
    def _status_error(error: APIStatusError) -> TranscriptionError:
        status = error.status_code
        if status in {401, 403}:
            return TranscriptionError(
                "provider_authentication",
                "Groq rejected the configured API credentials.",
                retryable=False,
            )
        if status == 429:
            return TranscriptionError(
                "provider_rate_limit",
                "Groq rate limits were reached. The transcription can be retried later.",
                retryable=True,
            )
        if status in {408, 409} or status >= 500:
            return TranscriptionError(
                "provider_unavailable",
                "Groq transcription is temporarily unavailable.",
                retryable=True,
            )
        return TranscriptionError(
            "provider_request",
            "Groq rejected the transcription request.",
            retryable=False,
        )


def _extract_segments(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []

    segments: list[dict[str, object]] = []
    for item in value:
        start = getattr(item, "start", None)
        end = getattr(item, "end", None)
        text = getattr(item, "text", None)
        if (
            isinstance(start, (int, float))
            and math.isfinite(float(start))
            and float(start) >= 0
            and isinstance(end, (int, float))
            and math.isfinite(float(end))
            and float(end) >= float(start)
            and isinstance(text, str)
        ):
            segments.append(
                {
                    "start": float(start),
                    "end": float(end),
                    "text": text,
                }
            )
    return segments
