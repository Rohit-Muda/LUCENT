from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProcessingStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    current_stage: str | None
    last_successful_stage: str | None
    retry_count: int
    attempts_by_stage: dict[str, int]
    manual_retry_count: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    can_retry: bool
