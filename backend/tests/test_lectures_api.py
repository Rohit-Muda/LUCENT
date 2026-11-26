import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import main
from backend.app.config import Settings
from backend.app.database import get_db
from backend.app.models import Base, Lecture, Transcript
from backend.app.routes.lectures import get_audio_storage
from backend.app.routes.processing import get_processing_job_manager
from backend.app.services.audio_storage import (
    AudioStorage,
    LocalAudioStorage,
    StorageError,
)
from backend.app.services.processing_jobs import ProcessingJobManager
from backend.tests.test_audio_validation import make_mp3, make_wav


@dataclass
class ApiHarness:
    app: object
    storage_root: Path
    settings: Settings
    engine: Engine


@pytest.fixture
def api_harness(tmp_path: Path) -> Iterator[ApiHarness]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    settings = Settings(
        _env_file=None,
        upload_dir=tmp_path / "uploads",
        max_upload_size_bytes=100_000,
        max_audio_duration_seconds=60,
        groq_max_audio_size_bytes=100_000,
    )
    app = main.create_app()

    def override_database() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = override_database
    app.dependency_overrides[get_audio_storage] = lambda: LocalAudioStorage(settings.upload_dir)
    app.dependency_overrides[main.get_settings] = lambda: settings

    yield ApiHarness(app=app, storage_root=settings.upload_dir, settings=settings, engine=engine)

    app.dependency_overrides.clear()
    engine.dispose()


def request(
    app: object,
    method: str,
    url: str,
    *,
    files: dict[str, tuple[str, bytes, str]] | None = None,
    params: dict[str, int] | None = None,
) -> Response:
    async def send() -> Response:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.request(method, url, files=files, params=params)

    return asyncio.run(send())


@pytest.mark.parametrize(
    ("filename", "content_type", "content", "expected_media_type"),
    [
        ("lesson.wav", "audio/wav", make_wav(), "audio/wav"),
        ("lesson.mp3", "audio/mpeg", make_mp3(), "audio/mpeg"),
    ],
)
def test_upload_accepts_valid_mp3_and_wav(
    api_harness: ApiHarness,
    filename: str,
    content_type: str,
    content: bytes,
    expected_media_type: str,
) -> None:
    response = request(
        api_harness.app,
        "POST",
        "/lectures",
        files={"file": (filename, content, content_type)},
    )

    assert response.status_code == 201
    lecture = response.json()
    assert lecture["original_filename"] == filename
    assert lecture["media_type"] == expected_media_type
    assert lecture["file_size_bytes"] == len(content)
    assert lecture["duration_seconds"] > 0
    assert lecture["status"] == "queued"
    assert "storage_key" not in lecture
    assert len(list(api_harness.storage_root.iterdir())) == 1
    processing = request(
        api_harness.app,
        "GET",
        f"/lectures/{lecture['id']}/processing",
    )
    assert processing.status_code == 200
    assert processing.json()["status"] == "queued"
    assert processing.json()["current_stage"] == "validate_upload"


def test_retry_endpoint_requeues_failed_job(api_harness: ApiHarness) -> None:
    response = request(
        api_harness.app,
        "POST",
        "/lectures",
        files={"file": ("retry.wav", make_wav(), "audio/wav")},
    )
    lecture_id = response.json()["id"]
    with Session(api_harness.engine, expire_on_commit=False) as session:
        lecture = session.scalar(select(Lecture).where(Lecture.id == lecture_id))
        lecture.status = "failed"
        lecture.processing_job.status = "failed"
        lecture.processing_job.current_stage = "validate_upload"
        lecture.processing_job.attempts_by_stage = {"validate_upload": 3}
        session.commit()

    manager = ProcessingJobManager(
        sessionmaker(bind=api_harness.engine, expire_on_commit=False),
        lease_seconds=60,
        max_stage_attempts=3,
        max_manual_retries=2,
        retry_backoff_seconds=1,
    )
    api_harness.app.dependency_overrides[get_processing_job_manager] = lambda: manager
    retried = request(api_harness.app, "POST", f"/lectures/{lecture_id}/retry")

    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    assert retried.json()["attempts_by_stage"] == {"validate_upload": 0}
    assert retried.json()["manual_retry_count"] == 1


