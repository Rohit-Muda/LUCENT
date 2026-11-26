from types import SimpleNamespace

import httpx2
import pytest
from google.genai import errors

from backend.app.providers import gemini_generator
from backend.app.providers.gemini_generator import GeminiJsonGenerator, GeminiProviderError
from backend.app.services.study_materials import NotesContent


def test_generator_uses_structured_stateless_request_without_sdk_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    client_options: dict[str, object] = {}

    class FakeInteractions:
        def create(self, **kwargs: object) -> SimpleNamespace:
            calls.append(kwargs)
            return SimpleNamespace(output_text='{"title":"Lecture","sections":[],"concepts":[]}')

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            client_options.update(kwargs)
            self.interactions = FakeInteractions()

        def close(self) -> None:
            pass

    monkeypatch.setattr(gemini_generator.genai, "Client", FakeClient)
    generator = GeminiJsonGenerator("test-key", "gemini-3.5-flash-lite", 20)

    output = generator.generate_json("prompt", NotesContent)
    generator.close()

    assert output.startswith('{"title"')
    assert client_options["api_key"] == "test-key"
    http_options = client_options["http_options"]
    assert http_options.timeout == 20_000
    assert http_options.retry_options.attempts == 1
    assert calls[0]["model"] == "gemini-3.5-flash-lite"
    assert calls[0]["input"] == "prompt"
    assert calls[0]["store"] is False
    assert calls[0]["response_format"]["mime_type"] == "application/json"
    assert calls[0]["response_format"]["schema"] == NotesContent.model_json_schema()


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (401, "provider_authentication", False),
        (429, "provider_rate_limit", True),
        (503, "provider_unavailable", True),
        (400, "provider_request", False),
    ],
)
def test_provider_status_errors_are_safe_and_classified(
    status_code: int,
    expected_code: str,
    retryable: bool,
) -> None:
    error = errors.APIError(status_code, {"message": "secret provider detail"})

    mapped = GeminiJsonGenerator._status_error(error)

    assert mapped.code == expected_code
    assert mapped.retryable is retryable
    assert "secret provider detail" not in mapped.safe_message


def test_timeout_is_mapped_to_retryable_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeInteractions:
        def create(self, **kwargs: object) -> None:
            del kwargs
            raise httpx2.TimeoutException("timeout")

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            del kwargs
            self.interactions = FakeInteractions()

        def close(self) -> None:
            pass

    monkeypatch.setattr(gemini_generator.genai, "Client", FakeClient)
    generator = GeminiJsonGenerator("test-key", "gemini-3.5-flash-lite", 20)

    with pytest.raises(GeminiProviderError) as raised:
        generator.generate_json("prompt", NotesContent)

    assert raised.value.code == "provider_timeout"
    assert raised.value.retryable
