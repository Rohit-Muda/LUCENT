import { useEffect, useState } from 'react'
import { useOutletContext, useParams } from 'react-router-dom'
import { submitQuiz } from '../api/lectures'
import EmptyState from '../components/EmptyState'
import ErrorMessage from '../components/ErrorMessage'
import LoadingSpinner from '../components/LoadingSpinner'
import { getApiErrorMessage } from '../utils/formatters'

export default function QuizPage() {
  const { lectureId } = useParams()
  const {
    resources,
    loadResource,
    processing,
    regeneratingFeature,
    handleRegenerate,
  } = useOutletContext()
  const resource = resources.quiz

  const [selectedAnswers, setSelectedAnswers] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [submission, setSubmission] = useState(null)

  useEffect(() => {
    if (resource.status === 'idle') {
      loadResource('quiz')
    }
  }, [resource.status, loadResource])

  if (resource.status === 'loading' || resource.status === 'idle') {
    return <LoadingSpinner message="Loading MCQ quiz..." />
  }

  if (resource.status === 'unavailable') {
    return (
      <EmptyState
        title="Quiz not yet available"
        message={resource.error}
      />
    )
  }

  if (resource.status === 'error') {
    return (
      <ErrorMessage
        message={resource.error}
        onRetry={() => loadResource('quiz', { force: true })}
      />
    )
  }

  const questions = resource.data?.questions || []
  const answeredCount = questions.filter((q) => selectedAnswers[q.id] !== undefined).length
  const allAnswered = questions.length > 0 && answeredCount === questions.length
  const isBusy =
    Boolean(regeneratingFeature) ||
    ['queued', 'running', 'waiting'].includes(processing?.status)

  const resultsByQuestionId = new Map(
    (submission?.answers || []).map((answer) => [answer.question_id, answer]),
  )

  function handleOptionSelect(questionId, position) {
    if (submission) return
    setSubmitError('')
    setSelectedAnswers((prev) => ({
      ...prev,
      [questionId]: position,
    }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!allAnswered || submitting) return

    setSubmitting(true)
    setSubmitError('')
    try {
      const payload = questions.map((question) => ({
        question_id: question.id,
        selected_option_position: selectedAnswers[question.id],
      }))
      const result = await submitQuiz(lectureId, payload)
      setSubmission(result)
    } catch (err) {
      setSubmitError(
        getApiErrorMessage(err, 'Quiz answers could not be submitted. Please try again.'),
      )
    } finally {
      setSubmitting(false)
    }
  }

  function handleRetake() {
    setSelectedAnswers({})
    setSubmission(null)
    setSubmitError('')
  }

  return (
    <section className="quiz-page" aria-label="Multiple-choice quiz">
      <div className="panel-header">
        <div>
          <h2>MCQ Practice Quiz</h2>
          <p className="muted-meta">
            Answer all {questions.length} questions, then submit to check correctness and explanations.
          </p>
        </div>
        {processing?.status === 'completed' && (
          <button
            className="button button-small button-secondary"
            type="button"
            disabled={isBusy}
            onClick={() => {
              handleRetake()
              handleRegenerate('quiz')
            }}
          >
            {regeneratingFeature === 'quiz' ? 'Queuing...' : 'Regenerate quiz'}
          </button>
        )}
      </div>

      {submission && (
        <div className="notice notice-success quiz-score-banner" role="status">
          <strong>
            Score: {submission.score} / {submission.total_questions}
          </strong>
          <span>
            {' '}
            ({Math.round((submission.score / Math.max(submission.total_questions, 1)) * 100)}%)
          </span>
        </div>
      )}

      {questions.length === 0 ? (
        <EmptyState
          title="No quiz questions found"
          message="No quiz questions were saved for this lecture."
        />
      ) : (
        <form onSubmit={handleSubmit}>
          <div className="quiz-questions">
            {questions.map((question, qIndex) => {
              const result = resultsByQuestionId.get(question.id)
              return (
                <fieldset className="card-block quiz-question" key={question.id}>
                  <legend>
                    <span className="quiz-question-number">Q{qIndex + 1}.</span> {question.prompt}
                  </legend>

                  <div className="quiz-options">
                    {question.options.map((option) => {
                      const isSelected = selectedAnswers[question.id] === option.position
                      const isCorrectOption =
                        result && result.correct_option_position === option.position
                      const isWrongSelection =
                        result && isSelected && !result.is_correct

                      let optionClass = 'quiz-option'
                      if (isCorrectOption) optionClass += ' quiz-option-correct'
                      else if (isWrongSelection) optionClass += ' quiz-option-wrong'
                      else if (isSelected) optionClass += ' quiz-option-selected'

                      return (
                        <label className={optionClass} key={option.id}>
                          <input
                            type="radio"
                            name={`question-${question.id}`}
                            value={option.position}
                            checked={isSelected}
                            disabled={Boolean(submission) || submitting}
                            onChange={() => handleOptionSelect(question.id, option.position)}
                          />
                          <span>{option.content}</span>
                        </label>
                      )
                    })}
                  </div>

                  {result && (
                    <div
                      className={`quiz-feedback ${
                        result.is_correct ? 'quiz-feedback-correct' : 'quiz-feedback-wrong'
                      }`}
                    >
                      <strong>{result.is_correct ? 'Correct' : 'Incorrect'}</strong>
                      <p>{result.explanation}</p>
                    </div>
                  )}
                </fieldset>
              )
            })}
          </div>

          {submitError && <ErrorMessage message={submitError} />}

          <div className="action-row quiz-actions">
            {!submission ? (
              <>
                <button
                  className="button button-primary"
                  type="submit"
                  disabled={!allAnswered || submitting}
                >
                  {submitting ? 'Submitting...' : 'Submit quiz'}
                </button>
                <span className="muted-meta">
                  {answeredCount} of {questions.length} answered
                </span>
              </>
            ) : (
              <button
                className="button button-secondary"
                type="button"
                onClick={handleRetake}
              >
                Retake quiz
              </button>
            )}
          </div>
        </form>
      )}
    </section>
  )
}
