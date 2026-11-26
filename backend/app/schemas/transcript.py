from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TranscriptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lecture_id: str
    original_text: str
    cleaned_text: str
    segments: list[dict[str, object]] | None
    provider: str | None
    model: str | None
    detected_language: str | None
    transcribed_duration_seconds: float | None
    created_at: datetime
