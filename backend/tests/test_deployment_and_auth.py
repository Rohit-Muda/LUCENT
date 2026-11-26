import base64
from collections.abc import Iterator
from pathlib import Path
import threading

from httpx import Response
from pydantic import SecretStr
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import main
from backend.app.config import Settings, get_settings
from backend.app.database import get_db
from backend.app.routes.lectures import get_audio_storage
from backend.app.routes.pdf import get_pdf_export_service
from backend.app.routes.processing import get_processing_job_manager
from backend.app.models import Base
from backend.app.services.audio_storage import LocalAudioStorage
from backend.app.services.pdf_export import PdfExportService
from backend.app.services.pdf_storage import LocalPdfStorage
from backend.app.services.processing_jobs import ProcessingJobManager, process_one_job
from backend.app.services.study_materials import StudyMaterialService
from backend.app.workers.processor import process_lecture_pipeline
from backend.tests.test_audio_validation import make_wav
from backend.tests.test_security_and_workflow_audit import (
    CountingGeminiGenerator,
    CountingTranscriber,
    send_request,
)


def _basic_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _build_protected_harness(
    tmp_path: Path,
    *,
    environment: str = "production",
    require_auth: bool = True,
    auth_username: str | None = "demo-user",
    auth_password: str | None = "secret-pass",
) -> tuple[object, sessionmaker[Session], Settings, ProcessingJobManager, PdfExportService, object]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    upload_dir = tmp_path / "shared_uploads"
    pdf_dir = tmp_path / "shared_pdfs"
    settings = Settings(
        _env_file=None,
        environment=environment,
        upload_dir=upload_dir,
        pdf_dir=pdf_dir,
        frontend_url="https://notes.example.edu",
        require_auth=require_auth,
        auth_username=SecretStr(auth_username) if auth_username is not None else None,
        auth_password=SecretStr(auth_password) if auth_password is not None else None,
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

    get_settings.cache_clear()
    app = main.create_app()

    def override_db() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_audio_storage] = lambda: LocalAudioStorage(upload_dir)
    app.dependency_overrides[get_processing_job_manager] = lambda: manager
    app.dependency_overrides[get_pdf_export_service] = lambda: pdf_exporter

    return app, factory, settings, manager, pdf_exporter, engine


