import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from backend.app.database import get_db
from backend.app.errors import ApiError
from backend.app.models import ConceptExplanation, Notes, QuizQuestion, RevisionPoint
from backend.app.schemas.study_materials import (
    ConceptExplanationResponse,
    NotesResponse,
    QuizAnswerResult,
    QuizQuestionResponse,
    QuizResponse,
    QuizSubmissionRequest,
    QuizSubmissionResponse,
    RevisionPointResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lectures", tags=["study materials"])


@router.get("/{lecture_id}/notes", response_model=NotesResponse)
def get_notes(
    lecture_id: str,
    session: Session = Depends(get_db),
) -> NotesResponse:
    try:
        notes = session.scalar(select(Notes).where(Notes.lecture_id == lecture_id))
    except SQLAlchemyError as exc:
        logger.exception("Lecture notes could not be read")
        raise ApiError(503, "database_unavailable", "Lecture notes are unavailable.") from exc
    if notes is None:
        raise ApiError(404, "notes_not_found", "Lecture notes were not found.")
    return NotesResponse(
        lecture_id=notes.lecture_id,
        content=notes.content,
        updated_at=notes.updated_at,
    )


@router.get(
    "/{lecture_id}/explanations",
    response_model=list[ConceptExplanationResponse],
)
def get_explanations(
    lecture_id: str,
    session: Session = Depends(get_db),
) -> list[ConceptExplanationResponse]:
    try:
        explanations = session.scalars(
            select(ConceptExplanation)
            .where(ConceptExplanation.lecture_id == lecture_id)
            .order_by(ConceptExplanation.position)
        ).all()
    except SQLAlchemyError as exc:
        logger.exception("Concept explanations could not be read")
        raise ApiError(
            503,
            "database_unavailable",
            "Concept explanations are unavailable.",
        ) from exc
    if not explanations:
        raise ApiError(404, "explanations_not_found", "Concept explanations were not found.")
    return [ConceptExplanationResponse.model_validate(item) for item in explanations]


@router.get(
    "/{lecture_id}/revision-points",
    response_model=list[RevisionPointResponse],
)
def get_revision_points(
    lecture_id: str,
    session: Session = Depends(get_db),
) -> list[RevisionPointResponse]:
    try:
        points = session.scalars(
            select(RevisionPoint)
            .where(RevisionPoint.lecture_id == lecture_id)
            .order_by(RevisionPoint.position)
        ).all()
    except SQLAlchemyError as exc:
        logger.exception("Revision points could not be read")
        raise ApiError(503, "database_unavailable", "Revision points are unavailable.") from exc
    if not points:
        raise ApiError(404, "revision_points_not_found", "Revision points were not found.")
    return [RevisionPointResponse.model_validate(item) for item in points]


@router.get("/{lecture_id}/quiz", response_model=QuizResponse)
def get_quiz(
    lecture_id: str,
    session: Session = Depends(get_db),
) -> QuizResponse:
    questions = _load_quiz_questions(session, lecture_id)
    if not questions:
        raise ApiError(404, "quiz_not_found", "The lecture quiz was not found.")
    if any(len(question.options) != 4 for question in questions):
        logger.error("Saved quiz has an invalid option count (lecture_id=%s)", lecture_id)
        raise ApiError(503, "quiz_unavailable", "The saved quiz is incomplete.")
    return QuizResponse(
        lecture_id=lecture_id,
        questions=[QuizQuestionResponse.model_validate(question) for question in questions],
    )


@router.post(
    "/{lecture_id}/quiz/submit",
    response_model=QuizSubmissionResponse,
)
def submit_quiz(
    lecture_id: str,
    request: QuizSubmissionRequest,
    session: Session = Depends(get_db),
) -> QuizSubmissionResponse:
    questions = _load_quiz_questions(session, lecture_id)
    if not questions:
        raise ApiError(404, "quiz_not_found", "The lecture quiz was not found.")

    answer_by_id = {answer.question_id: answer for answer in request.answers}
    expected_ids = {question.id for question in questions}
    if set(answer_by_id) != expected_ids:
        raise ApiError(
            422,
            "quiz_answers_incomplete",
            "Submit exactly one answer for every quiz question.",
        )

    results: list[QuizAnswerResult] = []
    for question in questions:
        answer = answer_by_id[question.id]
        if (
            len(question.options) != 4
            or answer.selected_option_position >= len(question.options)
            or not 0 <= question.correct_option_position < 4
        ):
            logger.error("Saved quiz question is invalid (question_id=%s)", question.id)
            raise ApiError(503, "quiz_unavailable", "The saved quiz is incomplete.")
        results.append(
            QuizAnswerResult(
                question_id=question.id,
                selected_option_position=answer.selected_option_position,
                correct_option_position=question.correct_option_position,
                is_correct=answer.selected_option_position == question.correct_option_position,
                explanation=question.explanation,
            )
        )
    return QuizSubmissionResponse(
        lecture_id=lecture_id,
        score=sum(answer.is_correct for answer in results),
        total_questions=len(results),
        answers=results,
    )


def _load_quiz_questions(session: Session, lecture_id: str) -> list[QuizQuestion]:
    try:
        return list(
            session.scalars(
                select(QuizQuestion)
                .where(QuizQuestion.lecture_id == lecture_id)
                .options(selectinload(QuizQuestion.options))
                .order_by(QuizQuestion.position)
            ).all()
        )
    except SQLAlchemyError as exc:
        logger.exception("Lecture quiz could not be read")
        raise ApiError(503, "database_unavailable", "Lecture quiz is unavailable.") from exc
