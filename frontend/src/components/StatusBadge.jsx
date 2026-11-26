const statusClasses = {
  completed: 'status-pill status-completed',
  failed: 'status-pill status-failed',
  queued: 'status-pill status-queued',
  running: 'status-pill status-running',
  waiting: 'status-pill status-waiting',
}

export default function StatusBadge({ status }) {
  const className = statusClasses[status] || 'status-pill'
  return <span className={className}>{status}</span>
}
