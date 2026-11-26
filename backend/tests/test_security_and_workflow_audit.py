import asyncio
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient, Response
import pytest
from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import main
from backend.app.config import Settings
from backend.app.database import get_db
from backend.app.models import Base, LecturePdf
from backend.app.providers.gemini_generator import GeminiProviderError
from backend.app.providers.groq_transcriber import TranscriptionResult
from backend.app.routes.lectures import get_audio_storage
from backend.app.routes.pdf import get_pdf_export_service
from backend.app.routes.processing import get_processing_job_manager
from backend.app.services.audio_storage import LocalAudioStorage
from backend.app.services.audio_validation import sanitize_original_filename
from backend.app.services.pdf_export import PdfExportService
from backend.app.services.pdf_storage import LocalPdfStorage
from backend.app.services.processing_jobs import ProcessingJobManager, process_one_job
from backend.app.services.study_materials import StudyMaterialService
from backend.app.workers.processor import process_lecture_pipeline
from backend.tests.test_audio_validation import make_wav


@dataclass
class WorkflowHarness:
    app: object
    engine: Engine
    factory: sessionmaker[Session]
    settings: Settings
    upload_dir: Path
    pdf_dir: Path
    manager: ProcessingJobManager
    pdf_exporter: PdfExportService


@pytest.fixture
def workflow_harness(tmp_path: Path) -> Iterator[WorkflowHarness]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    upload_dir = tmp_path / "uploads"
    pdf_dir = tmp_path / "pdfs"
    settings = Settings(
        _env_file=None,
        upload_dir=upload_dir,
        pdf_dir=pdf_dir,
        frontend_url="https://notes.example.edu, http://localhost:5173",
        max_upload_size_bytes=200_000,
        max_audio_duration_seconds=120,
        groq_max_audio_size_bytes=200_000,
    )

    manager = ProcessingJobManager(
        factory,
        lease_seconds=120,
        max_stage_attempts=2,
        max_manual_retries=2,
        retry_backoff_seconds=1,
    )
    pdf_exporter = PdfExportService(factory, LocalPdfStorage(pdf_dir))

    app = main.create_app()

    def override_db() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[main.get_settings] = lambda: settings
    app.dependency_overrides[get_audio_storage] = lambda: LocalAudioStorage(upload_dir)
    app.dependency_overrides[get_processing_job_manager] = lambda: manager
    app.dependency_overrides[get_pdf_export_service] = lambda: pdf_exporter

    yield WorkflowHarness(
        app=app,
        engine=engine,
        factory=factory,
        settings=settings,
        upload_dir=upload_dir,
        pdf_dir=pdf_dir,
        manager=manager,
        pdf_exporter=pdf_exporter,
    )

    app.dependency_overrides.clear()
    engine.dispose()


class CountingTranscriber:
    def __init__(self, transcript_text: str) -> None:
        self.transcript_text = transcript_text
        self.calls = 0

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        assert audio_path.is_file()
        self.calls += 1
        return TranscriptionResult(
            text=self.transcript_text,
            segments=[{"start": 0.0, "end": 1.0, "text": self.transcript_text}],
            detected_language="te",
            duration_seconds=1.0,
        )


