export function formatBytes(bytes) {
  if (bytes == null) return 'Unavailable'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function formatDuration(seconds) {
  if (seconds == null) return 'Unavailable'
  const totalSeconds = Math.round(seconds)
  const minutes = Math.floor(totalSeconds / 60)
  const remainder = totalSeconds % 60
  return minutes ? `${minutes} min ${remainder} sec` : `${remainder} sec`
}

export function formatTimestamp(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return '00:00'
  const totalSeconds = Math.max(0, Math.floor(Number(seconds)))
  const minutes = Math.floor(totalSeconds / 60)
  const remainder = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
}

export function formatStage(stage) {
  if (!stage) return ''
  return stage.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function formatDateTime(isoString) {
  if (!isoString) return 'Unavailable'
  const parsed = new Date(isoString)
  if (Number.isNaN(parsed.getTime())) return 'Unavailable'
  return parsed.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function getApiErrorMessage(error, fallback = 'Request failed. Please try again.') {
  return error?.response?.data?.error?.message || fallback
}

export function isNotFoundError(error) {
  return error?.response?.status === 404
}
