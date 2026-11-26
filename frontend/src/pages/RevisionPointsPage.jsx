import { useEffect } from 'react'
import { useOutletContext } from 'react-router-dom'
import EmptyState from '../components/EmptyState'
import ErrorMessage from '../components/ErrorMessage'
import LoadingSpinner from '../components/LoadingSpinner'

export default function RevisionPointsPage() {
  const {
    resources,
    loadResource,
    processing,
    regeneratingFeature,
    handleRegenerate,
  } = useOutletContext()
  const resource = resources.revisionPoints

  useEffect(() => {
    if (resource.status === 'idle') {
      loadResource('revisionPoints')
    }
  }, [resource.status, loadResource])

  if (resource.status === 'loading' || resource.status === 'idle') {
    return <LoadingSpinner message="Loading revision points..." />
  }

  if (resource.status === 'unavailable') {
    return (
      <EmptyState
        title="Revision points not yet available"
        message={resource.error}
      />
    )
  }

  if (resource.status === 'error') {
    return (
      <ErrorMessage
        message={resource.error}
        onRetry={() => loadResource('revisionPoints', { force: true })}
      />
    )
  }

  const points = Array.isArray(resource.data) ? resource.data : []
  const isBusy =
    Boolean(regeneratingFeature) ||
    ['queued', 'running', 'waiting'].includes(processing?.status)

  return (
    <section className="revision-page" aria-label="Revision points">
      <div className="panel-header">
        <div>
          <h2>Revision Points</h2>
          <p className="muted-meta">Concise takeaways for quick review before exams.</p>
        </div>
        {processing?.status === 'completed' && (
          <button
            className="button button-small button-secondary"
            type="button"
            disabled={isBusy}
            onClick={() => handleRegenerate('revision-points')}
          >
            {regeneratingFeature === 'revision-points'
              ? 'Queuing...'
              : 'Regenerate revision points'}
          </button>
        )}
      </div>

      {points.length === 0 ? (
        <EmptyState
          title="No revision points found"
          message="No revision points were saved for this lecture."
        />
      ) : (
        <ol className="revision-list">
          {points.map((point, index) => (
            <li className="card-block revision-item" key={point.id}>
              <div className="revision-item-row">
                <span className="revision-badge">{String(index + 1).padStart(2, '0')}</span>
                <div className="revision-item-body">
                  <p className="revision-content mixed-script">{point.content}</p>
                  {point.source_excerpt && (
                    <p className="source-excerpt mixed-script">
                      Reference: &ldquo;{point.source_excerpt}&rdquo;
                    </p>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
