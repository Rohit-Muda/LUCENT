import { Link, useOutletContext, useParams } from 'react-router-dom'
import ErrorMessage from '../components/ErrorMessage'
import ProcessingPanel from '../components/ProcessingPanel'
import StatusBadge from '../components/StatusBadge'
import TranscriptView from '../components/TranscriptView'
import { formatBytes, formatDateTime, formatDuration } from '../utils/formatters'

export default function LectureDetailsPage() {
  const { lectureId } = useParams()
  const {
    lecture,
    processing,
    processingError,
    retrying,
    resources,
    handleRetry,
    refreshStatus,
    handleDownloadPdf,
    pdfDownloading,
  } = useOutletContext()

  const transcript = resources.transcript

  return (
    <div className="subpage-stack">
      <dl className="details-grid">
        <dt>Original file</dt>
        <dd>{lecture.original_filename}</dd>
        <dt>Format</dt>
        <dd>{lecture.media_type}</dd>
        <dt>Size</dt>
        <dd>{formatBytes(lecture.file_size_bytes)}</dd>
        <dt>Duration</dt>
        <dd>{formatDuration(lecture.duration_seconds)}</dd>
        {lecture.created_at && (
          <>
            <dt>Uploaded</dt>
            <dd>{formatDateTime(lecture.created_at)}</dd>
          </>
        )}
        <dt>Status</dt>
        <dd>
          <StatusBadge status={lecture.status} />
        </dd>
      </dl>

      <ProcessingPanel
        processing={processing}
        processingError={processingError}
        retrying={retrying}
        onRetry={handleRetry}
        onRefresh={refreshStatus}
      />

      <section className="study-links-grid" aria-label="Saved study outputs">
        <Link className="study-link-card" to={`/lectures/${lectureId}/transcript`}>
          <strong>Transcript Viewer</strong>
          <span>View cleaned and original transcripts with timestamps</span>
        </Link>
        <Link className="study-link-card" to={`/lectures/${lectureId}/notes`}>
          <strong>Structured Notes</strong>
          <span>Headings, summaries, key points, and source excerpts</span>
        </Link>
        <Link className="study-link-card" to={`/lectures/${lectureId}/explanations`}>
          <strong>Telugu Explanations</strong>
          <span>Concise Telugu explanations for lecture concepts</span>
        </Link>
        <Link className="study-link-card" to={`/lectures/${lectureId}/revision`}>
          <strong>Revision Points</strong>
          <span>Quick exam-focused study takeaways</span>
        </Link>
        <Link className="study-link-card" to={`/lectures/${lectureId}/quiz`}>
          <strong>MCQ Quiz</strong>
          <span>Five lecture-grounded multiple-choice questions</span>
        </Link>
        <button
          className="study-link-card study-link-button"
          type="button"
          disabled={pdfDownloading}
          onClick={handleDownloadPdf}
        >
          <strong>{pdfDownloading ? 'Preparing PDF...' : 'Download Academic PDF'}</strong>
          <span>Reusable PDF with English and Telugu font support</span>
        </button>
      </section>

      {transcript.status === 'loaded' && transcript.data && (
        <TranscriptView transcript={transcript.data} />
      )}
      {transcript.status === 'error' && transcript.error && (
        <ErrorMessage message={transcript.error} />
      )}
    </div>
  )
}
