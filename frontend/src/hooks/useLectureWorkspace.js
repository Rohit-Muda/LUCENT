import { useCallback, useEffect, useRef, useState } from 'react'
import {
  downloadLecturePdf,
  getExplanations,
  getLecture,
  getNotes,
  getProcessingStatus,
  getQuiz,
  getRevisionPoints,
  getTranscript,
  regenerateFeature,
  retryProcessing,
} from '../api/lectures'
import { getApiErrorMessage, isNotFoundError } from '../utils/formatters'

const ACTIVE_STATUSES = new Set(['queued', 'running', 'waiting'])
const POLL_INTERVAL_MS = 2000

function createInitialResources() {
  return {
    transcript: { status: 'idle', data: null, error: '' },
    notes: { status: 'idle', data: null, error: '' },
    explanations: { status: 'idle', data: null, error: '' },
    revisionPoints: { status: 'idle', data: null, error: '' },
    quiz: { status: 'idle', data: null, error: '' },
  }
}

const RESOURCE_LOADERS = {
  transcript: {
    fetch: getTranscript,
    unavailableMessage: 'Transcript has not been generated yet.',
    errorMessage: 'The transcript could not be loaded.',
  },
  notes: {
    fetch: getNotes,
    unavailableMessage: 'Study notes have not been generated yet.',
    errorMessage: 'Study notes could not be loaded.',
  },
  explanations: {
    fetch: getExplanations,
    unavailableMessage: 'Telugu explanations have not been generated yet.',
    errorMessage: 'Telugu explanations could not be loaded.',
  },
  revisionPoints: {
    fetch: getRevisionPoints,
    unavailableMessage: 'Revision points have not been generated yet.',
    errorMessage: 'Revision points could not be loaded.',
  },
  quiz: {
    fetch: getQuiz,
    unavailableMessage: 'Quiz questions have not been generated yet.',
    errorMessage: 'The lecture quiz could not be loaded.',
  },
}

const REGENERATED_RESOURCE_MAP = {
  notes: 'notes',
  explanations: 'explanations',
  'revision-points': 'revisionPoints',
  quiz: 'quiz',
}

