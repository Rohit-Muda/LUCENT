from pathlib import Path

import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.config import Settings, get_settings
from backend.app.database import get_session_factory
from backend.app.main import create_app
from backend.app.models import (
    Base,
    ConceptExplanation,
    Lecture,
    LecturePdf,
    Notes,
    RevisionPoint,
    Transcript,
)
from backend.app.services.audio_storage import StorageError
from backend.app.services.pdf_export import (
    PdfExportService,
    PdfLectureNotFoundError,
    PdfMaterialNotReadyError,
    format_mixed_script_text,
    render_lecture_pdf,
)
from backend.app.services.pdf_storage import LocalPdfStorage
from backend.app.services.processing_jobs import ProcessingJobManager, enqueue_processing_job
from backend.app.workers.processor import process_lecture_pipeline


def _create_sqlite_session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _seed_lecture_materials(
    session_factory: sessionmaker,
    *,
    lecture_id: str = "lec-pdf-1",
    section_count: int = 2,
    include_explanations: bool = True,
    include_revision: bool = True,
) -> None:
    with session_factory() as session:
        lecture = Lecture(
            id=lecture_id,
            title="Binary Search and Time Complexity",
            original_filename="lecture_01.wav",
            storage_key=f"{lecture_id}.wav",
            media_type="audio/wav",
            file_size_bytes=2048,
            duration_seconds=125.0,
            status="completed",
        )
        session.add(lecture)
        session.add(
            Transcript(
                lecture_id=lecture_id,
                original_text="Binary search divides the sorted array.",
                cleaned_text="Binary search divides the sorted array.",
            )
        )
        sections = [
            {
                "heading": f"Section {idx}: Divide and Conquer",
                "summary": (
                    f"Binary search (బైనరీ సెర్చ్) repeatedly halves the search interval "
                    f"in a sorted array during pass {idx}."
                ),
                "key_points": [
                    "Requires a sorted array before searching.",
                    "Time complexity is O(log n) in the worst case.",
                    "విద్యార్థులు middle index overflow గురించి జాగ్రత్తగా ఉండాలి.",
                ],
                "source_excerpt": "Binary search divides the sorted array in half at each step.",
            }
            for idx in range(1, section_count + 1)
        ]
        session.add(
            Notes(
                lecture_id=lecture_id,
                content={
                    "title": "Binary Search and Time Complexity",
                    "sections": sections,
                    "concepts": [
                        {"name": "Binary Search", "source_excerpt": "Binary search divides the sorted array."},
                        {"name": "Logarithmic Complexity", "source_excerpt": "O(log n) complexity"},
                    ],
                },
            )
        )
        if include_explanations:
            session.add(
                ConceptExplanation(
                    lecture_id=lecture_id,
                    position=0,
                    concept="Binary Search",
                    source_excerpt="array sorted గా ఉంటేనే",
                    explanation_telugu=(
                        "బైనరీ సెర్చ్ అనేది క్రమబద్ధీకరించబడిన (sorted) శ్రేణిలో మధ్య మూలకాన్ని "
                        "పోల్చడం ద్వారా శోధన పరిధిని సగానికి తగ్గించే ప్రక్రియ."
                    ),
                )
            )
            session.add(
                ConceptExplanation(
                    lecture_id=lecture_id,
                    position=1,
                    concept="Logarithmic Complexity",
                    source_excerpt="O(log n) complexity",
                    explanation_telugu=(
                        "ప్రతి దశలో డేటా పరిమాణం సగానికి తగ్గుతుంది కాబట్టి విద్యార్థులు దీనిని "
                        "O(log n) అల్గారిథమ్ క్షేత్రంగా గుర్తుంచుకోవాలి."
                    ),
                )
            )
        if include_revision:
            session.add(
                RevisionPoint(
                    lecture_id=lecture_id,
                    position=0,
                    content="Always verify the input array is sorted before applying binary search.",
                    source_excerpt="Binary search divides the sorted array.",
                )
            )
            session.add(
                RevisionPoint(
                    lecture_id=lecture_id,
                    position=1,
                    content="Use mid = low + (high - low) // 2 to avoid integer overflow.",
                    source_excerpt=None,
                )
            )
        session.commit()


