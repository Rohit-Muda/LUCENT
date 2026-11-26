import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { uploadLecture } from '../api/lectures'
import { formatBytes } from '../utils/formatters'

const maxUploadBytes = Number(import.meta.env.VITE_MAX_UPLOAD_SIZE_BYTES || 25_000_000)

function formatUploadBytes(bytes) {
  if (bytes < 1_000) return `${bytes} B`
  if (bytes < 1_000_000) return `${(bytes / 1_000).toFixed(1)} KB`
  return `${(bytes / 1_000_000).toFixed(1)} MB`
}

function getErrorMessage(error) {
  return error.response?.data?.error?.message || 'Upload failed. Please try again.'
}

export default function UploadPage() {
  const [selectedFile, setSelectedFile] = useState(null)
  const [error, setError] = useState('')
  const [lecture, setLecture] = useState(null)
  const [progress, setProgress] = useState(null)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef(null)

  function chooseFile(event) {
    const file = event.target.files?.[0]
    setLecture(null)
    setProgress(null)
    setError('')
    if (!file) {
      setSelectedFile(null)
      return
    }

    const extension = file.name.split('.').pop()?.toLowerCase()
    if (!['mp3', 'wav'].includes(extension)) {
      setSelectedFile(null)
      setError('Choose an MP3 or WAV audio file.')
      return
    }
    if (file.size === 0) {
      setSelectedFile(null)
      setError('The selected file is empty.')
      return
    }
    if (file.size > maxUploadBytes) {
      setSelectedFile(null)
      setError(`The file exceeds the ${formatUploadBytes(maxUploadBytes)} upload limit.`)
      return
    }
    setSelectedFile(file)
  }

  async function submitUpload(event) {
    event.preventDefault()
    if (!selectedFile || uploading) return

    setUploading(true)
    setError('')
    setLecture(null)
    setProgress(null)
    try {
      const result = await uploadLecture(selectedFile, (progressEvent) => {
        if (progressEvent.total) {
          setProgress(Math.round((progressEvent.loaded / progressEvent.total) * 100))
        }
      })
      setLecture(result)
      setProgress(100)
      setSelectedFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (uploadError) {
      setError(getErrorMessage(uploadError))
    } finally {
      setUploading(false)
    }
  }

  return (
    <section className="upload-page">
      <p className="eyebrow">CODE-MIXED LECTURE NOTES</p>
      <h1>Turn a lecture recording into study material</h1>
      <p className="page-intro">
        Upload an English-Telugu lecture recording to begin. Your transcript and
        study material will be saved with the lecture.
      </p>

      <form className="upload-card" onSubmit={submitUpload}>
        <label className="dropzone" htmlFor="lecture-file">
          <strong>Select a lecture recording</strong>
          <span>MP3 or WAV, up to {formatUploadBytes(maxUploadBytes)} (server check: {formatBytes(maxUploadBytes)} max)</span>
          <input
            id="lecture-file"
            className="file-input"
            type="file"
            accept=".mp3,.wav,audio/mpeg,audio/wav"
            ref={fileInputRef}
            onChange={chooseFile}
            disabled={uploading}
          />
        </label>

        {selectedFile && (
          <div className="file-info" aria-live="polite">
            <span>
              <strong>{selectedFile.name}</strong>
              <span className="file-size">{formatUploadBytes(selectedFile.size)}</span>
            </span>
          </div>
        )}

        {uploading && (
          <div className="upload-progress">
            <label htmlFor="upload-progress">Uploading lecture</label>
            <progress id="upload-progress" max="100" value={progress ?? undefined} />
            <span>{progress == null ? 'Starting upload...' : `${progress}%`}</span>
          </div>
        )}

        <button className="button button-primary upload-button" type="submit" disabled={!selectedFile || uploading}>
          {uploading ? 'Uploading...' : 'Upload lecture'}
        </button>
        <p className="helper-text">The server checks audio format, content, size, and duration.</p>

        {error && <p className="notice notice-error" role="alert">{error}</p>}
        {lecture && (
          <div className="notice notice-success" role="status">
            <p>
              Lecture uploaded.{' '}
              <Link to={`/lectures/${lecture.id}/processing`}>Track processing status</Link>
              {' · '}
              <Link to={`/lectures/${lecture.id}`}>View lecture details</Link>
            </p>
          </div>
        )}
      </form>
    </section>
  )
}