def test_rejects_unsupported_extension(api_harness: ApiHarness) -> None:
    response = request(
        api_harness.app,
        "POST",
        "/lectures",
        files={"file": ("lesson.txt", b"not audio", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_audio_format"
    if api_harness.storage_root.exists():
        assert list(api_harness.storage_root.iterdir()) == []


@pytest.mark.parametrize(
    ("filename", "content_type", "content", "expected_code"),
    [
        ("lesson.wav", "audio/mpeg", make_wav(), "audio_content_type_mismatch"),
        ("lesson.wav", "audio/wav", b"", "empty_audio"),
        ("lesson.wav", "audio/wav", b"not audio", "invalid_audio"),
        ("lesson.mp3", "audio/mpeg", make_wav(), "audio_content_mismatch"),
    ],
)
def test_rejects_empty_corrupt_or_mismatched_uploads(
    api_harness: ApiHarness,
    filename: str,
    content_type: str,
    content: bytes,
    expected_code: str,
) -> None:
    response = request(
        api_harness.app,
        "POST",
        "/lectures",
        files={"file": (filename, content, content_type)},
    )

    assert response.status_code in {415, 422}
    assert response.json()["error"]["code"] == expected_code
    assert list(api_harness.storage_root.iterdir()) == []


def test_rejects_oversized_upload_before_persisting_audio(
    api_harness: ApiHarness,
) -> None:
    api_harness.settings.max_upload_size_bytes = 100
    api_harness.settings.groq_max_audio_size_bytes = 100

    response = request(
        api_harness.app,
        "POST",
        "/lectures",
        files={"file": ("lesson.wav", make_wav(), "audio/wav")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "audio_too_large"
    assert list(api_harness.storage_root.iterdir()) == []


def test_rejects_audio_above_configured_duration(
    api_harness: ApiHarness,
) -> None:
    api_harness.settings.max_audio_duration_seconds = 1

    response = request(
        api_harness.app,
        "POST",
        "/lectures",
        files={"file": ("lesson.wav", make_wav(2), "audio/wav")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "audio_too_long"
    assert list(api_harness.storage_root.iterdir()) == []


def test_duplicate_original_filenames_get_distinct_server_storage(
    api_harness: ApiHarness,
) -> None:
    files = {"file": ("lesson.wav", make_wav(), "audio/wav")}
    first = request(api_harness.app, "POST", "/lectures", files=files)
    second = request(api_harness.app, "POST", "/lectures", files=files)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["original_filename"] == second.json()["original_filename"]
    stored_files = list(api_harness.storage_root.iterdir())
    assert len(stored_files) == 2
    assert stored_files[0].name != stored_files[1].name


def test_untrusted_path_in_original_filename_is_not_used_for_storage(
    api_harness: ApiHarness,
) -> None:
    response = request(
        api_harness.app,
        "POST",
        "/lectures",
        files={"file": (r"..\..\outside\lesson.wav", make_wav(), "audio/wav")},
    )

    assert response.status_code == 201
    assert response.json()["original_filename"] == "lesson.wav"
    assert len(list(api_harness.storage_root.iterdir())) == 1
    assert not (api_harness.storage_root.parent / "outside" / "lesson.wav").exists()


def test_storage_failure_returns_safe_error(api_harness: ApiHarness) -> None:
    class FailedStorage:
        def store(self, source, extension: str, max_bytes: int) -> str:
            raise StorageError("internal detail must not be returned")

        def delete(self, storage_key: str) -> None:
            raise AssertionError("No file was stored")

        def path_for(self, storage_key: str) -> Path:
            raise AssertionError("No file was stored")

    api_harness.app.dependency_overrides[get_audio_storage] = lambda: FailedStorage()
    response = request(
        api_harness.app,
        "POST",
        "/lectures",
        files={"file": ("lesson.wav", make_wav(), "audio/wav")},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "storage_unavailable"
    assert "internal detail" not in response.text


def test_database_failure_removes_stored_file(
    api_harness: ApiHarness,
) -> None:
    class FailedDatabaseSession:
        def add(self, value) -> None:
            pass

        def flush(self) -> None:
            pass

        def scalar(self, statement):
            del statement
            return None

        def commit(self) -> None:
            raise OperationalError("INSERT", {}, RuntimeError("database unavailable"))

        def rollback(self) -> None:
            pass

    def override_database() -> Iterator[FailedDatabaseSession]:
        yield FailedDatabaseSession()

    api_harness.app.dependency_overrides[get_db] = override_database
    response = request(
        api_harness.app,
        "POST",
        "/lectures",
        files={"file": ("lesson.wav", make_wav(), "audio/wav")},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert list(api_harness.storage_root.iterdir()) == []


def test_list_and_detail_return_saved_lecture(api_harness: ApiHarness) -> None:
    upload = request(
        api_harness.app,
        "POST",
        "/lectures",
        files={"file": ("lesson.wav", make_wav(), "audio/wav")},
    )
    lecture_id = upload.json()["id"]

    detail = request(api_harness.app, "GET", f"/lectures/{lecture_id}")
    listing = request(api_harness.app, "GET", "/lectures", params={"limit": 1, "offset": 0})

    assert detail.status_code == 200
    assert detail.json()["id"] == lecture_id
    assert detail.json()["status"] == "queued"
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == lecture_id


def test_transcript_endpoint_returns_saved_text_and_segments(api_harness: ApiHarness) -> None:
    upload = request(
        api_harness.app,
        "POST",
        "/lectures",
        files={"file": ("lesson.wav", make_wav(), "audio/wav")},
    )
    lecture_id = upload.json()["id"]
    with Session(api_harness.engine, expire_on_commit=False) as session:
        session.add(
            Transcript(
                lecture_id=lecture_id,
                original_text="Original Telugu text",
                cleaned_text="Clean Telugu text",
                segments=[{"start": 1.0, "end": 2.0, "text": "Clean Telugu text"}],
                provider="groq",
                model="whisper-large-v3-turbo",
                detected_language="te",
                transcribed_duration_seconds=2.0,
            )
        )
        session.commit()

    response = request(api_harness.app, "GET", f"/lectures/{lecture_id}/transcript")
    missing = request(api_harness.app, "GET", "/lectures/not-a-lecture/transcript")

    assert response.status_code == 200
    assert response.json()["original_text"] == "Original Telugu text"
    assert response.json()["cleaned_text"] == "Clean Telugu text"
    assert response.json()["segments"] == [
        {"start": 1.0, "end": 2.0, "text": "Clean Telugu text"}
    ]
    assert response.json()["provider"] == "groq"
    assert response.json()["detected_language"] == "te"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "transcript_not_found"


def test_unknown_lecture_returns_not_found(api_harness: ApiHarness) -> None:
    response = request(api_harness.app, "GET", "/lectures/not-a-lecture")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "lecture_not_found"
