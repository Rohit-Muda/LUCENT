import io
import math
import struct
import wave

import lameenc
import pytest

from backend.app.errors import ApiError
from backend.app.services.audio_storage import (
    LocalAudioStorage,
    StorageError,
    UploadSizeLimitExceeded,
)
from backend.app.services.audio_validation import (
    sanitize_original_filename,
    validate_audio_file,
)


def make_wav(duration_seconds: float = 0.25) -> bytes:
    sample_rate = 8000
    sample_count = int(sample_rate * duration_seconds)
    samples = [int(5000 * math.sin(2 * math.pi * 440 * index / sample_rate)) for index in range(sample_count)]
    audio = io.BytesIO()
    with wave.open(audio, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(struct.pack(f"<{sample_count}h", *samples))
    return audio.getvalue()


def make_mp3() -> bytes:
    sample_rate = 44100
    samples = [
        int(4000 * math.sin(2 * math.pi * 440 * index / sample_rate))
        for index in range(sample_rate)
    ]
    encoder = lameenc.Encoder()
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(1)
    encoder.set_bit_rate(64)
    encoder.set_quality(5)
    return bytes(encoder.encode(struct.pack(f"<{len(samples)}h", *samples)) + encoder.flush())


@pytest.mark.parametrize(
    ("filename", "content_type", "content", "expected_extension"),
    [
        ("lesson.wav", "audio/wav", make_wav(), ".wav"),
        ("lesson.mp3", "audio/mpeg", make_mp3(), ".mp3"),
    ],
)
def test_valid_audio_content_is_recognized(
    tmp_path,
    filename: str,
    content_type: str,
    content: bytes,
    expected_extension: str,
) -> None:
    storage = LocalAudioStorage(tmp_path / "uploads")
    key = storage.store(io.BytesIO(content), expected_extension, 1_000_000)

    validated = validate_audio_file(
        storage.path_for(key),
        filename,
        content_type,
        max_size_bytes=1_000_000,
        max_duration_seconds=10,
    )

    assert validated.extension == expected_extension
    assert validated.size_bytes == len(content)
    assert 0 < validated.duration_seconds <= 10


def test_rejects_mismatched_audio_mime_type(tmp_path) -> None:
    storage = LocalAudioStorage(tmp_path / "uploads")
    key = storage.store(io.BytesIO(make_wav()), ".wav", 1_000_000)

    with pytest.raises(ApiError) as error:
        validate_audio_file(
            storage.path_for(key),
            "lesson.wav",
            "audio/mpeg",
            max_size_bytes=1_000_000,
            max_duration_seconds=10,
        )

    assert error.value.code == "audio_content_type_mismatch"


def test_rejects_content_that_does_not_match_extension(tmp_path) -> None:
    storage = LocalAudioStorage(tmp_path / "uploads")
    key = storage.store(io.BytesIO(make_wav()), ".mp3", 1_000_000)

    with pytest.raises(ApiError) as error:
        validate_audio_file(
            storage.path_for(key),
            "lesson.mp3",
            "audio/mpeg",
            max_size_bytes=1_000_000,
            max_duration_seconds=10,
        )

    assert error.value.code == "audio_content_mismatch"


@pytest.mark.parametrize(
    ("content", "expected_code"),
    [(b"", "empty_audio"), (b"not an audio recording", "invalid_audio")],
)
def test_rejects_empty_or_corrupt_audio(tmp_path, content: bytes, expected_code: str) -> None:
    storage = LocalAudioStorage(tmp_path / "uploads")
    key = storage.store(io.BytesIO(content), ".wav", 1_000_000)

    with pytest.raises(ApiError) as error:
        validate_audio_file(
            storage.path_for(key),
            "lesson.wav",
            "audio/wav",
            max_size_bytes=1_000_000,
            max_duration_seconds=10,
        )

    assert error.value.code == expected_code


def test_rejects_audio_over_duration_limit(tmp_path) -> None:
    storage = LocalAudioStorage(tmp_path / "uploads")
    key = storage.store(io.BytesIO(make_wav(2)), ".wav", 1_000_000)

    with pytest.raises(ApiError) as error:
        validate_audio_file(
            storage.path_for(key),
            "lesson.wav",
            "audio/wav",
            max_size_bytes=1_000_000,
            max_duration_seconds=1,
        )

    assert error.value.code == "audio_too_long"


def test_storage_enforces_size_limit_and_removes_temporary_file(tmp_path) -> None:
    storage = LocalAudioStorage(tmp_path / "uploads")

    with pytest.raises(UploadSizeLimitExceeded):
        storage.store(io.BytesIO(b"x" * 100), ".wav", 10)

    assert list(storage.root.iterdir()) == []


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        (r"..\..\private\lesson.wav", "lesson.wav"),
        ("../../private/lesson.wav", "lesson.wav"),
        ("lesson.wav", "lesson.wav"),
    ],
)
def test_original_filename_is_display_only_and_sanitized(filename: str, expected: str) -> None:
    assert sanitize_original_filename(filename) == expected


@pytest.mark.parametrize("storage_key", ["../outside.wav", r"..\outside.wav", "folder/file.wav", ""])
def test_storage_rejects_path_traversal_keys(tmp_path, storage_key: str) -> None:
    storage = LocalAudioStorage(tmp_path / "uploads")

    with pytest.raises(StorageError):
        storage.path_for(storage_key)
