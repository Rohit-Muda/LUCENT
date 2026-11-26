from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NotesResponse(BaseModel):
    lecture_id: str
    content: dict[str, object]
    updated_at: datetime


class ConceptExplanationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    concept: str
    source_excerpt: str
    explanation_telugu: str
    updated_at: datetime


class RevisionPointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    content: str
    source_excerpt: str | None
    updated_at: datetime


class QuizOptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    content: str


class QuizQuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    prompt: str
    options: list[QuizOptionResponse]


class QuizResponse(BaseModel):
    lecture_id: str
    questions: list[QuizQuestionResponse]


class QuizAnswerRequest(BaseModel):
    question_id: str
    selected_option_position: int = Field(ge=0, le=3)


class QuizSubmissionRequest(BaseModel):
    answers: list[QuizAnswerRequest]

    @model_validator(mode="after")
    def require_unique_question_answers(self) -> "QuizSubmissionRequest":
        ids = [answer.question_id for answer in self.answers]
        if len(ids) != len(set(ids)):
            raise ValueError("A question can only be answered once.")
        return self


class QuizAnswerResult(BaseModel):
    question_id: str
    selected_option_position: int
    correct_option_position: int
    is_correct: bool
    explanation: str


class QuizSubmissionResponse(BaseModel):
    lecture_id: str
    score: int
    total_questions: int
    answers: list[QuizAnswerResult]
