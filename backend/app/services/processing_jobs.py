import hashlib
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import GenerationChunk, Lecture, ProcessingJob, Transcript

logger = logging.getLogger(__name__)


class JobError(RuntimeError):
    pass


class LeaseLost(JobError):
    pass


class JobNotRetryable(JobError):
    pass


class RetryLimitReached(JobError):
    pass


class ProcessingError(JobError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        self.safe_message = message
        self.retryable = retryable
        super().__init__(message)


@dataclass(frozen=True)
class JobClaim:
    job_id: str
    lecture_id: str
    worker_id: str
    current_stage: str | None
    last_successful_stage: str | None


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def enqueue_processing_job(session: Session, lecture_id: str) -> ProcessingJob:
    existing = session.scalar(
        select(ProcessingJob).where(ProcessingJob.lecture_id == lecture_id)
    )
    if existing is not None:
        return existing

    job = ProcessingJob(
        lecture_id=lecture_id,
        status="queued",
        current_stage="validate_upload",
        retry_count=0,
        attempts_by_stage={},
        manual_retry_count=0,
    )
    session.add(job)
    return job


class ProcessingJobManager:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        lease_seconds: int = 300,
        max_stage_attempts: int = 3,
        max_manual_retries: int = 2,
        retry_backoff_seconds: int = 15,
        resume_waiting: bool = False,
    ) -> None:
        self.session_factory = session_factory
        self.lease_seconds = lease_seconds
        self.max_stage_attempts = max_stage_attempts
        self.max_manual_retries = max_manual_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.resume_waiting = resume_waiting

    def claim_next(self, worker_id: str, now: datetime | None = None) -> JobClaim | None:
        timestamp = now or utc_now()
        with self.session_factory() as session:
            self._recover_stale(session, timestamp)
            claimable_statuses = ["queued"]
            if self.resume_waiting:
                claimable_statuses.append("waiting")
            job = session.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.status.in_(claimable_statuses),
                    or_(
                        ProcessingJob.available_at.is_(None),
                        ProcessingJob.available_at <= timestamp,
                    ),
                )
                .order_by(ProcessingJob.created_at, ProcessingJob.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            ).first()
            if job is None:
                session.commit()
                return None

            job.status = "running"
            job.lease_owner = worker_id
            job.lease_expires_at = timestamp + timedelta(seconds=self.lease_seconds)
            lecture = session.get(Lecture, job.lecture_id)
            if lecture is not None:
                lecture.status = "processing"
            session.commit()
            return JobClaim(
                job_id=job.id,
                lecture_id=job.lecture_id,
                worker_id=worker_id,
                current_stage=job.current_stage,
                last_successful_stage=job.last_successful_stage,
            )

    def renew_lease(self, claim: JobClaim, now: datetime | None = None) -> bool:
        timestamp = now or utc_now()
        with self.session_factory() as session:
            result = session.execute(
                update(ProcessingJob)
                .where(
                    ProcessingJob.id == claim.job_id,
                    ProcessingJob.status == "running",
                    ProcessingJob.lease_owner == claim.worker_id,
                    ProcessingJob.lease_expires_at > timestamp,
                )
                .values(lease_expires_at=timestamp + timedelta(seconds=self.lease_seconds))
            )
            session.commit()
            return result.rowcount == 1

    def start_stage(self, claim: JobClaim, stage: str, now: datetime | None = None) -> int:
        timestamp = now or utc_now()
        with self.session_factory() as session:
            job = self._owned_job(session, claim, timestamp)
            attempts = dict(job.attempts_by_stage or {})
            stage_attempts = attempts.get(stage, 0) + 1
            attempts[stage] = stage_attempts
            job.attempts_by_stage = attempts
            job.current_stage = stage
            session.commit()
            return stage_attempts

    def complete_stage(self, claim: JobClaim, stage: str, now: datetime | None = None) -> None:
        timestamp = now or utc_now()
        with self.session_factory() as session:
            job = self._owned_job(session, claim, timestamp)
            if job.current_stage is None and job.last_successful_stage == stage:
                return
            if job.current_stage != stage:
                raise JobError("The completed stage does not match the current stage.")
            job.last_successful_stage = stage
            job.current_stage = None
            session.commit()

    def wait_for_stage(
        self,
        claim: JobClaim,
        next_stage: str,
        now: datetime | None = None,
    ) -> None:
        timestamp = now or utc_now()
        with self.session_factory() as session:
            job = session.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.id == claim.job_id)
                .with_for_update()
            ).first()
            if (
                job is not None
                and job.status == "waiting"
                and job.current_stage == next_stage
                and job.lease_owner is None
            ):
                return
            job = self._owned_job(session, claim, timestamp)
            job.status = "waiting"
            job.current_stage = next_stage
            job.lease_owner = None
            job.lease_expires_at = None
            job.available_at = None
            lecture = session.get(Lecture, job.lecture_id)
            if lecture is not None:
                lecture.status = "awaiting_transcription"
            session.commit()

    def complete_job(self, claim: JobClaim, now: datetime | None = None) -> None:
        timestamp = now or utc_now()
        with self.session_factory() as session:
            existing = session.get(ProcessingJob, claim.job_id, with_for_update=True)
            if existing is not None and existing.status == "completed":
                return
            job = self._owned_job(session, claim, timestamp)
            job.status = "completed"
            job.current_stage = None
            job.last_error = None
            job.lease_owner = None
            job.lease_expires_at = None
            job.available_at = None
            lecture = session.get(Lecture, job.lecture_id)
            if lecture is not None:
                lecture.status = "completed"
            session.commit()

    def fail_stage(
        self,
        claim: JobClaim,
        stage: str,
        safe_message: str,
        now: datetime | None = None,
        *,
        retryable: bool = True,
    ) -> None:
        timestamp = now or utc_now()
        with self.session_factory() as session:
            job = self._owned_job(session, claim, timestamp)
            if job.current_stage != stage:
                raise JobError("The failed stage does not match the current stage.")
            attempts = dict(job.attempts_by_stage or {})
            stage_attempts = attempts.get(stage, 0)
            job.retry_count += 1
            job.last_error = safe_message[:2000]
            job.lease_owner = None
            job.lease_expires_at = None
            lecture = session.get(Lecture, job.lecture_id)
            if retryable and stage_attempts < self.max_stage_attempts:
                delay = min(
                    self.retry_backoff_seconds
                    * (2 ** min(max(stage_attempts - 1, 0), 10)),
                    300,
                )
                job.status = "queued"
                job.available_at = timestamp + timedelta(seconds=delay)
                if lecture is not None:
                    lecture.status = "queued"
            else:
                job.status = "failed"
                job.available_at = None
                if lecture is not None:
                    lecture.status = "failed"
            session.commit()

    def recover_stale_jobs(self, now: datetime | None = None) -> int:
        timestamp = now or utc_now()
        with self.session_factory() as session:
            recovered = self._recover_stale(session, timestamp)
            session.commit()
            return recovered

    def retry_failed(self, lecture_id: str, now: datetime | None = None) -> ProcessingJob:
        timestamp = now or utc_now()
        with self.session_factory() as session:
            job = session.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.lecture_id == lecture_id)
                .with_for_update()
            ).first()
            if job is None:
                raise LookupError("Processing job was not found.")
            if job.status != "failed":
                raise JobNotRetryable("Only failed processing jobs can be retried.")
            if job.manual_retry_count >= self.max_manual_retries:
                raise RetryLimitReached("The manual retry limit has been reached.")

            stage = job.current_stage or "validate_upload"
            attempts = dict(job.attempts_by_stage or {})
            attempts[stage] = 0
            job.attempts_by_stage = attempts
            job.manual_retry_count += 1
            job.status = "queued"
            job.current_stage = stage
            job.last_error = None
            job.available_at = timestamp
            job.lease_owner = None
            job.lease_expires_at = None
            lecture = session.get(Lecture, lecture_id)
            if lecture is not None:
                lecture.status = "queued"
            session.commit()
            session.refresh(job)
            return job

    def queue_regeneration(
        self,
        lecture_id: str,
        feature: str,
        now: datetime | None = None,
    ) -> ProcessingJob:
        stage_by_feature = {
            "notes": "regenerate_notes",
            "explanations": "regenerate_explanations",
            "revision-points": "regenerate_revision_points",
            "quiz": "regenerate_quiz",
        }
        cache_types_by_feature = {
            "notes": ("notes_chunk", "notes_final"),
            "explanations": ("explanations_final",),
            "revision-points": ("revision_points_final",),
            "quiz": ("quiz_final",),
        }
        stage = stage_by_feature.get(feature)
        if stage is None:
            raise ValueError("The requested output cannot be regenerated.")

        timestamp = now or utc_now()
        with self.session_factory() as session:
            job = session.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.lecture_id == lecture_id)
                .with_for_update()
            ).first()
            if job is None:
                raise LookupError("Processing job was not found.")
            if job.status != "completed":
                raise JobNotRetryable("Output can only be regenerated after processing completes.")
            transcript = session.scalar(
                select(Transcript).where(Transcript.lecture_id == lecture_id)
            )
            if transcript is None:
                raise JobNotRetryable("A saved transcript is required to regenerate output.")

            transcript_hash = hashlib.sha256(
                transcript.cleaned_text.encode("utf-8")
            ).hexdigest()
            session.execute(
                delete(GenerationChunk).where(
                    GenerationChunk.lecture_id == lecture_id,
                    GenerationChunk.transcript_hash == transcript_hash,
                    GenerationChunk.output_type.in_(cache_types_by_feature[feature]),
                )
            )

            attempts = dict(job.attempts_by_stage or {})
            attempts[stage] = 0
            job.attempts_by_stage = attempts
            job.status = "queued"
            job.current_stage = stage
            job.last_error = None
            job.available_at = timestamp
            job.lease_owner = None
            job.lease_expires_at = None
            lecture = session.get(Lecture, lecture_id)
            if lecture is not None:
                lecture.status = "queued"
            session.commit()
            session.refresh(job)
            return job

    def get_for_lecture(self, lecture_id: str) -> ProcessingJob | None:
        with self.session_factory() as session:
            return session.scalar(
                select(ProcessingJob).where(ProcessingJob.lecture_id == lecture_id)
            )

    def get_by_id(self, job_id: str) -> ProcessingJob | None:
        with self.session_factory() as session:
            return session.get(ProcessingJob, job_id)

    def _recover_stale(self, session: Session, timestamp: datetime) -> int:
        stale_jobs = session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.status == "running",
                ProcessingJob.lease_expires_at <= timestamp,
            )
            .with_for_update(skip_locked=True)
        ).all()
        for job in stale_jobs:
            stage = job.current_stage or "validate_upload"
            attempts = dict(job.attempts_by_stage or {})
            job.lease_owner = None
            job.lease_expires_at = None
            job.retry_count += 1
            job.last_error = "Worker lease expired; processing will resume."
            lecture = session.get(Lecture, job.lecture_id)
            if attempts.get(stage, 0) >= self.max_stage_attempts:
                job.status = "failed"
                job.available_at = None
                if lecture is not None:
                    lecture.status = "failed"
            else:
                job.status = "queued"
                job.available_at = timestamp
                if lecture is not None:
                    lecture.status = "queued"
        return len(stale_jobs)

    @staticmethod
    def _owned_job(session: Session, claim: JobClaim, timestamp: datetime) -> ProcessingJob:
        job = session.scalars(
            select(ProcessingJob)
            .where(ProcessingJob.id == claim.job_id)
            .with_for_update()
        ).first()
        if (
            job is None
            or job.status != "running"
            or job.lease_owner != claim.worker_id
            or job.lease_expires_at is None
            or job.lease_expires_at <= timestamp
        ):
            raise LeaseLost("The processing job lease is no longer owned by this worker.")
        return job


