import { useEffect } from 'react'
import { useOutletContext } from 'react-router-dom'
import EmptyState from '../components/EmptyState'
import ErrorMessage from '../components/ErrorMessage'
import LoadingSpinner from '../components/LoadingSpinner'
import { formatDateTime } from '../utils/formatters'

export default function NotesPage() {
  const {
    resources,
    loadResource,
    processing,
    regeneratingFeature,
    handleRegenerate,
  } = useOutletContext()
  const resource = resources.notes

  useEffect(() => {
    if (resource.status === 'idle') {
      loadResource('notes')
    }
  }, [resource.status, loadResource])

  if (resource.status === 'loading' || resource.status === 'idle') {
    return <LoadingSpinner message="Loading structured study notes..." />
  }

  if (resource.status === 'unavailable') {
    return (
      <EmptyState
        title="Study notes not yet available"
        message={resource.error}
      />
    )
  }

  if (resource.status === 'error') {
    return (
      <ErrorMessage
        message={resource.error}
        onRetry={() => loadResource('notes', { force: true })}
      />
    )
  }

  const content = resource.data?.content || {}
  const sections = Array.isArray(content.sections) ? content.sections : []
  const concepts = Array.isArray(content.concepts) ? content.concepts : []
  const isBusy =
    Boolean(regeneratingFeature) ||
    ['queued', 'running', 'waiting'].includes(processing?.status)

  return (
    <section className="notes-page" aria-label="Generated study notes">
      <div className="panel-header">
        <div>
          <h2>{content.title || 'Structured Study Notes'}</h2>
          {resource.data?.updated_at && (
            <p className="muted-meta">Saved {formatDateTime(resource.data.updated_at)}</p>
          )}
        </div>
        {processing?.status === 'completed' && (
          <button
            className="button button-small button-secondary"
            type="button"
            disabled={isBusy}
            onClick={() => handleRegenerate('notes')}
          >
            {regeneratingFeature === 'notes' ? 'Queuing...' : 'Regenerate notes'}
          </button>
        )}
      </div>

      {sections.length === 0 ? (
        <EmptyState
          title="No note sections found"
          message="The saved notes payload did not include structured sections."
        />
      ) : (
        <div className="notes-editorial-layout">
          <aside className="notes-toc-rail" aria-label="Table of contents">
            <div className="notes-toc-block">
              <span className="toc-heading">Table of Contents</span>
              <nav className="notes-toc-nav">
                {sections.map((section, index) => (
                  <a
                    key={`toc-${section.heading || 'sec'}-${index}`}
                    className="notes-toc-link"
                    href={`#note-section-${index + 1}`}
                  >
                    {index + 1}. {section.heading || `Section ${index + 1}`}
                  </a>
                ))}
              </nav>
            </div>

            {concepts.length > 0 && (
              <div className="notes-gloss-card">
                <span className="gloss-card-label">Key Concepts ({concepts.length})</span>
                <p className="gloss-card-preview">
                  {concepts.slice(0, 3).map((c) => c.name).join(' · ')}
                </p>
              </div>
            )}
          </aside>

          <div className="notes-reading-canvas">
            <div className="notes-sections">
              {sections.map((section, index) => (
                <article
                  className="card-block note-section"
                  id={`note-section-${index + 1}`}
                  key={`${section.heading || 'sec'}-${index}`}
                >
                  <div className="note-section-divider">
                    <span className="note-section-num">
                      Section {String(index + 1).padStart(2, '0')}
                    </span>
                    <span className="note-section-line" aria-hidden="true" />
                  </div>

                  <h3>
                    {index + 1}. {section.heading || `Section ${index + 1}`}
                  </h3>
                  {section.subheading && <h4 className="note-subheading">{section.subheading}</h4>}
                  {section.summary && (
                    <p className="note-editorial-body mixed-script">{section.summary}</p>
                  )}

                  {Array.isArray(section.definitions) && section.definitions.length > 0 && (
                    <div className="note-definition-callout">
                      <div className="note-definition-bar" aria-hidden="true" />
                      <div className="note-definition-body">
                        <h4>Definitions</h4>
                        <ul>
                          {section.definitions.map((defItem, defIdx) => (
                            <li className="mixed-script" key={defIdx}>
                              {typeof defItem === 'string'
                                ? defItem
                                : `${defItem.term}: ${defItem.definition}`}
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  )}

                  {Array.isArray(section.key_points) && section.key_points.length > 0 && (
                    <div className="note-subgroup">
                      <h4>Key points</h4>
                      <ul>
                        {section.key_points.map((point, ptIdx) => (
                          <li className="mixed-script" key={ptIdx}>{point}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {Array.isArray(section.examples) && section.examples.length > 0 && (
                    <div className="note-subgroup">
                      <h4>Lecture examples</h4>
                      <ul>
                        {section.examples.map((ex, exIdx) => (
                          <li className="mixed-script" key={exIdx}>{ex}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {section.source_excerpt && (
                    <blockquote className="source-excerpt mixed-script">
                      Source excerpt: &ldquo;{section.source_excerpt}&rdquo;
                    </blockquote>
                  )}
                </article>
              ))}
            </div>

            {concepts.length > 0 && (
              <section className="card-block concepts-summary" aria-label="Core concepts">
                <h3>Core concepts covered</h3>
                <ul className="concept-chip-list">
                  {concepts.map((concept, index) => (
                    <li className="concept-chip" key={`${concept.name}-${index}`}>
                      <strong>{concept.name}</strong>
                      {concept.source_excerpt && (
                        <small className="mixed-script">&ldquo;{concept.source_excerpt}&rdquo;</small>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
