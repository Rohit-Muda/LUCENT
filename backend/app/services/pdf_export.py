import hashlib
import io
import json
import logging
import re
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import ConceptExplanation, Lecture, LecturePdf, Notes, RevisionPoint
from backend.app.services.audio_storage import StorageError
from backend.app.services.pdf_storage import PdfStorage

logger = logging.getLogger(__name__)

_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_TELUGU_RUN_RE = re.compile(r"([\u0C00-\u0C7F]+(?:\s+[\u0C00-\u0C7F]+)*)")
_LEFT_SCRIPT_BOUNDARY_RE = re.compile(r"(?<=[^\s\u0C00-\u0C7F])(?=[\u0C00-\u0C7F])")
_RIGHT_SCRIPT_BOUNDARY_RE = re.compile(r"(?<=[\u0C00-\u0C7F])(?=[^\s\u0C00-\u0C7F])")
_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
_FONT_LOCK = threading.Lock()
_FONTS_REGISTERED = False


class PdfExportError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        self.safe_message = message
        self.retryable = retryable
        super().__init__(message)


class PdfLectureNotFoundError(LookupError):
    pass


class PdfMaterialNotReadyError(PdfExportError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


@dataclass(frozen=True)
class LecturePdfResult:
    lecture_id: str
    storage_key: str
    filename: str
    file_size_bytes: int
    content_hash: str
    path: Path
    reused: bool


def register_pdf_fonts() -> None:
    """Register shapable Latin and Telugu TrueType fonts once."""
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    with _FONT_LOCK:
        if _FONTS_REGISTERED:
            return
        telugu_regular = _FONTS_DIR / "NotoSansTelugu-Regular.ttf"
        telugu_bold = _FONTS_DIR / "NotoSansTelugu-Bold.ttf"
        if not telugu_regular.is_file() or not telugu_bold.is_file():
            raise PdfExportError(
                "Bundled Telugu PDF fonts are missing.",
                retryable=False,
            )

        pdfmetrics.registerFont(TTFont("Vera", "Vera.ttf", shapable=True))
        pdfmetrics.registerFont(TTFont("VeraBd", "VeraBd.ttf", shapable=True))
        pdfmetrics.registerFont(TTFont("VeraIt", "VeraIt.ttf", shapable=True))
        registerFontFamily("Vera", normal="Vera", bold="VeraBd", italic="VeraIt")

        pdfmetrics.registerFont(TTFont("NotoSansTelugu", str(telugu_regular), shapable=True))
        pdfmetrics.registerFont(TTFont("NotoSansTeluguBd", str(telugu_bold), shapable=True))
        registerFontFamily("NotoSansTelugu", normal="NotoSansTelugu", bold="NotoSansTeluguBd")
        _FONTS_REGISTERED = True


def format_mixed_script_text(text: str, *, bold: bool = False) -> str:
    """Escape XML entities and tag Telugu runs so ReportLab shapes each script cleanly."""
    normalized = unicodedata.normalize("NFC", text).strip()
    if not normalized:
        return ""
    separated = _LEFT_SCRIPT_BOUNDARY_RE.sub(" ", normalized)
    separated = _RIGHT_SCRIPT_BOUNDARY_RE.sub(" ", separated)
    escaped = escape(separated)
    telugu_font = "NotoSansTeluguBd" if bold else "NotoSansTelugu"
    return _TELUGU_RUN_RE.sub(
        lambda match: f'<font name="{telugu_font}">{match.group(1)}</font>',
        escaped,
    )


def _format_duration(seconds: float | None) -> str | None:
    if seconds is None or seconds <= 0:
        return None
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}m {secs:02d}s"


def _safe_download_filename(title: str, lecture_id: str) -> str:
    slug = _FILENAME_SAFE_RE.sub("-", title).strip("-._")[:60]
    if not slug:
        slug = "lecture-notes"
    return f"{slug}-{lecture_id[:8]}.pdf"


