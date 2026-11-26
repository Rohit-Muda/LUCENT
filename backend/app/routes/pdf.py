import logging

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError

from backend.app.config import Settings, get_settings
from backend.app.database import get_session_factory
from backend.app.errors import ApiError
from backend.app.services.pdf_export import (
    PdfExportError,
    PdfExportService,
    PdfLectureNotFoundError,
    PdfMaterialNotReadyError,
)
from backend.app.services.pdf_storage import LocalPdfStorage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lectures", tags=["pdf"])


def get_pdf_export_service(settings: Settings = Depends(get_settings)) -> PdfExportService:
    return PdfExportService(
        get_session_factory(),
        LocalPdfStorage(settings.pdf_dir),
    )


@router.get("/{lecture_id}/pdf")
def download_lecture_pdf(
    lecture_id: str,
    service: PdfExportService = Depends(get_pdf_export_service),
) -> FileResponse:
    try:
        result = service.ensure_pdf(lecture_id)
    except PdfLectureNotFoundError as exc:
        raise ApiError(404, "lecture_not_found", "Lecture was not found.") from exc
    except PdfMaterialNotReadyError as exc:
        raise ApiError(409, "pdf_materials_not_ready", exc.safe_message) from exc
    except PdfExportError as exc:
        logger.exception("PDF export failed (lecture_id=%s)", lecture_id)
        raise ApiError(503, "pdf_export_unavailable", exc.safe_message) from exc
    except SQLAlchemyError as exc:
        logger.exception("PDF metadata lookup failed (lecture_id=%s)", lecture_id)
        raise ApiError(503, "database_unavailable", "PDF export is unavailable.") from exc

    return FileResponse(
        path=result.path,
        media_type="application/pdf",
        filename=result.filename,
    )
