import logging
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.config import Settings, get_settings
from backend.app.database import get_db, get_session_factory
from backend.app.errors import ApiError
from backend.app.models import ProcessingJob
from backend.app.schemas.processing import ProcessingStatusResponse
from backend.app.services.processing_jobs import (
    JobNotRetryable,
    ProcessingJobManager,
    RetryLimitReached,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lectures", tags=["processing"])


def get_processing_job_manager(
    settings: Settings = Depends(get_settings),
) -> ProcessingJobManager:
    return ProcessingJobManager(
        get_session_factory(),
        lease_seconds=settings.processing_job_lease_seconds,
        max_stage_attempts=settings.processing_job_max_stage_attempts,
        max_manual_retries=settings.processing_job_max_manual_retries,
        retry_backoff_seconds=settings.processing_job_retry_backoff_seconds,
    )


@router.get("/{lecture_id}/processing", response_model=ProcessingStatusResponse)
def get_processing_status(
    lecture_id: str,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProcessingStatusResponse:
    try:
        job = session.scalar(
            select(ProcessingJob).where(ProcessingJob.lecture_id == lecture_id)
        )
    except SQLAlchemyError as exc:
        logger.exception("Processing status could not be read")
        raise ApiError(503, "database_unavailable", "Processing status is unavailable.") from exc
    if job is None:
        raise ApiError(404, "processing_job_not_found", "Processing job was not found.")
    return _processing_status(job, settings)


@router.post("/{lecture_id}/retry", response_model=ProcessingStatusResponse)
def retry_processing(
    lecture_id: str,
    manager: ProcessingJobManager = Depends(get_processing_job_manager),
    settings: Settings = Depends(get_settings),
) -> ProcessingStatusResponse:
    try:
        job = manager.retry_failed(lecture_id)
    except LookupError as exc:
        raise ApiError(404, "processing_job_not_found", "Processing job was not found.") from exc
    except JobNotRetryable as exc:
        raise ApiError(409, "processing_job_not_retryable", str(exc)) from exc
    except RetryLimitReached as exc:
        raise ApiError(409, "processing_retry_limit_reached", str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Processing job could not be retried")
        raise ApiError(503, "database_unavailable", "Processing job could not be retried.") from exc
    return _processing_status(job, settings)


@router.post(
    "/{lecture_id}/regenerate/{feature}",
    response_model=ProcessingStatusResponse,
)
def regenerate_output(
    lecture_id: str,
    feature: Literal["notes", "explanations", "revision-points", "quiz"],
    manager: ProcessingJobManager = Depends(get_processing_job_manager),
    settings: Settings = Depends(get_settings),
) -> ProcessingStatusResponse:
    try:
        job = manager.queue_regeneration(lecture_id, feature)
    except LookupError as exc:
        raise ApiError(404, "processing_job_not_found", "Processing job was not found.") from exc
    except JobNotRetryable as exc:
        raise ApiError(409, "processing_job_not_retryable", str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Lecture output could not be regenerated")
        raise ApiError(503, "database_unavailable", "Lecture output could not be regenerated.") from exc
    return _processing_status(job, settings)


def _processing_status(job: ProcessingJob, settings: Settings) -> ProcessingStatusResponse:
    return ProcessingStatusResponse(
        id=job.id,
        status=job.status,
        current_stage=job.current_stage,
        last_successful_stage=job.last_successful_stage,
        retry_count=job.retry_count,
        attempts_by_stage=job.attempts_by_stage or {},
        manual_retry_count=job.manual_retry_count,
        last_error=job.last_error,
        created_at=job.created_at,
        updated_at=job.updated_at,
        can_retry=(
            job.status == "failed"
            and job.manual_retry_count < settings.processing_job_max_manual_retries
        ),
    )
