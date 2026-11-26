import { formatStage } from '../utils/formatters'
import StatusBadge from './StatusBadge'

const PIPELINE_STAGES = [
  { key: 'validate_upload', label: 'Validate uploaded audio' },
  { key: 'transcribe', label: 'Transcribe English-Telugu speech' },
  { key: 'generate_notes', label: 'Generate structured study notes' },
  { key: 'generate_explanations', label: 'Generate Telugu concept explanations' },
  { key: 'generate_revision_points', label: 'Generate revision points' },
  { key: 'generate_quiz', label: 'Generate MCQ quiz' },
  { key: 'generate_pdf', label: 'Generate academic PDF' },
]

function getStageState(stageKey, index, processing) {
  if (!processing) return 'pending'
  if (processing.status === 'completed') return 'done'

  const stageOrder = PIPELINE_STAGES.map((stage) => stage.key)
  const lastIndex = processing.last_successful_stage
    ? stageOrder.indexOf(processing.last_successful_stage)
    : -1

  if (index <= lastIndex) return 'done'
  if (processing.current_stage === stageKey) {
    return processing.status === 'failed' ? 'failed' : 'active'
  }
  return 'pending'
}

export default function ProcessingPanel({
  processing,
  processingError,
  retrying,
  onRetry,
  onRefresh,
}) {
  const isRegenerating = Boolean(processing?.current_stage?.startsWith('regenerate_'))

  return (
    <section className="notice processing-panel" aria-label="Processing status">
      <div className="panel-header">
        <h2>Processing status</h2>
        {processing && <StatusBadge status={processing.status} />}
      </div>

      {processingError && (
        <div className="notice notice-error" role="alert">
          <p>{processingError}</p>
          {onRefresh && (
            <button className="button button-small" type="button" onClick={onRefresh}>
              Refresh status
            </button>
          )}
        </div>
      )}

      {!processing && !processingError && <p role="status">Loading processing status...</p>}

      {processing && (
        <>
          <p role="status">Status: {processing.status.replaceAll('_', ' ')}</p>
          {processing.current_stage && (
            <p>Current stage: {formatStage(processing.current_stage)}</p>
          )}
          {processing.last_successful_stage && (
            <p>Last completed stage: {formatStage(processing.last_successful_stage)}</p>
          )}
          {processing.retry_count > 0 && (
            <p className="muted-meta">Automatic retries used: {processing.retry_count}</p>
          )}
          {processing.last_error && (
            <p className="notice notice-error" role="alert">
              {processing.last_error}
            </p>
          )}

          {!isRegenerating && (
            <ol className="stage-list" aria-label="Pipeline stages">
              {PIPELINE_STAGES.map((stage, index) => {
                const state = getStageState(stage.key, index, processing)
                return (
                  <li className={`stage-item stage-${state}`} key={stage.key}>
                    <span className="stage-indicator" aria-hidden="true">
                      {state === 'done' ? '✓' : state === 'failed' ? '!' : state === 'active' ? '•' : '○'}
                    </span>
                    <span className="stage-label">{stage.label}</span>
                  </li>
                )
              })}
            </ol>
          )}

          {processing.can_retry && (
            <div className="action-row">
              <button
                className="button button-primary"
                type="button"
                disabled={retrying}
                onClick={onRetry}
              >
                {retrying ? 'Retrying...' : 'Retry processing'}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
