import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.config import Settings, get_settings
from backend.app.database import get_db
from backend.app.errors import ApiError
from backend.app.models import Lecture
from backend.app.schemas.lecture import LectureListResponse, LectureResponse
from backend.app.services.audio_storage import (
    AudioStorage,
    LocalAudioStorage,
    StorageError,
    UploadSizeLimitExceeded,
)
from backend.app.services.audio_validation import (
    sanitize_original_filename,
    validate_audio_file,
)
from backend.app.services.processing_jobs import enqueue_processing_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lectures", tags=["lectures"])


def get_audio_storage(settings: Settings = Depends(get_settings)) -> AudioStorage:
    return LocalAudioStorage(settings.upload_dir)


@router.post("", response_model=LectureResponse, status_code=201)
def upload_lecture(
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
    storage: AudioStorage = Depends(get_audio_storage),
    settings: Settings = Depends(get_settings),
) -> LectureResponse:
    original_filename = sanitize_original_filename(file.filename)
    extension = Path(original_filename).suffix.lower()
    if extension not in {".mp3", ".wav"}:
        raise ApiError(415, "unsupported_audio_format", "Only MP3 and WAV audio files are supported.")

    effective_max_size = min(settings.max_upload_size_bytes, settings.groq_max_audio_size_bytes)
    try:
        storage_key = storage.store(file.file, extension, effective_max_size)
    except UploadSizeLimitExceeded as exc:
        raise ApiError(413, "audio_too_large", "The uploaded audio exceeds the configured/provider size limit.") from exc
    except StorageError as exc:
        logger.exception("Audio storage failed")
        raise ApiError(503, "storage_unavailable", "Audio could not be stored.") from exc

    try:
        stored_path = storage.path_for(storage_key)
        audio = validate_audio_file(
            stored_path,
            original_filename,
            file.content_type,
            effective_max_size,
            settings.max_audio_duration_seconds,
        )
    except ApiError:
        _delete_uploaded_file(storage, storage_key)
        raise
    except StorageError as exc:
        _delete_uploaded_file(storage, storage_key)
        logger.exception("Stored audio could not be accessed for validation")
        raise ApiError(503, "storage_unavailable", "Audio could not be validated from storage.") from exc

    lecture = Lecture(
        original_filename=original_filename,
        storage_key=storage_key,
        media_type="audio/mpeg" if audio.extension == ".mp3" else "audio/wav",
        file_size_bytes=audio.size_bytes,
        duration_seconds=audio.duration_seconds,
        status="queued",
    )
    try:
        session.add(lecture)
        session.flush()
        enqueue_processing_job(session, lecture.id)
        session.commit()
        session.refresh(lecture)
    except SQLAlchemyError as exc:
        session.rollback()
        _delete_uploaded_file(storage, storage_key)
        logger.exception("Lecture metadata could not be saved")
        raise ApiError(503, "database_unavailable", "Lecture metadata could not be saved.") from exc
    return LectureResponse.model_validate(lecture)


@router.get("", response_model=LectureListResponse)
def list_lectures(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> LectureListResponse:
    try:
        total = session.scalar(select(func.count()).select_from(Lecture)) or 0
        items = session.scalars(
            select(Lecture)
            .order_by(Lecture.created_at.desc(), Lecture.id)
            .limit(limit)
            .offset(offset)
        ).all()
    except SQLAlchemyError as exc:
        logger.exception("Lecture history could not be read")
        raise ApiError(503, "database_unavailable", "Lecture history is unavailable.") from exc
    return LectureListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{lecture_id}", response_model=LectureResponse)
def get_lecture(
    lecture_id: str,
    session: Session = Depends(get_db),
) -> LectureResponse:
    try:
        lecture = session.get(Lecture, lecture_id)
    except SQLAlchemyError as exc:
        logger.exception("Lecture details could not be read")
        raise ApiError(503, "database_unavailable", "Lecture details are unavailable.") from exc
    if lecture is None:
        raise ApiError(404, "lecture_not_found", "Lecture was not found.")
    return LectureResponse.model_validate(lecture)


def _delete_uploaded_file(storage: AudioStorage, storage_key: str) -> None:
    try:
        storage.delete(storage_key)
    except StorageError as exc:
        logger.exception("Failed to remove an uncommitted audio upload")
        raise ApiError(
            500,
            "upload_cleanup_failed",
            "Upload cleanup failed; contact the application operator.",
        ) from exc
