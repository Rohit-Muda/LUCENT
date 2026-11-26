import re
import unicodedata
from pathlib import Path
from collections.abc import Callable
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.app.config import Settings
from backend.app.errors import ApiError
from backend.app.models import Lecture, Transcript
from backend.app.providers.gemini_generator import GeminiProviderError
from backend.app.providers.groq_transcriber import (
    TranscriptionError,
    TranscriptionResult,
)
from backend.app.services.audio_storage import LocalAudioStorage, StorageError
from backend.app.services.audio_validation import validate_audio_file
from backend.app.services.pdf_export import PdfExportError
from backend.app.services.processing_jobs import (
    JobClaim,
    ProcessingError,
    ProcessingJobManager,
)
from backend.app.services.study_materials import StudyMaterialError


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> TranscriptionResult: ...


class StudyMaterials(Protocol):
    def generate_notes(self, lecture_id: str, transcript: str) -> object: ...

    def generate_explanations(self, lecture_id: str, transcript: str) -> object: ...

    def generate_revision_points(self, lecture_id: str, transcript: str) -> object: ...

    def generate_quiz(self, lecture_id: str, transcript: str) -> object: ...


class PdfExporter(Protocol):
    def ensure_pdf(self, lecture_id: str) -> object: ...


def validate_uploaded_audio(
    claim: JobClaim,
    manager: ProcessingJobManager,
    settings: Settings,
) -> None:
    validate_audio_stage(claim, manager, settings)
    manager.wait_for_stage(claim, "transcribe")


def validate_audio_stage(
    claim: JobClaim,
    manager: ProcessingJobManager,
    settings: Settings,
) -> None:
    if claim.last_successful_stage == "validate_upload":
        return
    manager.start_stage(claim, "validate_upload")
    try:
        with manager.session_factory() as session:
            lecture = session.get(Lecture, claim.lecture_id)
            if lecture is None:
                raise ProcessingError(
                    "The uploaded lecture record is missing.",
                    retryable=False,
                )
            path = LocalAudioStorage(settings.upload_dir).path_for(lecture.storage_key)
            validated = validate_audio_file(
                path,
                lecture.original_filename,
                lecture.media_type,
                min(settings.max_upload_size_bytes, settings.groq_max_audio_size_bytes),
                settings.max_audio_duration_seconds,
            )
            if validated.size_bytes != lecture.file_size_bytes:
                raise ProcessingError(
                    "The stored audio no longer matches its saved metadata.",
                    retryable=False,
                )
    except ProcessingError:
        raise
    except ApiError as exc:
        raise ProcessingError("The stored audio failed validation.", retryable=False) from exc
    except (OSError, StorageError, ValueError) as exc:
        raise ProcessingError("The stored audio could not be validated.", retryable=False) from exc

    manager.complete_stage(claim, "validate_upload")


def process_transcription(
    claim: JobClaim,
    manager: ProcessingJobManager,
    settings: Settings,
    transcriber: Transcriber,
) -> None:
    _ensure_transcript_stage(claim, manager, settings, transcriber)
    manager.complete_job(claim)


def process_lecture_pipeline(
    claim: JobClaim,
    manager: ProcessingJobManager,
    settings: Settings,
    transcriber: Transcriber,
    materials: StudyMaterials,
    pdf_exporter: PdfExporter | None = None,
) -> None:
    regeneration_stages = {
        "regenerate_notes": materials.generate_notes,
        "regenerate_explanations": materials.generate_explanations,
        "regenerate_revision_points": materials.generate_revision_points,
        "regenerate_quiz": materials.generate_quiz,
    }
    if claim.current_stage in regeneration_stages:
        stage = claim.current_stage
        transcript = _load_saved_transcript(manager, claim.lecture_id)
        _run_generation_stage(claim, manager, stage, regeneration_stages[stage], transcript)
        if pdf_exporter is not None and stage != "regenerate_quiz":
            _run_pdf_stage(claim, manager, pdf_exporter)
        manager.complete_job(claim)
        return

    _ensure_transcript_stage(claim, manager, settings, transcriber)
    transcript = _load_saved_transcript(manager, claim.lecture_id)
    stages = (
        ("generate_notes", materials.generate_notes),
        ("generate_explanations", materials.generate_explanations),
        ("generate_revision_points", materials.generate_revision_points),
        ("generate_quiz", materials.generate_quiz),
    )
    completed_stages = (
        "validate_upload",
        "transcribe",
        "generate_notes",
        "generate_explanations",
        "generate_revision_points",
        "generate_quiz",
        "generate_pdf",
    )
    last_successful_index = (
        completed_stages.index(claim.last_successful_stage)
        if claim.last_successful_stage in completed_stages
        else -1
    )
    for index, (stage, generate) in enumerate(stages, start=2):
        if index <= last_successful_index:
            continue
        _run_generation_stage(claim, manager, stage, generate, transcript)
    if pdf_exporter is not None and last_successful_index < 6:
        _run_pdf_stage(claim, manager, pdf_exporter)
    manager.complete_job(claim)


