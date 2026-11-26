import asyncio
import hashlib
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import main
from backend.app.config import Settings
from backend.app.database import get_db
from backend.app.models import (
    Base,
    GenerationChunk,
    Lecture,
    Notes,
    ProcessingJob,
    QuizOption,
    QuizQuestion,
    Transcript,
)
from backend.app.routes.processing import get_processing_job_manager
from backend.app.services.processing_jobs import ProcessingJobManager


class ApiHarness:
    def __init__(
        self,
        app: FastAPI,
        engine: Engine,
        factory: sessionmaker[Session],
        lecture_id: str,
    ) -> None:
        self.app = app
        self.engine = engine
        self.factory = factory
        self.lecture_id = lecture_id


@pytest.fixture
def api_harness() -> Iterator[ApiHarness]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        lecture = Lecture(
            original_filename="lesson.wav",
            storage_key="lesson.wav",
            media_type="audio/wav",
            file_size_bytes=100,
            status="completed",
        )
        session.add(lecture)
        session.flush()
        session.add(
            ProcessingJob(
                lecture_id=lecture.id,
                status="completed",
                current_stage=None,
                last_successful_stage="generate_quiz",
                retry_count=0,
                attempts_by_stage={},
                manual_retry_count=0,
            )
        )
        session.add(
            Transcript(
                lecture_id=lecture.id,
                original_text="Source lecture text.",
                cleaned_text="Source lecture text.",
            )
        )
        session.add(Notes(lecture_id=lecture.id, content={"title": "Saved notes"}))
        for question_index in range(5):
            question = QuizQuestion(
                lecture_id=lecture.id,
                position=question_index,
                prompt=f"Question {question_index}",
                correct_option_position=2,
                explanation="Source-supported answer.",
                source_excerpt="Source lecture text.",
            )
            session.add(question)
            session.flush()
            session.add_all(
                QuizOption(
                    question_id=question.id,
                    position=option_index,
                    content=f"Option {option_index}",
                )
                for option_index in range(4)
            )
        session.add_all(
            [
                GenerationChunk(
                    lecture_id=lecture.id,
                    transcript_hash=hashlib.sha256(
                        b"Source lecture text."
                    ).hexdigest(),
                    output_type="notes_chunk",
                    chunk_index=0,
                    content={"title": "Old note chunk"},
                ),
                GenerationChunk(
                    lecture_id=lecture.id,
                    transcript_hash=hashlib.sha256(
                        b"Source lecture text."
                    ).hexdigest(),
                    output_type="notes_final",
                    chunk_index=0,
                    content={"title": "Old note checkpoint"},
                ),
                GenerationChunk(
                    lecture_id=lecture.id,
                    transcript_hash=hashlib.sha256(
                        b"Source lecture text."
                    ).hexdigest(),
                    output_type="explanations_final",
                    chunk_index=0,
                    content={"explanations": []},
                ),
                GenerationChunk(
                    lecture_id=lecture.id,
                    transcript_hash=hashlib.sha256(
                        b"Source lecture text."
                    ).hexdigest(),
                    output_type="revision_points_final",
                    chunk_index=0,
                    content={"points": []},
                ),
                GenerationChunk(
                    lecture_id=lecture.id,
                    transcript_hash=hashlib.sha256(
                        b"Source lecture text."
                    ).hexdigest(),
                    output_type="quiz_final",
                    chunk_index=0,
                    content={"questions": []},
                ),
            ]
        )
        session.commit()
        lecture_id = lecture.id

    app = main.create_app()
    settings = Settings(_env_file=None)

    def override_database() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    manager = ProcessingJobManager(
        factory,
        lease_seconds=60,
        max_stage_attempts=3,
        max_manual_retries=2,
        retry_backoff_seconds=1,
    )
    app.dependency_overrides[get_db] = override_database
    app.dependency_overrides[main.get_settings] = lambda: settings
    app.dependency_overrides[get_processing_job_manager] = lambda: manager
    yield ApiHarness(app, engine, factory, lecture_id)
    app.dependency_overrides.clear()
    engine.dispose()


def request(
    app: FastAPI,
    method: str,
    url: str,
    *,
    json: dict[str, object] | None = None,
) -> Response:
    async def send() -> Response:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.request(method, url, json=json)

    return asyncio.run(send())


def test_quiz_answers_are_hidden_until_submission(api_harness: ApiHarness) -> None:
    quiz_response = request(
        api_harness.app,
        "GET",
        f"/lectures/{api_harness.lecture_id}/quiz",
    )
    quiz = quiz_response.json()

    assert quiz_response.status_code == 200
    assert len(quiz["questions"]) == 5
    assert len(quiz["questions"][0]["options"]) == 4
    assert "correct_option_position" not in quiz_response.text
    assert "explanation" not in quiz_response.text

    submission = request(
        api_harness.app,
        "POST",
        f"/lectures/{api_harness.lecture_id}/quiz/submit",
        json={
            "answers": [
                {
                    "question_id": question["id"],
                    "selected_option_position": 2,
                }
                for question in quiz["questions"]
            ]
        },
    )

    assert submission.status_code == 200
    assert submission.json()["score"] == 5
    assert submission.json()["total_questions"] == 5
    assert submission.json()["answers"][0]["correct_option_position"] == 2
    assert submission.json()["answers"][0]["is_correct"] is True
    assert submission.json()["answers"][0]["explanation"] == "Source-supported answer."


def test_quiz_submission_requires_one_answer_for_every_question(
    api_harness: ApiHarness,
) -> None:
    response = request(
        api_harness.app,
        "POST",
        f"/lectures/{api_harness.lecture_id}/quiz/submit",
        json={"answers": []},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "quiz_answers_incomplete"


@pytest.mark.parametrize(
    ("feature", "stage", "expected_remaining"),
    [
        (
            "notes",
            "regenerate_notes",
            {"explanations_final", "revision_points_final", "quiz_final"},
        ),
        (
            "explanations",
            "regenerate_explanations",
            {"notes_chunk", "notes_final", "revision_points_final", "quiz_final"},
        ),
        (
            "revision-points",
            "regenerate_revision_points",
            {"notes_chunk", "notes_final", "explanations_final", "quiz_final"},
        ),
        (
            "quiz",
            "regenerate_quiz",
            {"notes_chunk", "notes_final", "explanations_final", "revision_points_final"},
        ),
    ],
)
def test_regeneration_is_scoped_to_the_requested_feature(
    api_harness: ApiHarness,
    feature: str,
    stage: str,
    expected_remaining: set[str],
) -> None:
    response = request(
        api_harness.app,
        "POST",
        f"/lectures/{api_harness.lecture_id}/regenerate/{feature}",
    )

    assert response.status_code == 200
    assert response.json()["current_stage"] == stage
    with api_harness.factory() as session:
        job = session.scalar(
            select(ProcessingJob).where(
                ProcessingJob.lecture_id == api_harness.lecture_id
            )
        )
        notes = session.scalar(
            select(Notes).where(Notes.lecture_id == api_harness.lecture_id)
        )
        remaining_chunks = session.scalars(
            select(GenerationChunk).where(
                GenerationChunk.lecture_id == api_harness.lecture_id
            )
        ).all()

    assert job.status == "queued"
    assert notes.content == {"title": "Saved notes"}
    assert {chunk.output_type for chunk in remaining_chunks} == expected_remaining
