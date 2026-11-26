import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.errors import ApiError
from backend.app.models import Transcript
from backend.app.schemas.transcript import TranscriptResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lectures", tags=["transcripts"])


@router.get("/{lecture_id}/transcript", response_model=TranscriptResponse)
def get_transcript(
    lecture_id: str,
    session: Session = Depends(get_db),
) -> TranscriptResponse:
    try:
        transcript = session.scalar(
            select(Transcript).where(Transcript.lecture_id == lecture_id)
        )
    except SQLAlchemyError as exc:
        logger.exception("Transcript could not be read")
        raise ApiError(503, "database_unavailable", "Transcript is unavailable.") from exc
    if transcript is None:
        raise ApiError(404, "transcript_not_found", "Transcript was not found.")
    return TranscriptResponse.model_validate(transcript)