@pytest.mark.parametrize(
    ("require_auth", "auth_username", "auth_password"),
    [
        (True, None, None),
        (False, "only-user", None),
        (False, None, "only-pass"),
    ],
)
def test_auth_misconfiguration_fails_closed(
    tmp_path: Path,
    require_auth: bool,
    auth_username: str | None,
    auth_password: str | None,
) -> None:
    app, _factory, _settings, _manager, _pdf, engine = _build_protected_harness(
        tmp_path,
        require_auth=require_auth,
        auth_username=auth_username,
        auth_password=auth_password,
    )
    try:
        res: Response = send_request(app, "GET", "/lectures")
        assert res.status_code == 503
        assert res.json()["error"]["code"] == "auth_misconfigured"
        assert send_request(app, "GET", "/health").status_code == 200
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_public_auth_protects_all_lecture_endpoints_and_allows_valid_credentials(
    tmp_path: Path,
) -> None:
    app, factory, settings, manager, pdf_exporter, engine = _build_protected_harness(tmp_path)
    try:
        # Health endpoints remain open for platform health probes
        assert send_request(app, "GET", "/health").status_code == 200

        # Valid authenticated upload + shared-volume processing to populate every resource
        auth_headers = _basic_header("demo-user", "secret-pass")
        upload = send_request(
            app,
            "POST",
            "/lectures",
            files={"file": ("shared_volume.wav", make_wav(), "audio/wav")},
            headers=auth_headers,
        )
        assert upload.status_code == 201
        lecture_id = upload.json()["id"]

        transcriber = CountingTranscriber(
            "Cells convert glucose into usable ATP energy inside mitochondria. ATP is cellular energy."
        )
        generator = CountingGeminiGenerator()
        materials = StudyMaterialService(factory, generator)
        assert (
            process_one_job(
                manager,
                "prod-worker-1",
                lambda claim, job_manager: process_lecture_pipeline(
                    claim,
                    job_manager,
                    settings,
                    transcriber,
                    materials,
                    pdf_exporter,
                ),
            )
            is True
        )

        # Every protected route rejects missing, wrong, and non-Basic authorization
        protected_requests = [
            ("POST", "/lectures"),
            ("GET", "/lectures"),
            ("GET", f"/lectures/{lecture_id}"),
            ("GET", f"/lectures/{lecture_id}/processing"),
            ("POST", f"/lectures/{lecture_id}/retry"),
            ("POST", f"/lectures/{lecture_id}/regenerate/notes"),
            ("GET", f"/lectures/{lecture_id}/transcript"),
            ("GET", f"/lectures/{lecture_id}/notes"),
            ("GET", f"/lectures/{lecture_id}/explanations"),
            ("GET", f"/lectures/{lecture_id}/revision-points"),
            ("GET", f"/lectures/{lecture_id}/quiz"),
            ("POST", f"/lectures/{lecture_id}/quiz/submit"),
            ("GET", f"/lectures/{lecture_id}/pdf"),
        ]
        bad_auth_sets = [
            None,
            _basic_header("demo-user", "wrong-pass"),
            _basic_header("wrong-user", "secret-pass"),
            {"Authorization": "Bearer some-token"},
        ]
        for bad_headers in bad_auth_sets:
            for method, path in protected_requests:
                kwargs = {"headers": bad_headers} if bad_headers else {}
                if method == "POST" and path == "/lectures":
                    kwargs["files"] = {"file": ("unauth.wav", make_wav(), "audio/wav")}
                elif path.endswith("/quiz/submit"):
                    kwargs["json_body"] = {"answers": []}
                res = send_request(app, method, path, **kwargs)
                assert res.status_code == 401, f"Expected 401 for {method} {path}, got {res.status_code}"
                assert res.headers.get("www-authenticate") == 'Basic realm="Code-Mixed Lecture Notes"'

        # Authenticated reads & PDF download work as expected
        for method, path in [
            ("GET", "/lectures"),
            ("GET", f"/lectures/{lecture_id}"),
            ("GET", f"/lectures/{lecture_id}/processing"),
            ("GET", f"/lectures/{lecture_id}/transcript"),
            ("GET", f"/lectures/{lecture_id}/notes"),
            ("GET", f"/lectures/{lecture_id}/explanations"),
            ("GET", f"/lectures/{lecture_id}/revision-points"),
            ("GET", f"/lectures/{lecture_id}/quiz"),
            ("GET", f"/lectures/{lecture_id}/pdf"),
        ]:
            res = send_request(app, method, path, headers=auth_headers)
            assert res.status_code == 200, f"Expected 200 for {method} {path}, got {res.status_code}"
            if path.endswith("/pdf"):
                assert res.content.startswith(b"%PDF-")
                assert "attachment" in res.headers.get("content-disposition", "")
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_production_environment_cors_and_hidden_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("FRONTEND_URL", "https://notes.example.edu")
    monkeypatch.setenv("AUTH_USERNAME", "ops")
    monkeypatch.setenv("AUTH_PASSWORD", "ops-pass")
    get_settings.cache_clear()

    try:
        app = main.create_app()
        # Interactive API docs are disabled in production
        assert send_request(app, "GET", "/docs").status_code == 404
        assert send_request(app, "GET", "/openapi.json").status_code == 404

        # CORS preflight allows Authorization header and exposes Content-Disposition
        preflight = send_request(
            app,
            "OPTIONS",
            "/lectures",
            headers={
                "Origin": "https://notes.example.edu",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers.get("access-control-allow-origin") == "https://notes.example.edu"
        allowed_headers = preflight.headers.get("access-control-allow-headers", "").lower()
        assert "authorization" in allowed_headers
    finally:
        get_settings.cache_clear()


def test_shared_storage_survives_separate_api_and_worker_instances(tmp_path: Path) -> None:
    app, factory, settings, manager, _worker_pdf, engine = _build_protected_harness(tmp_path)
    try:
        auth_headers = _basic_header("demo-user", "secret-pass")
        upload = send_request(
            app,
            "POST",
            "/lectures",
            files={"file": ("shared_disk.wav", make_wav(), "audio/wav")},
            headers=auth_headers,
        )
        assert upload.status_code == 201
        lecture_id = upload.json()["id"]

        # Simulate separate worker process reading the same persistent volume
        worker_pdf_exporter = PdfExportService(factory, LocalPdfStorage(settings.pdf_dir))
        transcriber = CountingTranscriber(
            "Cells convert glucose into usable ATP energy inside mitochondria. ATP is cellular energy."
        )
        materials = StudyMaterialService(factory, CountingGeminiGenerator())
        assert (
            process_one_job(
                manager,
                "separate-worker",
                lambda claim, job_manager: process_lecture_pipeline(
                    claim,
                    job_manager,
                    settings,
                    transcriber,
                    materials,
                    worker_pdf_exporter,
                ),
            )
            is True
        )

        # Simulate separate API instance serving PDF written by worker
        api_pdf_res = send_request(
            app,
            "GET",
            f"/lectures/{lecture_id}/pdf",
            headers=auth_headers,
        )
        assert api_pdf_res.status_code == 200
        assert api_pdf_res.content.startswith(b"%PDF-")
        # Worker produced file on shared volume; API reused it cleanly (only 1 file exists)
        assert len(list(settings.pdf_dir.glob("*.pdf"))) == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_worker_shutdown_signal_sets_stop_event(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.workers import run as worker_run

    handlers: dict[int, object] = {}
    monkeypatch.setattr(
        worker_run.signal,
        "signal",
        lambda sig, fn: handlers.setdefault(sig, fn),
    )
    stop_event = threading.Event()
    worker_run._register_shutdown_signals(stop_event)
    assert worker_run.signal.SIGINT in handlers
    handlers[worker_run.signal.SIGINT](worker_run.signal.SIGINT, None)
    assert stop_event.is_set()
