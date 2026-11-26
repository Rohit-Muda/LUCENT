import apiClient from './client'

export async function uploadLecture(file, onUploadProgress) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await apiClient.post('/lectures', formData, {
    onUploadProgress,
  })
  return response.data
}

export async function getLectures(params = {}) {
  const response = await apiClient.get('/lectures', { params })
  return response.data
}

export async function getLecture(lectureId) {
  const response = await apiClient.get(`/lectures/${encodeURIComponent(lectureId)}`)
  return response.data
}

export async function getTranscript(lectureId) {
  const response = await apiClient.get(
    `/lectures/${encodeURIComponent(lectureId)}/transcript`,
  )
  return response.data
}

export async function getProcessingStatus(lectureId) {
  const response = await apiClient.get(
    `/lectures/${encodeURIComponent(lectureId)}/processing`,
  )
  return response.data
}

export async function retryProcessing(lectureId) {
  const response = await apiClient.post(
    `/lectures/${encodeURIComponent(lectureId)}/retry`,
  )
  return response.data
}

export async function getNotes(lectureId) {
  const response = await apiClient.get(
    `/lectures/${encodeURIComponent(lectureId)}/notes`,
  )
  return response.data
}

export async function getExplanations(lectureId) {
  const response = await apiClient.get(
    `/lectures/${encodeURIComponent(lectureId)}/explanations`,
  )
  return response.data
}

export async function getRevisionPoints(lectureId) {
  const response = await apiClient.get(
    `/lectures/${encodeURIComponent(lectureId)}/revision-points`,
  )
  return response.data
}

export async function getQuiz(lectureId) {
  const response = await apiClient.get(
    `/lectures/${encodeURIComponent(lectureId)}/quiz`,
  )
  return response.data
}

export async function submitQuiz(lectureId, answers) {
  const response = await apiClient.post(
    `/lectures/${encodeURIComponent(lectureId)}/quiz/submit`,
    { answers },
  )
  return response.data
}

export async function regenerateFeature(lectureId, feature) {
  const response = await apiClient.post(
    `/lectures/${encodeURIComponent(lectureId)}/regenerate/${encodeURIComponent(feature)}`,
  )
  return response.data
}

export function getPdfDownloadUrl(lectureId) {
  const base = apiClient.defaults.baseURL || '/api'
  return `${base}/lectures/${encodeURIComponent(lectureId)}/pdf`
}

function parseFilenameFromHeader(headerValue, lectureId) {
  if (typeof headerValue === 'string') {
    const match = headerValue.match(/filename="?([^";\n]+)"?/i)
    if (match?.[1]) return match[1]
  }
  return `lecture-${lectureId.slice(0, 8)}.pdf`
}

export async function downloadLecturePdf(lectureId) {
  try {
    const response = await apiClient.get(
      `/lectures/${encodeURIComponent(lectureId)}/pdf`,
      { responseType: 'blob' },
    )
    const filename = parseFilenameFromHeader(
      response.headers?.['content-disposition'],
      lectureId,
    )
    const blob = response.data
    if (typeof window !== 'undefined' && window.URL?.createObjectURL) {
      const objectUrl = window.URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = objectUrl
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.URL.revokeObjectURL(objectUrl)
    }
    return { filename }
  } catch (error) {
    if (error?.response?.data instanceof Blob) {
      try {
        const text = await error.response.data.text()
        const parsed = JSON.parse(text)
        error.response.data = parsed
      } catch {
        /* keep original blob error if non-JSON */
      }
    }
    throw error
  }
}
