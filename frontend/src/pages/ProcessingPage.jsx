import { Link, useOutletContext, useParams } from 'react-router-dom'
import ProcessingPanel from '../components/ProcessingPanel'

export default function ProcessingPage() {
  const { lectureId } = useParams()
  const {
    processing,
    processingError,
    retrying,
    handleRetry,
    refreshStatus,
    handleDownloadPdf,
    pdfDownloading,
  } = useOutletContext()

  return (
    <div className="subpage-stack">
      <ProcessingPanel
        processing={processing}
        processingError={processingError}
        retrying={retrying}
        onRetry={handleRetry}
        onRefresh={refreshStatus}
      />

      {processing?.status === 'completed' && (
        <section className="card-block" aria-label="Completed study outputs">
          <h2>Study outputs ready</h2>
          <p className="page-intro">
            All saved materials can be reopened below without repeating transcription or AI generation.
          </p>
          <div className="action-row">
            <Link className="button button-primary" to={`/lectures/${lectureId}/notes`}>
              Open structured notes
            </Link>
            <Link className="button button-secondary" to={`/lectures/${lectureId}/transcript`}>
              View transcript
            </Link>
            <Link className="button button-secondary" to={`/lectures/${lectureId}/explanations`}>
              Telugu explanations
            </Link>
            <Link className="button button-secondary" to={`/lectures/${lectureId}/revision`}>
              Revision points
            </Link>
            <Link className="button button-secondary" to={`/lectures/${lectureId}/quiz`}>
              Take MCQ quiz
            </Link>
            <button
              className="button button-secondary"
              type="button"
              disabled={pdfDownloading}
              onClick={handleDownloadPdf}
            >
              {pdfDownloading ? 'Downloading PDF...' : 'Download PDF'}
            </button>
          </div>
        </section>
      )}
    </div>
  )
}
