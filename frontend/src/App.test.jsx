import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./api/lectures', () => ({
  downloadLecturePdf: vi.fn(),
  getExplanations: vi.fn(),
  getLecture: vi.fn(),
  getLectures: vi.fn(),
  getNotes: vi.fn(),
  getPdfDownloadUrl: vi.fn((id) => `/api/lectures/${id}/pdf`),
  getProcessingStatus: vi.fn(),
  getQuiz: vi.fn(),
  getRevisionPoints: vi.fn(),
  getTranscript: vi.fn(),
  regenerateFeature: vi.fn(),
  retryProcessing: vi.fn(),
  submitQuiz: vi.fn(),
  uploadLecture: vi.fn(),
}))

import {
  downloadLecturePdf,
  getExplanations,
  getLecture,
  getLectures,
  getNotes,
  getProcessingStatus,
  getQuiz,
  getRevisionPoints,
  getTranscript,
  retryProcessing,
} from './api/lectures'

const lecture = {
  id: 'lecture-123',
  title: null,
  original_filename: 'lesson.wav',
  media_type: 'audio/wav',
  file_size_bytes: 3000,
  duration_seconds: 90,
  status: 'queued',
  created_at: '2026-11-26T10:00:00Z',
}

function openRoute(path) {
  window.history.replaceState({}, '', path)
  return render(<App />)
}