StageProcessor = Callable[[JobClaim, ProcessingJobManager], None]


class LeaseHeartbeat:
    def __init__(self, manager: ProcessingJobManager, claim: JobClaim) -> None:
        self.manager = manager
        self.claim = claim
        self.lease_lost = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "LeaseHeartbeat":
        interval = max(1.0, self.manager.lease_seconds / 3)
        self._thread = threading.Thread(
            target=self._run,
            args=(interval,),
            name=f"lease-heartbeat-{self.claim.job_id[:8]}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        del _exc_type, _exc, _traceback
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self.manager.lease_seconds / 3))

    def _run(self, interval: float) -> None:
        while not self._stop.wait(interval):
            try:
                if not self.manager.renew_lease(self.claim):
                    self.lease_lost.set()
                    logger.warning("Processing job lease was lost: %s", self.claim.job_id)
                    return
            except SQLAlchemyError:
                self.lease_lost.set()
                logger.exception("Could not renew processing job lease: %s", self.claim.job_id)
                return


def process_one_job(
    manager: ProcessingJobManager,
    worker_id: str,
    processor: StageProcessor,
) -> bool:
    claim = manager.claim_next(worker_id)
    if claim is None:
        return False

    with LeaseHeartbeat(manager, claim) as heartbeat:
        try:
            processor(claim, manager)
        except LeaseLost:
            logger.warning("Stopped processing after lease loss: %s", claim.job_id)
        except ProcessingError as exc:
            stage = _current_stage(manager, claim.job_id)
            if stage is not None:
                _fail_stage(manager, claim, stage, exc.safe_message, retryable=exc.retryable)
        except Exception:
            logger.exception("Processing job failed: %s", claim.job_id)
            stage = _current_stage(manager, claim.job_id)
            if stage is not None:
                _fail_stage(manager, claim, stage, "Processing failed unexpectedly.")
        if heartbeat.lease_lost.is_set():
            return True
    return True


def _current_stage(manager: ProcessingJobManager, job_id: str) -> str | None:
    job = manager.get_by_id(job_id)
    return job.current_stage if job is not None else None


def _fail_stage(
    manager: ProcessingJobManager,
    claim: JobClaim,
    stage: str,
    safe_message: str,
    *,
    retryable: bool = True,
) -> None:
    try:
        manager.fail_stage(claim, stage, safe_message, retryable=retryable)
    except LeaseLost:
        logger.warning("Could not record failure after lease loss: %s", claim.job_id)