def test_format_mixed_script_text_separates_boundaries_and_escapes_xml() -> None:
    formatted = format_mixed_script_text("Search (బైనరీ సెర్చ్) & O(log n) <test>.")
    assert "&amp;" in formatted
    assert "&lt;test&gt;" in formatted
    assert '<font name="NotoSansTelugu">బైనరీ సెర్చ్</font>' in formatted
    assert "( <font" in formatted
    assert "</font> )" in formatted


def test_render_lecture_pdf_handles_telugu_and_multipage_content() -> None:
    session_factory = _create_sqlite_session_factory()
    _seed_lecture_materials(session_factory, section_count=16)

    with session_factory() as session:
        lecture = session.get(Lecture, "lec-pdf-1")
        notes = session.scalar(select(Notes).where(Notes.lecture_id == "lec-pdf-1"))
        explanations = list(session.scalars(select(ConceptExplanation)).all())
        revision_points = list(session.scalars(select(RevisionPoint)).all())

    assert lecture is not None and notes is not None
    pdf_bytes = render_lecture_pdf(
        title="Binary Search and Time Complexity",
        original_filename=lecture.original_filename,
        duration_seconds=lecture.duration_seconds,
        notes_content=notes.content,
        explanations=explanations,
        revision_points=revision_points,
    )

    assert pdf_bytes.startswith(b"%PDF-")
    doc = pdfium.PdfDocument(pdf_bytes)
    assert len(doc) >= 2
    extracted = "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "Binary Search and Time Complexity" in extracted
    assert "Structured Study Notes" in extracted
    assert "Telugu-Supported Concept Explanations" in extracted
    assert "Key Revision Points" in extracted
    assert f"Page 1 of {len(doc)}" in extracted
    assert f"Page {len(doc)} of {len(doc)}" in extracted


def test_pdf_storage_rejects_path_traversal(tmp_path: Path) -> None:
    storage = LocalPdfStorage(tmp_path)
    with pytest.raises(StorageError):
        storage.path_for("../escape.pdf")
    with pytest.raises(StorageError):
        storage.path_for("sub/file.pdf")
    with pytest.raises(StorageError):
        storage.path_for("not-a-pdf.txt")
    with pytest.raises(StorageError):
        storage.store_bytes(b"")


def test_pdf_export_service_persists_and_reuses_saved_pdf(tmp_path: Path) -> None:
    session_factory = _create_sqlite_session_factory()
    _seed_lecture_materials(session_factory)
    storage = LocalPdfStorage(tmp_path / "pdfs")
    service = PdfExportService(session_factory, storage)

    first = service.ensure_pdf("lec-pdf-1")
    assert first.reused is False
    assert first.path.is_file()
    assert first.path.read_bytes().startswith(b"%PDF-")

    second = service.ensure_pdf("lec-pdf-1")
    assert second.reused is True
    assert second.storage_key == first.storage_key

    # Regenerate notes -> content_hash changes -> PDF is refreshed and old file removed
    with session_factory() as session:
        notes = session.scalar(select(Notes).where(Notes.lecture_id == "lec-pdf-1"))
        assert notes is not None
        updated_content = dict(notes.content)
        updated_content["title"] = "Updated Binary Search Notes"
        notes.content = updated_content
        session.commit()

    third = service.ensure_pdf("lec-pdf-1")
    assert third.reused is False
    assert third.storage_key != first.storage_key
    assert third.path.is_file()
    assert not first.path.exists()

    with session_factory() as session:
        record = session.scalar(select(LecturePdf).where(LecturePdf.lecture_id == "lec-pdf-1"))
        assert record is not None
        assert record.storage_key == third.storage_key
        assert record.file_size_bytes == third.file_size_bytes