describe('lecture processing details and navigation', () => {
  afterEach(() => {
    cleanup()
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    window.history.replaceState({}, '', '/')
  })

  beforeEach(() => {
    vi.clearAllMocks()
    getLecture.mockResolvedValue(lecture)
    getLectures.mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 })
    getTranscript.mockResolvedValue({
      provider: 'groq',
      detected_language: 'telugu',
      cleaned_text: 'కణం యొక్క కేంద్రకం',
      original_text: 'కణం   యొక్క కేంద్రకం',
      segments: [{ start: 1.2, end: 3.8, text: 'కణం యొక్క కేంద్రకం' }],
    })
    getNotes.mockRejectedValue({ response: { status: 404 } })
    getExplanations.mockRejectedValue({ response: { status: 404 } })
    getRevisionPoints.mockRejectedValue({ response: { status: 404 } })
    getQuiz.mockRejectedValue({ response: { status: 404 } })
    downloadLecturePdf.mockResolvedValue({ filename: 'lesson.pdf' })
    getProcessingStatus.mockResolvedValue({
      id: 'job-123',
      status: 'running',
      current_stage: 'validate_upload',
      last_successful_stage: null,
      retry_count: 0,
      attempts_by_stage: { validate_upload: 1 },
      manual_retry_count: 0,
      last_error: null,
      can_retry: false,
    })
  })

  it('shows the current processing stage', async () => {
    openRoute('/lectures/lecture-123')

    expect(await screen.findByText('Current stage: Validate Upload')).toBeInTheDocument()
    expect(screen.getByText('Status: running')).toBeInTheDocument()
  })

  it('offers retry for failed jobs and refreshes the status', async () => {
    getProcessingStatus.mockResolvedValueOnce({
      id: 'job-123',
      status: 'failed',
      current_stage: 'validate_upload',
      last_successful_stage: null,
      retry_count: 3,
      attempts_by_stage: { validate_upload: 3 },
      manual_retry_count: 0,
      last_error: 'The stored audio could not be validated.',
      can_retry: true,
    }).mockResolvedValueOnce({
      id: 'job-123',
      status: 'queued',
      current_stage: 'validate_upload',
      last_successful_stage: null,
      retry_count: 3,
      attempts_by_stage: { validate_upload: 0 },
      manual_retry_count: 1,
      last_error: null,
      can_retry: false,
    })
    retryProcessing.mockResolvedValue({
      id: 'job-123',
      status: 'queued',
      current_stage: 'validate_upload',
      last_successful_stage: null,
      retry_count: 3,
      attempts_by_stage: { validate_upload: 0 },
      manual_retry_count: 1,
      last_error: null,
      can_retry: false,
    })
    const user = userEvent.setup()
    openRoute('/lectures/lecture-123')

    await user.click(await screen.findByRole('button', { name: 'Retry processing' }))

    await waitFor(() => {
      expect(retryProcessing).toHaveBeenCalledWith('lecture-123')
      expect(getProcessingStatus).toHaveBeenCalledTimes(2)
      expect(screen.getByText('Status: queued')).toBeInTheDocument()
    })
  })

  it('displays the cleaned transcript, original text, and segment timestamps', async () => {
    getProcessingStatus.mockResolvedValue({
      id: 'job-123',
      status: 'completed',
      current_stage: null,
      last_successful_stage: 'transcribe',
      retry_count: 0,
      attempts_by_stage: { validate_upload: 1, transcribe: 1 },
      manual_retry_count: 0,
      last_error: null,
      can_retry: false,
    })
    openRoute('/lectures/lecture-123')

    const transcriptPanel = await screen.findByRole('region', {
      name: 'Lecture transcript',
    })
    expect(transcriptPanel).toHaveTextContent('కణం యొక్క కేంద్రకం')
    expect(screen.getByText('Provider: groq · Detected language: telugu')).toBeInTheDocument()
    expect(transcriptPanel.querySelector('time').textContent).toBe('00:01–00:03')
    await userEvent.click(screen.getByText('Original transcript'))
    expect(transcriptPanel.querySelectorAll('.transcript-text')[1].textContent).toBe(
      'కణం   యొక్క కేంద్రకం',
    )
  })

  it('toggles between light and dark themes and persists the choice', async () => {
    const user = userEvent.setup()
    openRoute('/')

    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    const toggle = await screen.findByRole('button', { name: 'Switch to dark theme' })
    await user.click(toggle)

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(localStorage.getItem('theme')).toBe('dark')
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument()
  })

  it('renders dashboard empty state and lecture history with pagination', async () => {
    const user = userEvent.setup()
    openRoute('/')

    expect(await screen.findByText('No lectures uploaded yet')).toBeInTheDocument()

    getLectures.mockResolvedValueOnce({
      items: [
        {
          id: 'lec-1',
          title: 'Cell Biology Basics',
          original_filename: 'cells.mp3',
          media_type: 'audio/mpeg',
          file_size_bytes: 204800,
          duration_seconds: 120,
          status: 'completed',
          created_at: '2026-11-26T09:00:00Z',
        },
      ],
      total: 12,
      limit: 10,
      offset: 0,
    }).mockResolvedValueOnce({
      items: [
        {
          id: 'lec-2',
          title: 'Genetics Intro',
          original_filename: 'genetics.wav',
          media_type: 'audio/wav',
          file_size_bytes: 512000,
          duration_seconds: 300,
          status: 'queued',
          created_at: '2026-11-25T09:00:00Z',
        },
      ],
      total: 12,
      limit: 10,
      offset: 10,
    })

    await user.click(screen.getByRole('link', { name: 'Lecture history' }))

    expect(await screen.findByText('Cell Biology Basics')).toBeInTheDocument()
    expect(screen.getByText('Showing 1–1 of 12 lectures')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Genetics Intro')).toBeInTheDocument()
    expect(getLectures).toHaveBeenLastCalledWith({ limit: 10, offset: 10 })
  })

  it('displays recent lectures on dashboard and pipeline stages on processing screen', async () => {
    getLectures.mockResolvedValueOnce({
      items: [
        {
          id: 'lec-proc',
          title: 'Signals Lecture',
          original_filename: 'signals.wav',
          media_type: 'audio/wav',
          file_size_bytes: 4096,
          duration_seconds: 180,
          status: 'processing',
          created_at: '2026-11-26T11:00:00Z',
        },
      ],
      total: 1,
      limit: 5,
      offset: 0,
    })

    const user = userEvent.setup()
    openRoute('/')

    expect(await screen.findByText('Signals Lecture')).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Processing' }))

    expect(await screen.findByRole('list', { name: 'Pipeline stages' })).toBeInTheDocument()
    expect(screen.getByText('Transcribe English-Telugu speech')).toBeInTheDocument()
  })
})
