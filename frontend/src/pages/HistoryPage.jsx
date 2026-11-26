import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { downloadLecturePdf, getLectures } from '../api/lectures'
import EmptyState from '../components/EmptyState'
import ErrorMessage from '../components/ErrorMessage'
import LoadingSpinner from '../components/LoadingSpinner'
import StatusBadge from '../components/StatusBadge'
import {
  formatBytes,
  formatDateTime,
  formatDuration,
  getApiErrorMessage,
} from '../utils/formatters'

const PAGE_SIZE = 10

export default function HistoryPage() {
  const [lectures, setLectures] = useState([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [downloadingId, setDownloadingId] = useState('')
  const [pdfError, setPdfError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true
    getLectures({ limit: PAGE_SIZE, offset })
      .then((result) => {
        if (!active) return
        setLectures(result.items || [])
        setTotal(result.total ?? (result.items?.length || 0))
        setError('')
      })
      .catch((err) => {
        if (active) {
          setError(getApiErrorMessage(err, 'Lecture history could not be loaded. Please try again.'))
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [offset, reloadKey])

  function handleRetry() {
    setLoading(true)
    setError('')
    setReloadKey((current) => current + 1)
  }

  function changeOffset(nextOffset) {
    setLoading(true)
    setError('')
    setOffset(nextOffset)
  }

  async function handlePdfDownload(lectureId) {
    setDownloadingId(lectureId)
    setPdfError('')
    try {
      await downloadLecturePdf(lectureId)
    } catch (err) {
      setPdfError(
        getApiErrorMessage(err, 'Saved PDF is not available for this lecture yet.'),
      )
    } finally {
      setDownloadingId('')
    }
  }

  const hasPrevious = offset > 0
  const hasNext = offset + lectures.length < total
  const rangeStart = total === 0 ? 0 : offset + 1
  const rangeEnd = offset + lectures.length

  return (
    <section className="history-page">
      <div className="panel-header">
        <div>
          <p className="eyebrow">LECTURE LIBRARY</p>
          <h1>Lecture history</h1>
          <p className="page-intro">
            Reopen saved lectures, transcripts, notes, Telugu explanations, quizzes, and PDFs without
            repeating AI processing.
          </p>
        </div>
        <Link className="button button-primary" to="/upload">
          Upload lecture
        </Link>
      </div>

      {pdfError && <ErrorMessage message={pdfError} />}
      {loading && <LoadingSpinner message="Loading lectures..." />}
      {error && (
        <ErrorMessage
          message={error}
          onRetry={handleRetry}
        />
      )}

      {!loading && !error && lectures.length === 0 && (
        <EmptyState
          title="No lectures yet"
          message="Upload an MP3 or WAV lecture to get started."
          actionLabel="Upload lecture"
          actionTo="/upload"
        />
      )}

      {!loading && !error && lectures.length > 0 && (
        <>
          <div className="lecture-list">
            {lectures.map((lecture) => (
              <div className="lecture-row lecture-history-row" key={lecture.id}>
                <Link className="lecture-row-main" to={`/lectures/${lecture.id}`}>
                  <strong>{lecture.title || lecture.original_filename}</strong>
                  <small>
                    {lecture.original_filename}
                    {' · '}
                    {formatBytes(lecture.file_size_bytes)}
                    {' · '}
                    {formatDuration(lecture.duration_seconds)}
                    {lecture.created_at && ` · ${formatDateTime(lecture.created_at)}`}
                  </small>
                </Link>
                <div className="lecture-row-actions">
                  <span className="dialect-pill">EN + TE</span>
                  <StatusBadge status={lecture.status} />
                  {lecture.status === 'completed' ? (
                    <>
                      <Link
                        className="button button-small button-secondary"
                        to={`/lectures/${lecture.id}/notes`}
                      >
                        Notes
                      </Link>
                      <Link
                        className="button button-small button-secondary"
                        to={`/lectures/${lecture.id}/quiz`}
                      >
                        Quiz
                      </Link>
                      <button
                        className="button button-small button-secondary"
                        type="button"
                        disabled={downloadingId === lecture.id}
                        onClick={() => handlePdfDownload(lecture.id)}
                      >
                        {downloadingId === lecture.id ? 'Downloading...' : 'PDF'}
                      </button>
                    </>
                  ) : (
                    <Link
                      className="button button-small button-secondary"
                      to={`/lectures/${lecture.id}/processing`}
                    >
                      Status
                    </Link>
                  )}
                </div>
              </div>
            ))}
          </div>

          {total > PAGE_SIZE && (
            <nav className="pagination-bar" aria-label="Lecture history pagination">
              <span className="muted-meta">
                Showing {rangeStart}–{rangeEnd} of {total} lectures
              </span>
              <div className="action-row">
                <button
                  className="button button-small button-secondary"
                  type="button"
                  disabled={!hasPrevious}
                  onClick={() => changeOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  Previous
                </button>
                <button
                  className="button button-small button-secondary"
                  type="button"
                  disabled={!hasNext}
                  onClick={() => changeOffset(offset + PAGE_SIZE)}
                >
                  Next
                </button>
              </div>
            </nav>
          )}
        </>
      )}
    </section>
  )
}
