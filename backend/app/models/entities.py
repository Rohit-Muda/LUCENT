from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


def _new_id() -> str:
    return str(uuid4())


class Lecture(TimestampMixin, Base):
    __tablename__ = "lectures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    title: Mapped[str | None] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    media_type: Mapped[str] = mapped_column(String(127), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_seconds: Mapped[float | None]
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded", index=True)

    transcript: Mapped["Transcript | None"] = relationship(
        back_populates="lecture", cascade="all, delete-orphan", uselist=False
    )
    notes: Mapped["Notes | None"] = relationship(
        back_populates="lecture", cascade="all, delete-orphan", uselist=False
    )
    revision_points: Mapped[list["RevisionPoint"]] = relationship(
        back_populates="lecture", cascade="all, delete-orphan"
    )
    quiz_questions: Mapped[list["QuizQuestion"]] = relationship(
        back_populates="lecture", cascade="all, delete-orphan"
    )
    processing_job: Mapped["ProcessingJob | None"] = relationship(
        back_populates="lecture", cascade="all, delete-orphan", uselist=False
    )
    pdf: Mapped["LecturePdf | None"] = relationship(
        back_populates="lecture", cascade="all, delete-orphan", uselist=False
    )


class Transcript(TimestampMixin, Base):
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    lecture_id: Mapped[str] = mapped_column(
        ForeignKey("lectures.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_text: Mapped[str] = mapped_column(Text, nullable=False)
    segments: Mapped[list[dict[str, object]] | None] = mapped_column(JSON)
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(128))
    detected_language: Mapped[str | None] = mapped_column(String(32))
    transcribed_duration_seconds: Mapped[float | None]

    lecture: Mapped[Lecture] = relationship(back_populates="transcript")


class Notes(TimestampMixin, Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    lecture_id: Mapped[str] = mapped_column(
        ForeignKey("lectures.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    content: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)

    lecture: Mapped[Lecture] = relationship(back_populates="notes")


class ConceptExplanation(TimestampMixin, Base):
    __tablename__ = "concept_explanations"
    __table_args__ = (
        UniqueConstraint("lecture_id", "position", name="uq_concept_explanation_lecture_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    lecture_id: Mapped[str] = mapped_column(
        ForeignKey("lectures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    concept: Mapped[str] = mapped_column(String(255), nullable=False)
    source_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_telugu: Mapped[str] = mapped_column(Text, nullable=False)


class RevisionPoint(TimestampMixin, Base):
    __tablename__ = "revision_points"
    __table_args__ = (
        UniqueConstraint("lecture_id", "position", name="uq_revision_point_lecture_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    lecture_id: Mapped[str] = mapped_column(
        ForeignKey("lectures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_excerpt: Mapped[str | None] = mapped_column(Text)

    lecture: Mapped[Lecture] = relationship(back_populates="revision_points")


class QuizQuestion(TimestampMixin, Base):
    __tablename__ = "quiz_questions"
    __table_args__ = (
        UniqueConstraint("lecture_id", "position", name="uq_quiz_question_lecture_position"),
        CheckConstraint(
            "correct_option_position >= 0 AND correct_option_position < 4",
            name="ck_quiz_question_correct_option_position",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    lecture_id: Mapped[str] = mapped_column(
        ForeignKey("lectures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    correct_option_position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    source_excerpt: Mapped[str | None] = mapped_column(Text)

    lecture: Mapped[Lecture] = relationship(back_populates="quiz_questions")
    options: Mapped[list["QuizOption"]] = relationship(
        back_populates="question", cascade="all, delete-orphan", order_by="QuizOption.position"
    )


class QuizOption(TimestampMixin, Base):
    __tablename__ = "quiz_options"
    __table_args__ = (
        UniqueConstraint("question_id", "position", name="uq_quiz_option_question_position"),
        Index("ix_quiz_options_question_id", "question_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    question_id: Mapped[str] = mapped_column(
        ForeignKey("quiz_questions.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    question: Mapped[QuizQuestion] = relationship(back_populates="options")


class ProcessingJob(TimestampMixin, Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        Index("ix_processing_jobs_status_lease_expiry", "status", "lease_expires_at"),
        Index("ix_processing_jobs_status_available_at", "status", "available_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    lecture_id: Mapped[str] = mapped_column(
        ForeignKey("lectures.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    current_stage: Mapped[str | None] = mapped_column(String(64))
    last_successful_stage: Mapped[str | None] = mapped_column(String(64))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts_by_stage: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
    manual_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)

    lecture: Mapped[Lecture] = relationship(back_populates="processing_job")


class GenerationChunk(TimestampMixin, Base):
    __tablename__ = "generation_chunks"
    __table_args__ = (
        UniqueConstraint(
            "lecture_id",
            "transcript_hash",
            "output_type",
            "chunk_index",
            name="uq_generation_chunk_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    lecture_id: Mapped[str] = mapped_column(
        ForeignKey("lectures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transcript_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_type: Mapped[str] = mapped_column(String(32), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class LecturePdf(TimestampMixin, Base):
    __tablename__ = "lecture_pdfs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    lecture_id: Mapped[str] = mapped_column(
        ForeignKey("lectures.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    lecture: Mapped[Lecture] = relationship(back_populates="pdf")
