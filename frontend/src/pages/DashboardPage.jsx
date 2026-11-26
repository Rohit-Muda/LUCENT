import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getLectures } from '../api/lectures'
import EmptyState from '../components/EmptyState'
import ErrorMessage from '../components/ErrorMessage'
import LoadingSpinner from '../components/LoadingSpinner'
import StatusBadge from '../components/StatusBadge'
import { formatDateTime, formatDuration, getApiErrorMessage } from '../utils/formatters'

const ACTIVE_STATUSES = new Set(['queued', 'processing', 'awaiting_transcription', 'failed'])

export default function DashboardPage() {
  const [lectures, setLectures] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true
    getLectures({ limit: 5, offset: 0 })
      .then((result) => {
        if (!active) return
        setLectures(result.items || [])
        setTotal(result.total ?? (result.items?.length || 0))
        setError('')
      })
      .catch((err) => {
        if (active) {
          setError(getApiErrorMessage(err, 'Recent lectures could not be loaded.'))
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [reloadKey])

  function handleRetry() {
    setLoading(true)
    setError('')
    setReloadKey((current) => current + 1)
  }

  const completedCount = lectures.filter((item) => item.status === 'completed').length
  const latestCompleted = lectures.find((item) => item.status === 'completed') || null

  return (
    <section className="dashboard-page">
      {/* Editorial Welcome Header */}
      <div className="dashboard-welcome">
        <div className="dashboard-welcome-copy">
          <div className="dashboard-badges-row">
            <span className="archive-status-badge">
              <span className="archive-status-dot" aria-hidden="true" />
              Bilingual Archive · EN / TE · {total} {total === 1 ? 'Lecture' : 'Lectures'}
            </span>
          </div>
          <h1>Study Workspace</h1>
          <p className="page-intro editorial-intro">
            Transform English–Telugu classroom lectures into saved transcripts, structured notes,
            Telugu explanations, revision points, and practice quizzes.
          </p>
        </div>

        <div className="stats-strip" aria-label="Archive summary">
          <div className="stats-strip-item">
            <span className="stats-label">Saved Lectures</span>
            <strong className="stats-value">{total}</strong>
          </div>
          <div className="stats-strip-item">
            <span className="stats-label">Recent Ready</span>
            <strong className="stats-value stats-value-accent">{completedCount}</strong>
          </div>
          <div className="stats-strip-item">
            <span className="stats-label">Languages</span>
            <strong className="stats-value stats-value-secondary">EN + TE</strong>
          </div>
        </div>
      </div>

      {/* 12-Column Primary Workspace Grid */}
      <div className="dashboard-bento">
        <div className="bento-col-ingest card-block">
          <div className="bento-card-header">
            <span className="eyebrow">ACOUSTIC INGESTION</span>
            <h2>Ingest Lecture</h2>
          </div>
          <p className="bento-card-desc">
            Upload classroom MP3 or WAV recordings. Audio is validated before transcription and
            saved with resumable stage checkpoints.
          </p>
          <div className="ingest-spec-pills">
            <span>MP3 / WAV</span>
            <span>EN + TE Code-Mixed</span>
            <span>PDF Export</span>
          </div>
          <div className="action-row bento-actions">
            <Link className="button button-primary" to="/upload">
              Upload lecture
            </Link>
            <Link className="button button-secondary" to="/lectures">
              View lecture history{total > 0 ? ` (${total})` : ''}
            </Link>
          </div>
        </div>

        <div className="bento-col-suite card-block">
          <div className="bento-card-header-row">
            <div>
              <span className="eyebrow">STUDY SUITE</span>
              <h2>
                {latestCompleted
                  ? latestCompleted.title || latestCompleted.original_filename
                  : 'Generated Study Matrix'}
              </h2>
            </div>
            {latestCompleted && <StatusBadge status={latestCompleted.status} />}
          </div>

          {latestCompleted ? (
            <>
              <p className="bento-card-desc editorial-intro">
                Reopen saved study modules for this lecture without repeating AI processing.
              </p>
              <div className="suite-matrix">
                <Link className="suite-tile" to={`/lectures/${latestCompleted.id}/notes`}>
                  <strong className="suite-tile-title">Structured Notes</strong>
                  <span>Hierarchical sections, definitions &amp; excerpts</span>
                </Link>
                <Link className="suite-tile" to={`/lectures/${latestCompleted.id}/explanations`}>
                  <strong className="suite-tile-title">Telugu Explanations</strong>
                  <span>Concise bilingual concept clarifications</span>
                </Link>
                <Link className="suite-tile" to={`/lectures/${latestCompleted.id}/revision`}>
                  <strong className="suite-tile-title">Revision Points</strong>
                  <span>High-yield takeaways for quick recall</span>
                </Link>
                <Link className="suite-tile" to={`/lectures/${latestCompleted.id}/quiz`}>
                  <strong className="suite-tile-title">MCQ Quiz</strong>
                  <span>Practice questions with graded review</span>
                </Link>
              </div>
            </>
          ) : (
            <p className="bento-card-desc">
              Once a lecture finishes processing, its Structured Notes, Telugu Explanations,
              Revision Points, MCQ Quiz, and Academic PDF appear here for instant reopening.
            </p>
          )}
        </div>
      </div>

      {/* Recent Lecture Archives */}
      <section className="dashboard-section" aria-label="Recent lectures">
        <div className="section-heading-row">
          <div className="section-title-group">
            <h2>Recent lectures</h2>
            {total > 0 && <span className="count-pill">{lectures.length} of {total}</span>}
          </div>
          {total > 5 && (
            <Link className="text-link" to="/lectures">
              See all {total} lectures →
            </Link>
          )}
        </div>

        {loading && <LoadingSpinner message="Loading recent lectures..." />}
        {error && (
          <ErrorMessage
            message={error}
            onRetry={handleRetry}
          />
        )}

        {!loading && !error && lectures.length === 0 && (
          <EmptyState
            title="No lectures uploaded yet"
            message="Upload your first English-Telugu lecture audio file to generate study materials."
            actionLabel="Upload lecture"
            actionTo="/upload"
          />
        )}

        {!loading && !error && lectures.length > 0 && (
          <div className="lecture-list">
            {lectures.map((lecture) => (
              <div className="lecture-row" key={lecture.id}>
                <Link className="lecture-row-main" to={`/lectures/${lecture.id}`}>
                  <strong>{lecture.title || lecture.original_filename}</strong>
                  <small>
                    {lecture.original_filename}
                    {' · '}
                    {formatDuration(lecture.duration_seconds)}
                    {lecture.created_at && ` · ${formatDateTime(lecture.created_at)}`}
                  </small>
                </Link>
                <div className="lecture-row-actions">
                  <span className="dialect-pill">EN + TE</span>
                  <StatusBadge status={lecture.status} />
                  {ACTIVE_STATUSES.has(lecture.status) ? (
                    <Link
                      className="button button-small button-secondary"
                      to={`/lectures/${lecture.id}/processing`}
                    >
                      Processing
                    </Link>
                  ) : (
                    <Link
                      className="button button-small button-secondary"
                      to={`/lectures/${lecture.id}`}
                    >
                      Open
                    </Link>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </section>
  )
}