def test_pdf_export_service_errors_when_missing_lecture_or_notes(tmp_path: Path) -> None:
    session_factory = _create_sqlite_session_factory()
    storage = LocalPdfStorage(tmp_path / "pdfs")
    service = PdfExportService(session_factory, storage)

    with pytest.raises(PdfLectureNotFoundError):
        service.ensure_pdf("missing-lecture")

    with session_factory() as session:
        session.add(
            Lecture(
                id="lec-no-notes",
                original_filename="raw.wav",
                storage_key="raw.wav",
                media_type="audio/wav",
                file_size_bytes=512,
                status="queued",
            )
        )
        session.commit()

    with pytest.raises(PdfMaterialNotReadyError):
        service.ensure_pdf("lec-no-notes")


def test_pdf_download_endpoint_streams_and_reuses_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_factory = _create_sqlite_session_factory()
    _seed_lecture_materials(session_factory)
    pdf_dir = tmp_path / "generated_pdfs"

    app = create_app()
    settings = Settings(_env_file=None, pdf_dir=pdf_dir)
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr("backend.app.routes.pdf.get_session_factory", lambda: session_factory)

    client = TestClient(app)
    first_resp = client.get("/lectures/lec-pdf-1/pdf")
    assert first_resp.status_code == 200
    assert first_resp.headers["content-type"] == "application/pdf"
    assert "attachment;" in first_resp.headers["content-disposition"]
    assert first_resp.content.startswith(b"%PDF-")

    second_resp = client.get("/lectures/lec-pdf-1/pdf")
    assert second_resp.status_code == 200
    assert second_resp.content == first_resp.content

    missing_resp = client.get("/lectures/unknown-id/pdf")
    assert missing_resp.status_code == 404
    assert missing_resp.json()["error"]["code"] == "lecture_not_found"


def test_pdf_download_endpoint_returns_409_when_notes_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_factory = _create_sqlite_session_factory()
    with session_factory() as session:
        session.add(
            Lecture(
                id="lec-pending",
                original_filename="pending.wav",
                storage_key="pending.wav",
                media_type="audio/wav",
                file_size_bytes=512,
                status="queued",
            )
        )
        session.commit()

    app = create_app()
    settings = Settings(_env_file=None, pdf_dir=tmp_path / "generated_pdfs")
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr("backend.app.routes.pdf.get_session_factory", lambda: session_factory)

    client = TestClient(app)
    response = client.get("/lectures/lec-pending/pdf")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "pdf_materials_not_ready"


def test_worker_pipeline_runs_generate_pdf_stage(tmp_path: Path) -> None:
    session_factory = _create_sqlite_session_factory()
    _seed_lecture_materials(session_factory, lecture_id="lec-worker-pdf")
    with session_factory() as session:
        job = enqueue_processing_job(session, "lec-worker-pdf")
        job.last_successful_stage = "generate_quiz"
        job.current_stage = None
        session.commit()

    manager = ProcessingJobManager(session_factory)
    claim = manager.claim_next("pdf-worker")
    assert claim is not None

    class NoOpTranscriber:
        def transcribe(self, audio_path: Path) -> object:
            raise AssertionError("Should not transcribe")

    class NoOpMaterials:
        def generate_notes(self, lecture_id: str, transcript: str) -> object:
            raise AssertionError("Should not generate notes")

        def generate_explanations(self, lecture_id: str, transcript: str) -> object:
            raise AssertionError("Should not generate explanations")

        def generate_revision_points(self, lecture_id: str, transcript: str) -> object:
            raise AssertionError("Should not generate revision points")

        def generate_quiz(self, lecture_id: str, transcript: str) -> object:
            raise AssertionError("Should not generate quiz")

    pdf_exporter = PdfExportService(session_factory, LocalPdfStorage(tmp_path / "pdfs"))
    process_lecture_pipeline(
        claim,
        manager,
        Settings(_env_file=None),
        NoOpTranscriber(),
        NoOpMaterials(),
        pdf_exporter,
    )

    with session_factory() as session:
        record = session.scalar(select(LecturePdf).where(LecturePdf.lecture_id == "lec-worker-pdf"))
        assert record is not None
        assert (tmp_path / "pdfs" / record.storage_key).is_file()