export default function useLectureWorkspace(lectureId) {
  const [lecture, setLecture] = useState(null)
  const [lectureError, setLectureError] = useState('')
  const [lectureLoading, setLectureLoading] = useState(true)

  const [processing, setProcessing] = useState(null)
  const [processingError, setProcessingError] = useState('')
  const [retrying, setRetrying] = useState(false)
  const [regeneratingFeature, setRegeneratingFeature] = useState('')
  const [pdfDownloading, setPdfDownloading] = useState(false)
  const [pdfError, setPdfError] = useState('')

  const [resources, setResources] = useState(createInitialResources)
  const [pollTrigger, setPollTrigger] = useState(0)

  const activeLectureRef = useRef(lectureId)
  const resourcesRef = useRef(resources)
  resourcesRef.current = resources
  const pendingLoadsRef = useRef(new Set())
  const pendingRegenerationFeatureRef = useRef('')

  useEffect(() => {
    activeLectureRef.current = lectureId
    pendingLoadsRef.current.clear()
    pendingRegenerationFeatureRef.current = ''
    setLecture(null)
    setLectureError('')
    setLectureLoading(true)
    setProcessing(null)
    setProcessingError('')
    setPdfError('')
    setResources(createInitialResources())
  }, [lectureId])

  useEffect(() => {
    let active = true
    getLecture(lectureId)
      .then((result) => {
        if (active) {
          setLecture(result)
          setLectureError('')
        }
      })
      .catch((err) => {
        if (active) {
          setLectureError(
            isNotFoundError(err)
              ? 'Lecture was not found.'
              : getApiErrorMessage(err, 'Lecture details could not be loaded.'),
          )
        }
      })
      .finally(() => {
        if (active) setLectureLoading(false)
      })
    return () => {
      active = false
    }
  }, [lectureId])

  const loadResource = useCallback(
    async (key, { force = false } = {}) => {
      const loader = RESOURCE_LOADERS[key]
      if (!loader) return null

      const currentState = resourcesRef.current[key]
      if (!force && (currentState.status === 'loaded' || currentState.status === 'unavailable')) {
        return currentState.data
      }
      if (pendingLoadsRef.current.has(key)) {
        return null
      }

      pendingLoadsRef.current.add(key)
      setResources((prev) => ({
        ...prev,
        [key]: { ...prev[key], status: 'loading', error: '' },
      }))

      try {
        const data = await loader.fetch(lectureId)
        if (activeLectureRef.current !== lectureId) return null
        setResources((prev) => ({
          ...prev,
          [key]: { status: 'loaded', data, error: '' },
        }))
        return data
      } catch (err) {
        if (activeLectureRef.current !== lectureId) return null
        if (isNotFoundError(err)) {
          setResources((prev) => ({
            ...prev,
            [key]: { status: 'unavailable', data: null, error: loader.unavailableMessage },
          }))
        } else {
          setResources((prev) => ({
            ...prev,
            [key]: {
              status: 'error',
              data: null,
              error: getApiErrorMessage(err, loader.errorMessage),
            },
          }))
        }
        return null
      } finally {
        pendingLoadsRef.current.delete(key)
      }
    },
    [lectureId],
  )

  useEffect(() => {
    let active = true
    let timer = null

    async function refreshProcessingStatus() {
      try {
        const result = await getProcessingStatus(lectureId)
        if (!active) return
        setProcessing(result)
        setProcessingError('')

        if (result.status === 'completed') {
          const regenFeature = pendingRegenerationFeatureRef.current
          if (regenFeature) {
            pendingRegenerationFeatureRef.current = ''
            const resourceKey = REGENERATED_RESOURCE_MAP[regenFeature]
            if (resourceKey) {
              loadResource(resourceKey, { force: true })
            }
          }
          if (resourcesRef.current.transcript.status === 'idle') {
            loadResource('transcript')
          }
        } else if (ACTIVE_STATUSES.has(result.status)) {
          timer = setTimeout(refreshProcessingStatus, POLL_INTERVAL_MS)
        }
      } catch (err) {
        if (active) {
          setProcessingError(
            getApiErrorMessage(err, 'Processing status could not be loaded.'),
          )
        }
      }
    }

    refreshProcessingStatus()
    return () => {
      active = false
      if (timer) clearTimeout(timer)
    }
  }, [lectureId, pollTrigger, loadResource])

  const refreshStatus = useCallback(() => {
    setPollTrigger((version) => version + 1)
  }, [])

  const handleRetry = useCallback(async () => {
    setRetrying(true)
    setProcessingError('')
    try {
      const updated = await retryProcessing(lectureId)
      setProcessing(updated)
      setPollTrigger((version) => version + 1)
    } catch (err) {
      setProcessingError(
        getApiErrorMessage(err, 'Processing could not be retried. Please try again.'),
      )
    } finally {
      setRetrying(false)
    }
  }, [lectureId])

  const handleRegenerate = useCallback(
    async (feature) => {
      setRegeneratingFeature(feature)
      setProcessingError('')
      try {
        const updated = await regenerateFeature(lectureId, feature)
        pendingRegenerationFeatureRef.current = feature
        setProcessing(updated)
        setPollTrigger((version) => version + 1)
      } catch (err) {
        setProcessingError(
          getApiErrorMessage(err, 'Regeneration could not be started. Please try again.'),
        )
      } finally {
        setRegeneratingFeature('')
      }
    },
    [lectureId],
  )

  const handleDownloadPdf = useCallback(async () => {
    setPdfDownloading(true)
    setPdfError('')
    try {
      await downloadLecturePdf(lectureId)
    } catch (err) {
      setPdfError(
        getApiErrorMessage(err, 'PDF could not be downloaded. Ensure study notes are complete.'),
      )
    } finally {
      setPdfDownloading(false)
    }
  }, [lectureId])

  return {
    lecture,
    lectureError,
    lectureLoading,
    processing,
    processingError,
    retrying,
    regeneratingFeature,
    pdfDownloading,
    pdfError,
    resources,
    loadResource,
    refreshStatus,
    handleRetry,
    handleRegenerate,
    handleDownloadPdf,
  }
}
