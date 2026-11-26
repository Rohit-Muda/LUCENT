from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
import time

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.config import Settings
from backend.app.models import Base, Lecture, ProcessingJob, Transcript
from backend.app.providers.groq_transcriber import TranscriptionResult
from backend.app.services.processing_jobs import (
    JobNotRetryable,
    ProcessingError,
    ProcessingJobManager,
    RetryLimitReached,
    enqueue_processing_job,
    process_one_job,
)
from backend.app.services.audio_validation import validate_audio_file
from backend.app.workers.processor import (
    clean_transcript,
    process_lecture_pipeline,
    process_transcription,
    validate_uploaded_audio,
)
from backend.tests.test_audio_validation import make_wav


@pytest.fixture
def job_store() -> Iterator[tuple[Engine, sessionmaker[Session], str]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        lecture = Lecture(
            original_filename="job.wav",
            storage_key="job-audio.wav",
            media_type="audio/wav",
            file_size_bytes=100,
            duration_seconds=1,
            status="queued",
        )
        session.add(lecture)
        session.flush()
        job = ProcessingJob(
            lecture_id=lecture.id,
            status="queued",
            current_stage="validate_upload",
            retry_count=0,
            attempts_by_stage={},
            manual_retry_count=0,
        )
        session.add(job)
        session.commit()
        lecture_id = lecture.id
    yield engine, factory, lecture_id
    engine.dispose()


def build_manager(factory: sessionmaker[Session], **overrides: int) -> ProcessingJobManager:
    options = {
        "lease_seconds": 30,
        "max_stage_attempts": 2,
        "max_manual_retries": 2,
        "retry_backoff_seconds": 1,
    }
    options.update(overrides)
    return ProcessingJobManager(factory, **options)


def test_job_can_only_be_claimed_once_until_lease_expires(job_store) -> None:
    _, factory, _ = job_store
    manager = build_manager(factory)
    now = datetime(2026, 1, 1)

    first = manager.claim_next("worker-one", now)
    second = manager.claim_next("worker-two", now + timedelta(seconds=1))

    assert first is not None
    assert first.worker_id == "worker-one"
    assert second is None
    assert manager.renew_lease(first, now + timedelta(seconds=2))
    with factory() as session:
        lecture = session.scalar(select(Lecture))
        assert lecture.status == "processing"


def test_enqueuing_an_existing_lecture_reuses_its_job(job_store) -> None:
    _, factory, lecture_id = job_store
    with factory() as session:
        original = session.scalar(
            select(ProcessingJob).where(ProcessingJob.lecture_id == lecture_id)
        )
        existing = enqueue_processing_job(session, lecture_id)
        session.commit()

    assert existing.id == original.id


def test_worker_can_resume_a_waiting_transcription_job(job_store) -> None:
    _, factory, lecture_id = job_store
    with factory() as session:
        job = session.scalar(
            select(ProcessingJob).where(ProcessingJob.lecture_id == lecture_id)
        )
        job.status = "waiting"
        job.current_stage = "transcribe"
        job.last_successful_stage = "validate_upload"
        session.commit()

    assert build_manager(factory).claim_next("paused-worker") is None
    claim = build_manager(factory, resume_waiting=True).claim_next("transcription-worker")

    assert claim is not None
    assert claim.current_stage == "transcribe"
    assert claim.last_successful_stage == "validate_upload"


def test_expired_worker_lease_recovers_from_last_successful_stage(job_store) -> None:
    _, factory, _ = job_store
    manager = build_manager(factory)
    now = datetime(2026, 1, 1)
    first_claim = manager.claim_next("worker-one", now)
    assert first_claim is not None
    manager.start_stage(first_claim, "validate_upload", now)
    manager.complete_stage(first_claim, "validate_upload", now + timedelta(seconds=1))
    manager.start_stage(first_claim, "transcribe", now + timedelta(seconds=2))

    recovered = manager.recover_stale_jobs(now + timedelta(seconds=31))
    second_claim = manager.claim_next("worker-two", now + timedelta(seconds=32))

    assert recovered == 1
    assert second_claim is not None
    assert second_claim.current_stage == "transcribe"
    assert second_claim.last_successful_stage == "validate_upload"


def test_stage_retries_are_bounded_and_manual_retries_have_a_limit(job_store) -> None:
    _, factory, lecture_id = job_store
    manager = build_manager(factory, max_manual_retries=1)
    now = datetime(2026, 1, 1)

    for attempt in range(2):
        claim = manager.claim_next(f"worker-{attempt}", now)
        assert claim is not None
        manager.start_stage(claim, "transcribe", now)
        manager.fail_stage(claim, "transcribe", "Safe provider error.", now + timedelta(seconds=1))
        if attempt == 0:
            assert manager.claim_next("early-worker", now + timedelta(seconds=1)) is None
        now += timedelta(seconds=2)

    with factory() as session:
        job = session.scalar(select(ProcessingJob).where(ProcessingJob.lecture_id == lecture_id))
        assert job.status == "failed"
        assert job.attempts_by_stage == {"transcribe": 2}
        assert job.retry_count == 2

    manager.retry_failed(lecture_id, now)
    assert manager.get_for_lecture(lecture_id).manual_retry_count == 1
    retry_claim = manager.claim_next("manual-retry", now)
    assert retry_claim is not None
    manager.start_stage(retry_claim, "transcribe", now)
    manager.fail_stage(retry_claim, "transcribe", "Safe provider error.", now + timedelta(seconds=1))
    now += timedelta(seconds=2)
    claim = manager.claim_next("second-cycle", now)
    assert claim is not None
    manager.start_stage(claim, "transcribe", now)
    manager.fail_stage(claim, "transcribe", "Safe provider error.", now + timedelta(seconds=1))
    with pytest.raises(RetryLimitReached):
        manager.retry_failed(lecture_id, now)


def test_regeneration_cannot_bypass_a_failed_job_retry_limit(job_store) -> None:
    _, factory, lecture_id = job_store
    with factory() as session:
        job = session.scalar(
            select(ProcessingJob).where(ProcessingJob.lecture_id == lecture_id)
        )
        job.status = "failed"
        job.manual_retry_count = 2
        session.add(
            Transcript(
                lecture_id=lecture_id,
                original_text="Saved transcript",
                cleaned_text="Saved transcript",
            )
        )
        session.commit()

    with pytest.raises(JobNotRetryable):
        build_manager(factory).queue_regeneration(lecture_id, "notes")

    assert build_manager(factory).get_for_lecture(lecture_id).status == "failed"


def test_worker_persists_stage_success_and_waits_for_next_pipeline_phase(job_store) -> None:
    _, factory, lecture_id = job_store
    manager = build_manager(factory)

    def processor(claim, job_manager):
        job_manager.start_stage(claim, "validate_upload")
        job_manager.complete_stage(claim, "validate_upload")
        manager.complete_stage(claim, "validate_upload")
        manager.wait_for_stage(claim, "transcribe")
        job_manager.wait_for_stage(claim, "transcribe")

    assert process_one_job(manager, "worker-one", processor)
    job = manager.get_for_lecture(lecture_id)
    with factory() as session:
        lecture = session.scalar(select(Lecture).where(Lecture.id == lecture_id))
        assert lecture.status == "awaiting_transcription"

    assert job.status == "waiting"
    assert job.last_successful_stage == "validate_upload"
    assert job.current_stage == "transcribe"


def test_worker_records_safe_error_and_requeues_for_bounded_retry(job_store) -> None:
    _, factory, lecture_id = job_store
    manager = build_manager(factory)

    def processor(claim, job_manager):
        job_manager.start_stage(claim, "validate_upload")
        raise ProcessingError("The audio could not be validated.")

    assert process_one_job(manager, "worker-one", processor)
    job = manager.get_for_lecture(lecture_id)

    assert job.status == "queued"
    assert job.last_error == "The audio could not be validated."
    assert job.attempts_by_stage == {"validate_upload": 1}


def test_worker_renews_lease_during_long_stage(job_store) -> None:
    _, factory, lecture_id = job_store
    manager = build_manager(factory, lease_seconds=2)

    def processor(claim, job_manager):
        job_manager.start_stage(claim, "transcribe")
        time.sleep(2.2)
        job_manager.complete_stage(claim, "transcribe")
        job_manager.complete_job(claim)

    assert process_one_job(manager, "worker-one", processor)
    assert manager.get_for_lecture(lecture_id).status == "completed"


def test_worker_skips_successful_checkpoint_after_restart(job_store, tmp_path: Path) -> None:
    _, factory, lecture_id = job_store
    manager = build_manager(factory)
    audio_path = tmp_path / "job-audio.wav"
    audio_path.write_bytes(make_wav())
    validated = validate_audio_file(audio_path, "job.wav", "audio/wav", 100_000, 60)
    with factory() as session:
        lecture = session.get(Lecture, lecture_id)
        lecture.file_size_bytes = validated.size_bytes
        lecture.duration_seconds = validated.duration_seconds
        session.commit()
    settings = Settings(
        _env_file=None,
        upload_dir=tmp_path,
        max_upload_size_bytes=100_000,
        max_audio_duration_seconds=60,
        groq_max_audio_size_bytes=100_000,
    )
    process_audio = lambda claim, job_manager: validate_uploaded_audio(claim, job_manager, settings)

    assert process_one_job(manager, "worker-one", process_audio)
    with factory() as session:
        job = session.scalar(select(ProcessingJob).where(ProcessingJob.lecture_id == lecture_id))
        job.status = "queued"
        job.current_stage = None
        job.available_at = None
        session.commit()

    assert process_one_job(manager, "worker-restarted", process_audio)
    job = manager.get_for_lecture(lecture_id)
    assert job.status == "waiting"
    assert job.last_successful_stage == "validate_upload"
    assert job.attempts_by_stage == {"validate_upload": 1}


def test_transcription_is_saved_before_stage_completion(job_store, tmp_path: Path) -> None:
    _, factory, lecture_id = job_store
    manager = build_manager(factory)
    audio_path = tmp_path / "job-audio.wav"
    audio_path.write_bytes(make_wav())
    validated = validate_audio_file(audio_path, "job.wav", "audio/wav", 100_000, 60)
    with factory() as session:
        lecture = session.get(Lecture, lecture_id)
        lecture.file_size_bytes = validated.size_bytes
        lecture.duration_seconds = validated.duration_seconds
        session.commit()
    settings = Settings(
        _env_file=None,
        upload_dir=tmp_path,
        max_upload_size_bytes=100_000,
        max_audio_duration_seconds=60,
        groq_max_audio_size_bytes=100_000,
        groq_model="whisper-large-v3-turbo",
    )

    class FakeTranscriber:
        calls = 0

        def transcribe(self, path: Path) -> TranscriptionResult:
            assert path == audio_path
            self.calls += 1
            return TranscriptionResult(
                text="తెలుగు   English\tterm",
                segments=[{"start": 0.0, "end": 2.0, "text": "తెలుగు English"}],
                detected_language="te",
                duration_seconds=2.0,
            )

    transcriber = FakeTranscriber()
    claim = manager.claim_next("worker-one")
    assert claim is not None

    process_transcription(claim, manager, settings, transcriber)

    assert transcriber.calls == 1
    assert manager.get_for_lecture(lecture_id).status == "completed"
    with factory() as session:
        transcript = session.scalar(
            select(Transcript).where(Transcript.lecture_id == lecture_id)
        )
        assert transcript.original_text == "తెలుగు   English\tterm"
        assert transcript.cleaned_text == "తెలుగు English term"
        assert transcript.provider == "groq"
        assert transcript.model == "whisper-large-v3-turbo"
        assert transcript.detected_language == "te"
        assert transcript.segments == [
            {"start": 0.0, "end": 2.0, "text": "తెలుగు English"}
        ]


def test_full_pipeline_resumes_after_saved_transcript_without_repeating_groq(
    job_store,
) -> None:
    _, factory, lecture_id = job_store
    with factory() as session:
        job = session.scalar(
            select(ProcessingJob).where(ProcessingJob.lecture_id == lecture_id)
        )
        job.current_stage = "generate_notes"
        job.last_successful_stage = "transcribe"
        session.add(
            Transcript(
                lecture_id=lecture_id,
                original_text="Saved mixed-language transcript.",
                cleaned_text="Saved mixed-language transcript.",
            )
        )
        session.commit()

    manager = build_manager(factory)
    calls: list[tuple[str, str]] = []

    class NoCallTranscriber:
        def transcribe(self, path: Path) -> TranscriptionResult:
            raise AssertionError(f"Unexpected Groq request for {path}")

    class FakeMaterials:
        def generate_notes(self, _lecture_id: str, transcript: str) -> None:
            del _lecture_id
            calls.append(("notes", transcript))

        def generate_explanations(self, _lecture_id: str, transcript: str) -> None:
            del _lecture_id
            calls.append(("explanations", transcript))

        def generate_revision_points(self, _lecture_id: str, transcript: str) -> None:
            del _lecture_id
            calls.append(("revision-points", transcript))

        def generate_quiz(self, _lecture_id: str, transcript: str) -> None:
            del _lecture_id
            calls.append(("quiz", transcript))

    claim = manager.claim_next("study-material-worker")
    assert claim is not None
    process_lecture_pipeline(
        claim,
        manager,
        Settings(_env_file=None),
        NoCallTranscriber(),
        FakeMaterials(),
    )

    assert [stage for stage, _ in calls] == [
        "notes",
        "explanations",
        "revision-points",
        "quiz",
    ]
    assert {transcript for _, transcript in calls} == {"Saved mixed-language transcript."}
    assert manager.get_for_lecture(lecture_id).status == "completed"


def test_persisted_transcript_is_not_requested_again(job_store) -> None:
    _, factory, lecture_id = job_store
    manager = build_manager(factory)
    with factory() as session:
        job = session.scalar(
            select(ProcessingJob).where(ProcessingJob.lecture_id == lecture_id)
        )
        job.status = "queued"
        job.current_stage = "transcribe"
        job.last_successful_stage = "validate_upload"
        session.add(
            Transcript(
                lecture_id=lecture_id,
                original_text="Saved transcript",
                cleaned_text="Saved transcript",
                segments=[],
            )
        )
        session.commit()

    class NoCallTranscriber:
        def transcribe(self, path: Path) -> TranscriptionResult:
            raise AssertionError(f"Unexpected transcription request for {path}")

    claim = manager.claim_next("worker-restarted")
    assert claim is not None
    settings = Settings(_env_file=None)

    process_transcription(claim, manager, settings, NoCallTranscriber())

    assert manager.get_for_lecture(lecture_id).status == "completed"


def test_clean_transcript_normalizes_whitespace_without_losing_telugu() -> None:
    assert clean_transcript("తెలుగు   English\tterm\r\n\r\n\r\nముగింపు") == (
        "తెలుగు English term\n\nముగింపు"
    )