class _NumberedCanvas(canvas.Canvas):
    def __init__(self, *args: object, header_title: str = "", **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, object]] = []
        self._header_title = header_title

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_chrome(total_pages)
            super().showPage()
        super().save()

    def _draw_chrome(self, total_pages: int) -> None:
        width, height = A4
        margin = 54
        self.saveState()
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)

        if self._pageNumber > 1 and self._header_title:
            self.setFont("Vera", 8.5)
            self.setFillColor(colors.HexColor("#64748B"))
            truncated = self._header_title[:75] + ("..." if len(self._header_title) > 75 else "")
            self.drawString(margin, height - 38, truncated)
            self.line(margin, height - 44, width - margin, height - 44)

        self.line(margin, 44, width - margin, 44)
        self.setFont("Vera", 8.5)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(margin, 30, "Code-Mixed Lecture Notes Generator (AI-assisted)")
        self.drawRightString(width - margin, 30, f"Page {self._pageNumber} of {total_pages}")
        self.restoreState()


def _build_styles() -> dict[str, ParagraphStyle]:
    base = dict(fontName="Vera", textColor=colors.HexColor("#1E293B"), shaping=True)
    return {
        "title": ParagraphStyle(
            "PdfTitle",
            fontName="VeraBd",
            fontSize=18,
            leading=24,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=6,
            shaping=True,
        ),
        "meta": ParagraphStyle(
            "PdfMeta",
            fontName="Vera",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#475569"),
            spaceAfter=4,
            shaping=True,
        ),
        "disclaimer": ParagraphStyle(
            "PdfDisclaimer",
            fontName="VeraIt",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#64748B"),
            spaceAfter=10,
            shaping=True,
        ),
        "h1": ParagraphStyle(
            "PdfHeading1",
            fontName="VeraBd",
            fontSize=13.5,
            leading=18,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=12,
            spaceAfter=6,
            shaping=True,
        ),
        "h2": ParagraphStyle(
            "PdfHeading2",
            fontName="VeraBd",
            fontSize=11.5,
            leading=16,
            textColor=colors.HexColor("#1E293B"),
            spaceBefore=8,
            spaceAfter=4,
            shaping=True,
        ),
        "body": ParagraphStyle(
            "PdfBody",
            **base,
            fontSize=10.5,
            leading=15.5,
            spaceAfter=5,
        ),
        "bullet": ParagraphStyle(
            "PdfBullet",
            **base,
            fontSize=10.2,
            leading=15,
            leftIndent=14,
            firstLineIndent=-10,
            spaceAfter=3,
        ),
        "excerpt": ParagraphStyle(
            "PdfExcerpt",
            fontName="VeraIt",
            fontSize=9.2,
            leading=13.5,
            textColor=colors.HexColor("#475569"),
            leftIndent=10,
            spaceAfter=6,
            shaping=True,
        ),
    }


