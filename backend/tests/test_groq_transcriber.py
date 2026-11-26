from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from groq import APIStatusError, APITimeoutError

from backend.app.providers import groq_transcriber
from backend.app.providers.groq_transcriber import (
    GroqTranscriber,
    TranscriptionError,
)


def test_groq_request_preserves_segments_and_does_not_force_language(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "lesson.wav"
    audio_path.write_bytes(b"test audio")
    response = SimpleNamespace(
        text="తెలుగు English",
        segments=[
            SimpleNamespace(start=0.1, end=2.5, text="తెలుగు English"),
            SimpleNamespace(start=3.0, end=2.0, text="invalid segment"),
        ],
        language="te",
        duration=2.5,
    )
    calls: list[dict[str, object]] = []

    class FakeTranscriptions:
        def create(self, **kwargs: object) -> SimpleNamespace:
            calls.append(kwargs)
            assert not kwargs["file"].closed
            return response

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["timeout"] == 20
            assert kwargs["max_retries"] == 0
            self.audio = SimpleNamespace(transcriptions=FakeTranscriptions())

    monkeypatch.setattr(groq_transcriber, "Groq", FakeClient)
    transcriber = GroqTranscriber("test-key", "whisper-large-v3-turbo", 20)
    result = transcriber.transcribe(audio_path)

    assert result.text == "తెలుగు English"
    assert result.segments == [{"start": 0.1, "end": 2.5, "text": "తెలుగు English"}]
    assert result.detected_language == "te"
    assert result.duration_seconds == 2.5
    assert calls[0]["model"] == "whisper-large-v3-turbo"
    assert calls[0]["response_format"] == "verbose_json"
    assert calls[0]["timestamp_granularities"] == ["segment"]
    assert calls[0]["temperature"] == 0.0
    assert "language" not in calls[0]
    assert calls[0]["file"].closed


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (401, "provider_authentication", False),
        (429, "provider_rate_limit", True),
        (503, "provider_unavailable", True),
        (400, "provider_request", False),
    ],
)
def test_groq_status_errors_are_safe_and_classified(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    status_code: int,
    expected_code: str,
    retryable: bool,
) -> None:
    audio_path = tmp_path / "lesson.wav"
    audio_path.write_bytes(b"test audio")
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/audio/transcriptions")
    response = httpx.Response(status_code, request=request)
    status_error = APIStatusError("secret upstream message", response=response, body=None)

    class FakeTranscriptions:
        def create(self, **kwargs: object) -> None:
            del kwargs
            raise status_error

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            del kwargs
            self.audio = SimpleNamespace(transcriptions=FakeTranscriptions())

    monkeypatch.setattr(groq_transcriber, "Groq", FakeClient)
    transcriber = GroqTranscriber("test-key", "whisper-large-v3-turbo", 20)

    with pytest.raises(TranscriptionError) as raised:
        transcriber.transcribe(audio_path)

    assert raised.value.code == expected_code
    assert raised.value.retryable is retryable
    assert "secret upstream message" not in raised.value.safe_message


def test_groq_timeout_is_retryable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "lesson.wav"
    audio_path.write_bytes(b"test audio")
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/audio/transcriptions")

    class FakeTranscriptions:
        def create(self, **kwargs: object) -> None:
            del kwargs
            raise APITimeoutError(request)

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            del kwargs
            self.audio = SimpleNamespace(transcriptions=FakeTranscriptions())

    monkeypatch.setattr(groq_transcriber, "Groq", FakeClient)
    transcriber = GroqTranscriber("test-key", "whisper-large-v3-turbo", 20)

    with pytest.raises(TranscriptionError) as raised:
        transcriber.transcribe(audio_path)

    assert raised.value.code == "provider_timeout"
    assert raised.value.retryable