def _ensure_transcript_stage(
    claim: JobClaim,
    manager: ProcessingJobManager,
    settings: Settings,
    transcriber: Transcriber,
) -> None:
    if claim.last_successful_stage in {
        "transcribe",
        "generate_notes",
        "generate_explanations",
        "generate_revision_points",
        "generate_quiz",
        "generate_pdf",
    }:
        return
    if claim.last_successful_stage != "validate_upload":
        validate_audio_stage(claim, manager, settings)

    manager.start_stage(claim, "transcribe")
    with manager.session_factory() as session:
        lecture = session.get(Lecture, claim.lecture_id)
        if lecture is None:
            raise ProcessingError("The uploaded lecture record is missing.", retryable=False)
        existing_transcript = session.scalar(
            select(Transcript.id).where(Transcript.lecture_id == claim.lecture_id)
        )
        storage_key = lecture.storage_key
        filename = lecture.original_filename
        media_type = lecture.media_type
        file_size_bytes = lecture.file_size_bytes

    if existing_transcript is not None:
        manager.complete_stage(claim, "transcribe")
        return

    try:
        audio_path = LocalAudioStorage(settings.upload_dir).path_for(storage_key)
        validated = validate_audio_file(
            audio_path,
            filename,
            media_type,
            min(settings.max_upload_size_bytes, settings.groq_max_audio_size_bytes),
            settings.max_audio_duration_seconds,
        )
    except (ApiError, OSError, StorageError, ValueError) as exc:
        raise ProcessingError("The stored audio failed validation before transcription.", retryable=False) from exc

    if validated.size_bytes != file_size_bytes:
        raise ProcessingError(
            "The stored audio no longer matches its saved metadata.",
            retryable=False,
        )

    try:
        result = transcriber.transcribe(audio_path)
    except TranscriptionError as exc:
        raise ProcessingError(exc.safe_message, retryable=exc.retryable) from None

    cleaned_text = clean_transcript(result.text)
    if not cleaned_text:
        raise ProcessingError("The transcript could not be cleaned.", retryable=False)

    transcript = Transcript(
        lecture_id=claim.lecture_id,
        original_text=result.text,
        cleaned_text=cleaned_text,
        segments=result.segments,
        provider="groq",
        model=settings.groq_model,
        detected_language=result.detected_language,
        transcribed_duration_seconds=result.duration_seconds,
    )
    with manager.session_factory() as session:
        session.add(transcript)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing_transcript = session.scalar(
                select(Transcript.id).where(Transcript.lecture_id == claim.lecture_id)
            )
            if existing_transcript is None:
                raise ProcessingError("The transcript could not be saved.", retryable=True) from None
        except SQLAlchemyError:
            session.rollback()
            raise ProcessingError("The transcript could not be saved.", retryable=True) from None

    manager.complete_stage(claim, "transcribe")


def _load_saved_transcript(manager: ProcessingJobManager, lecture_id: str) -> str:
    with manager.session_factory() as session:
        transcript = session.scalar(
            select(Transcript.cleaned_text).where(Transcript.lecture_id == lecture_id)
        )
    if not isinstance(transcript, str) or not transcript.strip():
        raise ProcessingError(
            "A saved transcript is required for content generation.",
            retryable=False,
        )
    return transcript


def _run_generation_stage(
    claim: JobClaim,
    manager: ProcessingJobManager,
    stage: str,
    generate: Callable[[str, str], object],
    transcript: str,
) -> None:
    manager.start_stage(claim, stage)
    try:
        generate(claim.lecture_id, transcript)
    except GeminiProviderError as exc:
        raise ProcessingError(exc.safe_message, retryable=exc.retryable) from None
    except StudyMaterialError as exc:
        raise ProcessingError(exc.safe_message, retryable=exc.retryable) from None
    manager.complete_stage(claim, stage)


def _run_pdf_stage(
    claim: JobClaim,
    manager: ProcessingJobManager,
    pdf_exporter: PdfExporter,
) -> None:
    manager.start_stage(claim, "generate_pdf")
    try:
        pdf_exporter.ensure_pdf(claim.lecture_id)
    except PdfExportError as exc:
        raise ProcessingError(exc.safe_message, retryable=exc.retryable) from None
    manager.complete_stage(claim, "generate_pdf")


def clean_transcript(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[^\S\n]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()
