import logging
import signal
import socket
import threading
import uuid

from backend.app.config import get_settings
from backend.app.database import get_engine, get_session_factory
from backend.app.providers.gemini_generator import GeminiJsonGenerator
from backend.app.providers.groq_transcriber import GroqTranscriber
from backend.app.services.pdf_export import PdfExportService
from backend.app.services.pdf_storage import LocalPdfStorage
from backend.app.services.processing_jobs import ProcessingJobManager, process_one_job
from backend.app.services.study_materials import StudyMaterialService
from backend.app.workers.processor import process_lecture_pipeline

logger = logging.getLogger(__name__)


def _register_shutdown_signals(stop_event: threading.Event) -> None:
    def _request_stop(signum: int, _frame: object) -> None:
        logger.info("Worker received signal %s; shutting down after current step.", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _request_stop)


def main() -> None:
    settings = get_settings()
    if settings.groq_api_key is None:
        raise RuntimeError("GROQ_API_KEY must be configured before starting the transcription worker.")
    if settings.gemini_api_key is None:
        raise RuntimeError("GEMINI_API_KEY must be configured before starting the study-material worker.")
    logging.basicConfig(
        level=settings.log_level,
        format="%(levelname)s %(name)s: %(message)s",
    )
    stop_event = threading.Event()
    _register_shutdown_signals(stop_event)

    manager = ProcessingJobManager(
        get_session_factory(),
        lease_seconds=settings.processing_job_lease_seconds,
        max_stage_attempts=settings.processing_job_max_stage_attempts,
        max_manual_retries=settings.processing_job_max_manual_retries,
        retry_backoff_seconds=settings.processing_job_retry_backoff_seconds,
        resume_waiting=True,
    )
    transcriber = GroqTranscriber(
        settings.groq_api_key.get_secret_value(),
        settings.groq_model,
        settings.groq_timeout_seconds,
    )
    generator = GeminiJsonGenerator(
        settings.gemini_api_key.get_secret_value(),
        settings.gemini_model,
        settings.gemini_timeout_seconds,
    )
    materials = StudyMaterialService(manager.session_factory, generator)
    pdf_exporter = PdfExportService(manager.session_factory, LocalPdfStorage(settings.pdf_dir))
    worker_id = f"{socket.gethostname()}:{uuid.uuid4().hex}"[:128]
    logger.info("Starting lecture processing worker (worker_id=%s)", worker_id)
    try:
        while not stop_event.is_set():
            handled = process_one_job(
                manager,
                worker_id,
                lambda claim, job_manager: process_lecture_pipeline(
                    claim,
                    job_manager,
                    settings,
                    transcriber,
                    materials,
                    pdf_exporter,
                ),
            )
            if not handled:
                stop_event.wait(timeout=settings.processing_job_poll_interval_seconds)
    finally:
        generator.close()
        if get_engine.cache_info().currsize > 0:
            get_engine().dispose()
        logger.info("Lecture processing worker stopped cleanly.")


if __name__ == "__main__":
    main()
