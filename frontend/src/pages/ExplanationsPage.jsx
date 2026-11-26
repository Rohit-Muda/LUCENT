import { useEffect } from 'react'
import { useOutletContext } from 'react-router-dom'
import EmptyState from '../components/EmptyState'
import ErrorMessage from '../components/ErrorMessage'
import LoadingSpinner from '../components/LoadingSpinner'

export default function ExplanationsPage() {
  const {
    resources,
    loadResource,
    processing,
    regeneratingFeature,
    handleRegenerate,
  } = useOutletContext()
  const resource = resources.explanations

  useEffect(() => {
    if (resource.status === 'idle') {
      loadResource('explanations')
    }
  }, [resource.status, loadResource])

  if (resource.status === 'loading' || resource.status === 'idle') {
    return <LoadingSpinner message="Loading Telugu concept explanations..." />
  }

  if (resource.status === 'unavailable') {
    return (
      <EmptyState
        title="Telugu explanations not yet available"
        message={resource.error}
      />
    )
  }

  if (resource.status === 'error') {
    return (
      <ErrorMessage
        message={resource.error}
        onRetry={() => loadResource('explanations', { force: true })}
      />
    )
  }

  const items = Array.isArray(resource.data) ? resource.data : []
  const isBusy =
    Boolean(regeneratingFeature) ||
    ['queued', 'running', 'waiting'].includes(processing?.status)

  return (
    <section className="explanations-page" aria-label="Telugu-supported concept explanations">
      <div className="panel-header">
        <div>
          <h2>Telugu-Supported Explanations</h2>
          <p className="muted-meta">
            Concise Telugu explanations grounded in core concepts from the lecture.
          </p>
        </div>
        {processing?.status === 'completed' && (
          <button
            className="button button-small button-secondary"
            type="button"
            disabled={isBusy}
            onClick={() => handleRegenerate('explanations')}
          >
            {regeneratingFeature === 'explanations'
              ? 'Queuing...'
              : 'Regenerate explanations'}
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <EmptyState
          title="No concept explanations found"
          message="No Telugu concept explanations were saved for this lecture."
        />
      ) : (
        <div className="explanation-list">
          {items.map((item, index) => (
            <article className="card-block explanation-card" key={item.id}>
              <div className="explanation-card-header">
                <span className="explanation-index">
                  Concept {String(index + 1).padStart(2, '0')}
                </span>
                <span className="dialect-pill">EN → TE</span>
              </div>
              <h3>{item.concept}</h3>
              <p className="telugu-text mixed-script" lang="te">
                {item.explanation_telugu}
              </p>
              {item.source_excerpt && (
                <blockquote className="source-excerpt mixed-script">
                  Lecture reference: &ldquo;{item.source_excerpt}&rdquo;
                </blockquote>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
