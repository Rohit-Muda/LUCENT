from collections.abc import Iterator
import json

import pytest
from sqlalchemy import Engine, create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.models import (
    Base,
    ConceptExplanation,
    GenerationChunk,
    Lecture,
    Notes,
    QuizQuestion,
    RevisionPoint,
    Transcript,
)
from backend.app.providers.gemini_generator import GeminiProviderError
from backend.app.services.study_materials import (
    ExplanationsContent,
    LectureConcept,
    NotesContent,
    NoteSection,
    QuizContent,
    QuizQuestionItem,
    RevisionPointItem,
    RevisionPointsContent,
    StudyMaterialError,
    StudyMaterialService,
    split_transcript,
)

TRANSCRIPT = "The cell is the basic unit of life. DNA stores genetic information."


@pytest.fixture
def material_store() -> Iterator[tuple[Engine, sessionmaker[Session], str]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        lecture = Lecture(
            original_filename="biology.wav",
            storage_key="biology.wav",
            media_type="audio/wav",
            file_size_bytes=100,
            status="completed",
        )
        session.add(lecture)
        session.flush()
        session.add(
            Transcript(
                lecture_id=lecture.id,
                original_text=TRANSCRIPT,
                cleaned_text=TRANSCRIPT,
            )
        )
        session.commit()
        lecture_id = lecture.id
    yield engine, factory, lecture_id
    engine.dispose()


class FakeGenerator:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_consolidation = False
        self.chunk_notes: list[NotesContent] = []
        self.notes_override: NotesContent | None = None

    def generate_json(self, prompt: str, schema: type) -> str:
        self.calls.append(schema.__name__)
        if schema is NotesContent:
            if "Transcript:" in prompt:
                transcript = json.loads(prompt.split("Transcript:", 1)[1].strip())
                if self.notes_override is not None:
                    return self.notes_override.model_dump_json()
                excerpt = transcript.split(".")[0] + "."
                if transcript == TRANSCRIPT:
                    return NotesContent(
                        title="Biology",
                        sections=[
                            NoteSection(
                                heading="Core idea",
                                summary="A lecture-supported summary.",
                                key_points=["A source-grounded point."],
                                source_excerpt="The cell is the basic unit of life.",
                            )
                        ],
                        concepts=[
                            LectureConcept(
                                name="cell",
                                source_excerpt="The cell is the basic unit of life.",
                            ),
                            LectureConcept(
                                name="DNA",
                                source_excerpt="DNA stores genetic information.",
                            ),
                        ],
                    ).model_dump_json()
                name = excerpt.split()[0]
                result = _notes_output(name, excerpt)
                self.chunk_notes.append(result)
                return result.model_dump_json()
            if self.fail_consolidation:
                self.fail_consolidation = False
                raise GeminiProviderError(
                    "provider_unavailable",
                    "Gemini is temporarily unavailable.",
                    retryable=True,
                )
            concepts = []
            sections = []
            for notes in self.chunk_notes:
                concepts.extend(notes.concepts)
                sections.extend(notes.sections)
            return NotesContent(
                title="Lecture notes",
                sections=sections,
                concepts=concepts,
            ).model_dump_json()
        if schema is ExplanationsContent:
            return ExplanationsContent(
                explanations=[
                    {
                        "concept": "cell",
                        "source_excerpt": "The cell is the basic unit of life.",
                        "explanation_telugu": "కణం జీవి యొక్క ప్రాథమిక ప్రమాణం.",
                    },
                    {
                        "concept": "DNA",
                        "source_excerpt": "DNA stores genetic information.",
                        "explanation_telugu": "DNA జన్యు సమాచారాన్ని నిల్వ చేస్తుంది.",
                    },
                ]
            ).model_dump_json()
        if schema is RevisionPointsContent:
            return RevisionPointsContent(
                points=[
                    RevisionPointItem(
                        content="The cell is the basic unit of life.",
                        source_excerpt="The cell is the basic unit of life.",
                    ),
                    RevisionPointItem(
                        content="DNA stores genetic information.",
                        source_excerpt="DNA stores genetic information.",
                    ),
                ]
            ).model_dump_json()
        if schema is QuizContent:
            return QuizContent(
                questions=[
                    QuizQuestionItem(
                        question=f"Question {index}: What does the lecture state?",
                        options=[
                            f"Correct {index}",
                            f"Incorrect A {index}",
                            f"Incorrect B {index}",
                            f"Incorrect C {index}",
                        ],
                        correct_option_index=0,
                        explanation="The cited statement supports the selected answer.",
                        source_excerpt=(
                            "The cell is the basic unit of life."
                            if index % 2 == 0
                            else "DNA stores genetic information."
                        ),
                    )
                    for index in range(5)
                ]
            ).model_dump_json()
        raise AssertionError(f"Unexpected schema requested: {schema.__name__}")


def _notes_output(concept: str, excerpt: str) -> NotesContent:
    return NotesContent(
        title="Biology",
        sections=[
            NoteSection(
                heading="Core idea",
                summary="A lecture-supported summary.",
                key_points=["A source-grounded point."],
                source_excerpt=excerpt,
            )
        ],
        concepts=[LectureConcept(name=concept, source_excerpt=excerpt)],
    )


def test_study_materials_are_saved_and_only_the_requested_output_is_replaced(
    material_store: tuple[Engine, sessionmaker[Session], str],
) -> None:
    _, factory, lecture_id = material_store
    generator = FakeGenerator()
    service = StudyMaterialService(factory, generator)

    notes = service.generate_notes(lecture_id, TRANSCRIPT)
    service.generate_explanations(lecture_id, TRANSCRIPT)
    service.generate_revision_points(lecture_id, TRANSCRIPT)
    service.generate_quiz(lecture_id, TRANSCRIPT)
    successful_provider_calls = list(generator.calls)
    service.generate_notes(lecture_id, TRANSCRIPT)
    service.generate_explanations(lecture_id, TRANSCRIPT)
    service.generate_revision_points(lecture_id, TRANSCRIPT)
    service.generate_quiz(lecture_id, TRANSCRIPT)
    assert generator.calls == successful_provider_calls

    with factory() as session:
        old_explanations = session.scalars(
            select(ConceptExplanation).where(ConceptExplanation.lecture_id == lecture_id)
        ).all()
        old_revision = session.scalars(
            select(RevisionPoint).where(RevisionPoint.lecture_id == lecture_id)
        ).all()
        old_quiz = session.scalars(
            select(QuizQuestion).where(QuizQuestion.lecture_id == lecture_id)
        ).all()
        assert len(old_explanations) == 2
        assert len(old_revision) == 2
        assert len(old_quiz) == 5

    revised_notes = NotesContent(
        title="Updated biology",
        sections=notes.sections,
        concepts=notes.concepts,
    )
    generator.notes_override = revised_notes
    with factory() as session:
        session.execute(
            delete(GenerationChunk).where(
                GenerationChunk.lecture_id == lecture_id,
                GenerationChunk.output_type.in_(["notes_chunk", "notes_final"]),
            )
        )
        session.commit()
    service.generate_notes(lecture_id, TRANSCRIPT)

    with factory() as session:
        saved_notes = session.scalar(select(Notes).where(Notes.lecture_id == lecture_id))
        explanations = session.scalars(
            select(ConceptExplanation).where(ConceptExplanation.lecture_id == lecture_id)
        ).all()
        revision_points = session.scalars(
            select(RevisionPoint).where(RevisionPoint.lecture_id == lecture_id)
        ).all()
        quiz_questions = session.scalars(
            select(QuizQuestion).where(QuizQuestion.lecture_id == lecture_id)
        ).all()
        assert saved_notes.content["title"] == "Updated biology"
        assert [item.concept for item in explanations] == ["cell", "DNA"]
        assert len(revision_points) == 2
        assert len(quiz_questions) == 5


def test_cached_note_chunks_are_reused_after_consolidation_failure(
    material_store: tuple[Engine, sessionmaker[Session], str],
) -> None:
    _, factory, lecture_id = material_store
    transcript = " ".join(
        f"Concept{index} explains a lecture detail." for index in range(5000)
    )
    generator = FakeGenerator()
    generator.fail_consolidation = True
    service = StudyMaterialService(factory, generator)

    with pytest.raises(GeminiProviderError):
        service.generate_notes(lecture_id, transcript)
    calls_after_failure = len(generator.calls)
    with factory() as session:
        cached_chunk_count = len(
            session.scalars(
            select(GenerationChunk).where(
                GenerationChunk.lecture_id == lecture_id,
                GenerationChunk.output_type == "notes_chunk",
            )
            ).all()
        )

    service.generate_notes(lecture_id, transcript)

    assert cached_chunk_count > 1
    assert len(generator.calls) == calls_after_failure + 1
    assert generator.calls.count("NotesContent") == cached_chunk_count + 2


def test_split_transcript_preserves_order_and_bounds_chunk_size() -> None:
    transcript = " ".join(f"తెలుగు Topic{index}." for index in range(20))

    chunks = split_transcript(transcript, max_chars=32)

    assert len(chunks) > 1
    assert all(len(chunk) <= 32 for chunk in chunks)
    assert " ".join(chunks) == transcript


def test_invalid_or_non_grounded_materials_are_rejected_without_persistence(
    material_store: tuple[Engine, sessionmaker[Session], str],
) -> None:
    _, factory, lecture_id = material_store

    class InvalidGenerator:
        def generate_json(self, prompt: str, schema: type) -> str:
            del prompt, schema
            return NotesContent(
                title="Unsupported",
                sections=[
                    NoteSection(
                        heading="Unsupported",
                        summary="Unsupported statement.",
                        key_points=["Unsupported point."],
                        source_excerpt="This wording is not in the lecture.",
                    )
                ],
                concepts=[
                    LectureConcept(
                        name="Unsupported",
                        source_excerpt="This wording is not in the lecture.",
                    )
                ],
            ).model_dump_json()

    service = StudyMaterialService(factory, InvalidGenerator())

    with pytest.raises(StudyMaterialError) as raised:
        service.generate_notes(lecture_id, TRANSCRIPT)

    assert not raised.value.retryable
    with factory() as session:
        assert session.scalar(select(Notes).where(Notes.lecture_id == lecture_id)) is None