class CountingGeminiGenerator:
    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.calls = 0
        self.fail_on_call = fail_on_call

    def generate_json(self, prompt: str, schema: type[BaseModel]) -> str:
        del prompt
        self.calls += 1
        if self.fail_on_call == self.calls:
            raise GeminiProviderError(
                "provider_request",
                "Gemini temporarily rejected the prompt.",
                retryable=False,
            )

        schema_name = schema.__name__
        if schema_name == "NotesContent":
            return json.dumps(
                {
                    "title": "Cellular Respiration Basics",
                    "sections": [
                        {
                            "heading": "ATP Synthesis",
                            "summary": "Cells convert glucose into usable ATP energy.",
                            "key_points": [
                                "Glycolysis begins in the cytoplasm",
                                "Mitochondria produce ATP during aerobic respiration",
                            ],
                            "source_excerpt": "Cells convert glucose into usable ATP energy inside mitochondria.",
                        }
                    ],
                    "concepts": [
                        {
                            "name": "ATP",
                            "source_excerpt": "Cells convert glucose into usable ATP energy inside mitochondria.",
                        }
                    ],
                }
            )
        if schema_name == "ExplanationsContent":
            return json.dumps(
                {
                    "explanations": [
                        {
                            "concept": "ATP",
                            "source_excerpt": "Cells convert glucose into usable ATP energy inside mitochondria.",
                            "explanation_telugu": "ATP కణాలకు అవసరమైన తక్షణ శక్తి వనరు.",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        if schema_name == "RevisionPointsContent":
            return json.dumps(
                {
                    "points": [
                        {
                            "content": "Cells convert glucose into ATP energy inside mitochondria.",
                            "source_excerpt": "Cells convert glucose into usable ATP energy inside mitochondria.",
                        }
                    ]
                }
            )
        if schema_name == "QuizContent":
            return json.dumps(
                {
                    "questions": [
                        {
                            "question": f"Lecture check question {idx + 1} about ATP?",
                            "options": [
                                "Mitochondria energy currency",
                                f"Distractor A-{idx}",
                                f"Distractor B-{idx}",
                                f"Distractor C-{idx}",
                            ],
                            "correct_option_index": 0,
                            "explanation": "ATP serves as usable cellular energy.",
                            "source_excerpt": "Cells convert glucose into usable ATP energy inside mitochondria.",
                        }
                        for idx in range(5)
                    ]
                }
            )
        raise AssertionError(f"Unexpected schema requested: {schema_name}")


def send_request(
    app: object,
    method: str,
    url: str,
    *,
    files: dict[str, tuple[str, bytes, str]] | None = None,
    json_body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    async def _do() -> Response:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            return await client.request(
                method,
                url,
                files=files,
                json=json_body,
                headers=headers,
            )

    return asyncio.run(_do())


def test_cors_allows_configured_origins_and_rejects_wildcard() -> None:
    settings = Settings(
        _env_file=None,
        frontend_url="*, https://app.example.com/ , http://localhost:5173",
    )
    assert settings.cors_origins == ["https://app.example.com", "http://localhost:5173"]

    app = main.create_app()
    allowed = send_request(
        app,
        "OPTIONS",
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    disallowed = send_request(
        app,
        "OPTIONS",
        "/health",
        headers={
            "Origin": "https://evil.example.net",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in disallowed.headers


def test_filename_sanitization_blocks_path_traversal_and_null_bytes() -> None:
    assert sanitize_original_filename("../../etc/passwd/lecture.wav") == "lecture.wav"
    assert sanitize_original_filename("C:\\Users\\victim\\notes\x00.mp3") == "notes.mp3"
    for invalid in ("", ".", "..", "../../..", "\x00\x01"):
        with pytest.raises(Exception):
            sanitize_original_filename(invalid)


def test_unhandled_exception_returns_safe_json_without_traceback() -> None:
    app = main.create_app()
    boom_router = APIRouter()

    @boom_router.get("/boom")
    def trigger_boom() -> dict[str, str]:
        raise RuntimeError("secret_database_password_leak")

    app.include_router(boom_router)

    response = send_request(app, "GET", "/boom")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_server_error",
            "message": "An unexpected internal error occurred.",
        }
    }
    assert "secret_database_password_leak" not in response.text
    assert "Traceback" not in response.text


def test_frontend_sources_contain_no_backend_secrets_or_raw_html_injection() -> None:
    frontend_src = Path(__file__).resolve().parents[2] / "frontend" / "src"
    forbidden_tokens = ("GROQ_API_KEY", "GEMINI_API_KEY", "DATABASE_URL", "dangerouslySetInnerHTML")
    for source_file in frontend_src.rglob("*.js*"):
        if source_file.name.endswith((".test.js", ".test.jsx")):
            continue
        content = source_file.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in content, f"Forbidden token {token} found in {source_file}"


def test_end_to_end_upload_to_reopen_workflow_reuses_saved_outputs_without_repeat_ai_calls(
    workflow_harness: WorkflowHarness,
) -> None:
    # 1. Upload valid WAV audio
    upload_res = send_request(
        workflow_harness.app,
        "POST",
        "/lectures",
        files={"file": ("biology_telugu.wav", make_wav(), "audio/wav")},
    )
    assert upload_res.status_code == 201
    lecture_id = upload_res.json()["id"]

    # 2. Worker executes full pipeline (Groq + Gemini + PDF)
    transcriber = CountingTranscriber(
        "Cells convert glucose into usable ATP energy inside mitochondria. ATP is cellular energy."
    )
    generator = CountingGeminiGenerator()
    materials = StudyMaterialService(workflow_harness.factory, generator)

    handled = process_one_job(
        workflow_harness.manager,
        "audit-worker-1",
        lambda claim, job_manager: process_lecture_pipeline(
            claim,
            job_manager,
            workflow_harness.settings,
            transcriber,
            materials,
            workflow_harness.pdf_exporter,
        ),
    )
    assert handled is True
    assert transcriber.calls == 1
    assert generator.calls == 4

    # 3. Verify processing, lecture history, and all saved study outputs
    status_res = send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/processing")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "completed"
    assert status_res.json()["last_successful_stage"] == "generate_pdf"

    history_res = send_request(workflow_harness.app, "GET", "/lectures")
    assert history_res.status_code == 200
    assert history_res.json()["total"] == 1
    assert history_res.json()["items"][0]["status"] == "completed"

    transcript_res = send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/transcript")
    notes_res = send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/notes")
    explanations_res = send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/explanations")
    revision_res = send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/revision-points")
    assert transcript_res.status_code == 200
    assert notes_res.status_code == 200
    assert explanations_res.status_code == 200
    assert "ATP కణాలకు" in explanations_res.json()[0]["explanation_telugu"]
    assert revision_res.status_code == 200

    # 4. Quiz security: answers absent before submission, graded on complete submission
    quiz_res = send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/quiz")
    assert quiz_res.status_code == 200
    assert "correct_option_position" not in quiz_res.text
    assert "explanation" not in quiz_res.text
    questions = quiz_res.json()["questions"]
    assert len(questions) == 5

    submit_res = send_request(
        workflow_harness.app,
        "POST",
        f"/lectures/{lecture_id}/quiz/submit",
        json_body={
            "answers": [
                {"question_id": q["id"], "selected_option_position": 0}
                for q in questions
            ]
        },
    )
    assert submit_res.status_code == 200
    assert submit_res.json()["score"] == 5
    assert submit_res.json()["total_questions"] == 5

    # 5. PDF download + re-download reuse check
    pdf_first = send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/pdf")
    pdf_second = send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/pdf")
    assert pdf_first.status_code == 200
    assert pdf_first.headers["content-type"] == "application/pdf"
    assert pdf_first.content.startswith(b"%PDF-")
    assert pdf_second.status_code == 200
    assert pdf_second.content == pdf_first.content
    assert len(list(workflow_harness.pdf_dir.glob("*.pdf"))) == 1
    with workflow_harness.factory() as session:
        assert session.scalar(select(LecturePdf).where(LecturePdf.lecture_id == lecture_id)) is not None

    # 6. Reopening saved lecture/study routes makes zero additional AI calls
    send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}")
    send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/transcript")
    send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/notes")
    send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/explanations")
    send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/revision-points")
    send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/quiz")

    assert transcriber.calls == 1
    assert generator.calls == 4


def test_stage_failure_preserves_completed_outputs_and_resumes_without_repeat_calls(
    workflow_harness: WorkflowHarness,
) -> None:
    upload_res = send_request(
        workflow_harness.app,
        "POST",
        "/lectures",
        files={"file": ("partial.wav", make_wav(), "audio/wav")},
    )
    lecture_id = upload_res.json()["id"]

    transcriber = CountingTranscriber(
        "Cells convert glucose into usable ATP energy inside mitochondria. ATP is cellular energy."
    )
    # Call 1: notes (ok), Call 2: explanations (ok), Call 3: revision points (fail non-retryably)
    failing_generator = CountingGeminiGenerator(fail_on_call=3)
    failing_materials = StudyMaterialService(workflow_harness.factory, failing_generator)

    process_one_job(
        workflow_harness.manager,
        "audit-worker-fail",
        lambda claim, job_manager: process_lecture_pipeline(
            claim,
            job_manager,
            workflow_harness.settings,
            transcriber,
            failing_materials,
            workflow_harness.pdf_exporter,
        ),
    )

    failed_status = send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/processing").json()
    assert failed_status["status"] == "failed"
    assert failed_status["last_successful_stage"] == "generate_explanations"
    assert failed_status["can_retry"] is True

    # Earlier outputs remain accessible despite later stage failure
    assert send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/transcript").status_code == 200
    assert send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/notes").status_code == 200
    assert send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/explanations").status_code == 200
    assert send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/revision-points").status_code == 404

    # Retry and resume: must NOT re-run Groq or notes/explanations Gemini calls!
    retried = send_request(workflow_harness.app, "POST", f"/lectures/{lecture_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"

    healthy_generator = CountingGeminiGenerator()
    healthy_materials = StudyMaterialService(workflow_harness.factory, healthy_generator)
    process_one_job(
        workflow_harness.manager,
        "audit-worker-resume",
        lambda claim, job_manager: process_lecture_pipeline(
            claim,
            job_manager,
            workflow_harness.settings,
            transcriber,
            healthy_materials,
            workflow_harness.pdf_exporter,
        ),
    )

    recovered_status = send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/processing").json()
    assert recovered_status["status"] == "completed"
    assert transcriber.calls == 1
    # Only revision points + quiz ran on resume (2 calls, not 4!)
    assert healthy_generator.calls == 2
    assert send_request(workflow_harness.app, "GET", f"/lectures/{lecture_id}/pdf").status_code == 200
