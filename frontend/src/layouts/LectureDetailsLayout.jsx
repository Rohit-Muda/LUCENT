import { Link, NavLink, Outlet, useParams } from 'react-router-dom'
import ErrorMessage from '../components/ErrorMessage'
import LoadingSpinner from '../components/LoadingSpinner'
import StatusBadge from '../components/StatusBadge'
import useLectureWorkspace from '../hooks/useLectureWorkspace'
import { formatBytes, formatDateTime, formatDuration } from '../utils/formatters'

export default function LectureDetailsLayout() {
  const { lectureId } = useParams()
  const workspace = useLectureWorkspace(lectureId)
  const { lecture, lectureError, lectureLoading, pdfDownloading, pdfError, handleDownloadPdf } =
    workspace

  if (lectureError) {
    return (
      <section className="subpage-stack">
        <ErrorMessage message={lectureError} />
        <p className="back-link-row">
          <Link className="text-link" to="/lectures">← Back to lecture history</Link>
        </p>
      </section>
    )
  }

  if (lectureLoading || !lecture) {
    return <LoadingSpinner message="Loading lecture..." />
  }

  return (
    <section className="lecture-workspace">
      <div className="workspace-topbar-meta">
        <Link className="workspace-back-link" to="/lectures">
          <span aria-hidden="true">←</span>
          <span>Lecture Library</span>
        </Link>
        <span className="archival-edition-badge">
          <span className="archival-edition-dot" aria-hidden="true" />
          Archival Study Edition
        </span>
      </div>

      <div className="workspace-header">
        <div>
          <p className="eyebrow">LECTURE DETAILS</p>
          <h1>{lecture.title || lecture.original_filename}</h1>
          <p className="workspace-meta">
            <span>{lecture.original_filename}</span>
            <span> · {formatBytes(lecture.file_size_bytes)}</span>
            <span> · {formatDuration(lecture.duration_seconds)}</span>
            {lecture.created_at && <span> · Uploaded {formatDateTime(lecture.created_at)}</span>}
            <span className="dialect-pill">EN + TE</span>
          </p>
        </div>
        <div className="workspace-header-actions">
          <StatusBadge status={lecture.status} />
          <button
            className="button button-dark-action"
            type="button"
            disabled={pdfDownloading}
            onClick={handleDownloadPdf}
          >
            {pdfDownloading ? 'Downloading PDF...' : 'Download PDF'}
          </button>
        </div>
      </div>

      {pdfError && <ErrorMessage message={pdfError} />}

      <nav className="lecture-tabs" aria-label="Lecture sections">
        <NavLink to={`/lectures/${lectureId}`} end>
          Overview
        </NavLink>
        <NavLink to={`/lectures/${lectureId}/processing`}>Processing</NavLink>
        <NavLink to={`/lectures/${lectureId}/transcript`}>Transcript</NavLink>
        <NavLink to={`/lectures/${lectureId}/notes`}>Notes</NavLink>
        <NavLink to={`/lectures/${lectureId}/explanations`}>Telugu explanations</NavLink>
        <NavLink to={`/lectures/${lectureId}/revision`}>Revision points</NavLink>
        <NavLink to={`/lectures/${lectureId}/quiz`}>MCQ quiz</NavLink>
      </nav>

      <div className="workspace-body">
        <Outlet key={lectureId} context={workspace} />
      </div>
    </section>
  )
}
