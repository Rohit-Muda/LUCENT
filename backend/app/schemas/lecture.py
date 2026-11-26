from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LectureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    original_filename: str
    media_type: str
    file_size_bytes: int
    duration_seconds: float | None
    status: str
    created_at: datetime


class LectureListResponse(BaseModel):
    items: list[LectureResponse]
    total: int
    limit: int
    offset: int