def render_lecture_pdf(
    *,
    title: str,
    original_filename: str,
    duration_seconds: float | None,
    notes_content: dict[str, object],
    explanations: list[ConceptExplanation],
    revision_points: list[RevisionPoint],
) -> bytes:
    """Render an academic-style English-Telugu PDF from saved lecture material."""
    register_pdf_fonts()
    styles = _build_styles()
    buffer = io.BytesIO()
    margin = 0.75 * inch
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=60,
        bottomMargin=58,
        title=title,
    )

    story: list[object] = []
    story.append(Paragraph(format_mixed_script_text(title, bold=True), styles["title"]))

    meta_parts = [f"Source: {original_filename}"]
    duration_label = _format_duration(duration_seconds)
    if duration_label:
        meta_parts.append(f"Duration: {duration_label}")
    story.append(Paragraph(format_mixed_script_text("  |  ".join(meta_parts)), styles["meta"]))
    story.append(
        Paragraph(
            "Note: These study materials are AI-assisted from code-mixed English-Telugu audio. "
            "Verify critical definitions and formulas against course instruction.",
            styles["disclaimer"],
        )
    )
    story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#CBD5E1"), spaceAfter=10))

    # 1. Structured Notes
    story.append(Paragraph("Structured Study Notes", styles["h1"]))
    sections = notes_content.get("sections")
    if isinstance(sections, list):
        for idx, section in enumerate(sections, start=1):
            if not isinstance(section, dict):
                continue
            heading = str(section.get("heading") or f"Section {idx}")
            summary = str(section.get("summary") or "").strip()
            key_points = section.get("key_points")
            source_excerpt = str(section.get("source_excerpt") or "").strip()

            header_block: list[object] = [
                Paragraph(format_mixed_script_text(f"{idx}. {heading}", bold=True), styles["h2"])
            ]
            if summary:
                header_block.append(Paragraph(format_mixed_script_text(summary), styles["body"]))
            story.append(KeepTogether(header_block))

            if isinstance(key_points, list):
                for point in key_points:
                    point_text = str(point).strip()
                    if point_text:
                        story.append(
                            Paragraph(
                                f"&#8226; {format_mixed_script_text(point_text)}",
                                styles["bullet"],
                            )
                        )
            if source_excerpt:
                story.append(
                    Paragraph(
                        format_mixed_script_text(f'Lecture reference: "{source_excerpt}"'),
                        styles["excerpt"],
                    )
                )
            story.append(Spacer(1, 4))

    concepts = notes_content.get("concepts")
    if isinstance(concepts, list) and concepts:
        concept_names = [
            str(item.get("name")).strip()
            for item in concepts
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        if concept_names:
            story.append(
                KeepTogether(
                    [
                        Paragraph("Core Lecture Concepts", styles["h2"]),
                        Paragraph(
                            format_mixed_script_text(", ".join(concept_names)),
                            styles["body"],
                        ),
                    ]
                )
            )

    # 2. Telugu-Supported Concept Explanations
    if explanations:
        story.append(Spacer(1, 6))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0"), spaceAfter=4))
        story.append(Paragraph("Telugu-Supported Concept Explanations", styles["h1"]))
        for idx, item in enumerate(explanations, start=1):
            block: list[object] = [
                Paragraph(
                    format_mixed_script_text(f"{idx}. {item.concept}", bold=True),
                    styles["h2"],
                ),
                Paragraph(
                    format_mixed_script_text(item.explanation_telugu),
                    styles["body"],
                ),
            ]
            if item.source_excerpt and item.source_excerpt.strip():
                block.append(
                    Paragraph(
                        format_mixed_script_text(f'Supporting excerpt: "{item.source_excerpt}"'),
                        styles["excerpt"],
                    )
                )
            story.append(KeepTogether(block))

    # 3. Revision Points
    if revision_points:
        story.append(Spacer(1, 6))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0"), spaceAfter=4))
        story.append(Paragraph("Key Revision Points", styles["h1"]))
        for idx, point in enumerate(revision_points, start=1):
            point_block: list[object] = [
                Paragraph(
                    f"{idx}. {format_mixed_script_text(point.content)}",
                    styles["body"],
                )
            ]
            if point.source_excerpt and point.source_excerpt.strip():
                point_block.append(
                    Paragraph(
                        format_mixed_script_text(f'Reference: "{point.source_excerpt}"'),
                        styles["excerpt"],
                    )
                )
            story.append(KeepTogether(point_block))

    header_title = re.sub(r"[\u0C00-\u0C7F]+", "", title)
    header_title = re.sub(r"\(\s*\)", "", header_title)
    header_title = re.sub(r"\s{2,}", " ", header_title).strip(" -:") or original_filename
    doc.build(
        story,
        canvasmaker=lambda *args, **kwargs: _NumberedCanvas(
            *args, header_title=header_title, **kwargs
        ),
    )
    return buffer.getvalue()


class PdfExportService:
    def __init__(self, session_factory: sessionmaker[Session], storage: PdfStorage) -> None:
        self.session_factory = session_factory
        self.storage = storage

    def ensure_pdf(self, lecture_id: str) -> LecturePdfResult:
        with self.session_factory() as session:
            lecture = session.get(Lecture, lecture_id)
            if lecture is None:
                raise PdfLectureNotFoundError("Lecture was not found.")
            notes = session.scalar(select(Notes).where(Notes.lecture_id == lecture_id))
            if notes is None or not isinstance(notes.content, dict):
                raise PdfMaterialNotReadyError(
                    "Study notes must be generated before exporting a PDF."
                )
            explanations = list(
                session.scalars(
                    select(ConceptExplanation)
                    .where(ConceptExplanation.lecture_id == lecture_id)
                    .order_by(ConceptExplanation.position)
                ).all()
            )
            revision_points = list(
                session.scalars(
                    select(RevisionPoint)
                    .where(RevisionPoint.lecture_id == lecture_id)
                    .order_by(RevisionPoint.position)
                ).all()
            )
            existing = session.scalar(
                select(LecturePdf).where(LecturePdf.lecture_id == lecture_id)
            )

            title = str(notes.content.get("title") or lecture.title or lecture.original_filename)
            content_hash = self._compute_content_hash(
                title=title,
                original_filename=lecture.original_filename,
                duration_seconds=lecture.duration_seconds,
                notes_content=notes.content,
                explanations=explanations,
                revision_points=revision_points,
            )

            if existing is not None and existing.content_hash == content_hash:
                try:
                    existing_path = self.storage.path_for(existing.storage_key)
                    if existing_path.is_file():
                        return LecturePdfResult(
                            lecture_id=lecture_id,
                            storage_key=existing.storage_key,
                            filename=existing.filename,
                            file_size_bytes=existing.file_size_bytes,
                            content_hash=existing.content_hash,
                            path=existing_path,
                            reused=True,
                        )
                except StorageError:
                    pass

            old_storage_key = existing.storage_key if existing is not None else None
            original_filename = lecture.original_filename
            duration_seconds = lecture.duration_seconds
            notes_content = dict(notes.content)

        pdf_bytes = render_lecture_pdf(
            title=title,
            original_filename=original_filename,
            duration_seconds=duration_seconds,
            notes_content=notes_content,
            explanations=explanations,
            revision_points=revision_points,
        )
        try:
            new_storage_key = self.storage.store_bytes(pdf_bytes)
            new_path = self.storage.path_for(new_storage_key)
        except StorageError as exc:
            raise PdfExportError("Generated PDF could not be stored.", retryable=True) from exc

        download_filename = _safe_download_filename(title, lecture_id)
        try:
            with self.session_factory() as session:
                record = session.scalar(
                    select(LecturePdf).where(LecturePdf.lecture_id == lecture_id)
                )
                if record is None:
                    record = LecturePdf(
                        lecture_id=lecture_id,
                        storage_key=new_storage_key,
                        filename=download_filename,
                        file_size_bytes=len(pdf_bytes),
                        content_hash=content_hash,
                    )
                    session.add(record)
                else:
                    old_storage_key = record.storage_key
                    record.storage_key = new_storage_key
                    record.filename = download_filename
                    record.file_size_bytes = len(pdf_bytes)
                    record.content_hash = content_hash
                session.commit()
        except IntegrityError as exc:
            try:
                self.storage.delete(new_storage_key)
            except StorageError:
                logger.warning("Failed to clean up raced PDF %s", new_storage_key)
            with self.session_factory() as session:
                winner = session.scalar(
                    select(LecturePdf).where(LecturePdf.lecture_id == lecture_id)
                )
                if winner is not None and winner.content_hash == content_hash:
                    try:
                        winner_path = self.storage.path_for(winner.storage_key)
                        if winner_path.is_file():
                            return LecturePdfResult(
                                lecture_id=lecture_id,
                                storage_key=winner.storage_key,
                                filename=winner.filename,
                                file_size_bytes=winner.file_size_bytes,
                                content_hash=winner.content_hash,
                                path=winner_path,
                                reused=True,
                            )
                    except StorageError:
                        pass
            raise PdfExportError("Generated PDF metadata could not be saved.", retryable=True) from exc
        except SQLAlchemyError as exc:
            try:
                self.storage.delete(new_storage_key)
            except StorageError:
                logger.warning("Failed to clean up uncommitted PDF %s", new_storage_key)
            raise PdfExportError("Generated PDF metadata could not be saved.", retryable=True) from exc

        if old_storage_key and old_storage_key != new_storage_key:
            try:
                self.storage.delete(old_storage_key)
            except StorageError:
                logger.warning("Failed to remove superseded PDF %s", old_storage_key)

        return LecturePdfResult(
            lecture_id=lecture_id,
            storage_key=new_storage_key,
            filename=download_filename,
            file_size_bytes=len(pdf_bytes),
            content_hash=content_hash,
            path=new_path,
            reused=False,
        )

    @staticmethod
    def _compute_content_hash(
        *,
        title: str,
        original_filename: str,
        duration_seconds: float | None,
        notes_content: dict[str, object],
        explanations: list[ConceptExplanation],
        revision_points: list[RevisionPoint],
    ) -> str:
        payload = {
            "title": title,
            "original_filename": original_filename,
            "duration_seconds": duration_seconds,
            "notes": notes_content,
            "explanations": [
                {
                    "position": item.position,
                    "concept": item.concept,
                    "source_excerpt": item.source_excerpt,
                    "explanation_telugu": item.explanation_telugu,
                }
                for item in explanations
            ],
            "revision_points": [
                {
                    "position": item.position,
                    "content": item.content,
                    "source_excerpt": item.source_excerpt,
                }
                for item in revision_points
            ],
        }
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
