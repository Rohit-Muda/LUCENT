import { useEffect } from 'react'
import { useOutletContext } from 'react-router-dom'
import EmptyState from '../components/EmptyState'
import ErrorMessage from '../components/ErrorMessage'
import LoadingSpinner from '../components/LoadingSpinner'
import TranscriptView from '../components/TranscriptView'

export default function TranscriptPage() {
  const { resources, loadResource } = useOutletContext()
  const resource = resources.transcript

  useEffect(() => {
    if (resource.status === 'idle') {
      loadResource('transcript')
    }
  }, [resource.status, loadResource])

  if (resource.status === 'loading' || resource.status === 'idle') {
    return <LoadingSpinner message="Loading saved transcript..." />
  }

  if (resource.status === 'unavailable') {
    return (
      <EmptyState
        title="Transcript not yet available"
        message={resource.error}
      />
    )
  }

  if (resource.status === 'error') {
    return (
      <ErrorMessage
        message={resource.error}
        onRetry={() => loadResource('transcript', { force: true })}
      />
    )
  }

  return <TranscriptView transcript={resource.data} />
}
