import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

vi.mock('../api/lectures', () => ({
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
  regenerateFeature,
  retryProcessing,
  submitQuiz,
} from '../api/lectures'

const completedLecture = {
  id: 'lec-done',
  title: 'Thermodynamics Lecture 1',
  original_filename: 'thermo.mp3',
  media_type: 'audio/mpeg',
  file_size_bytes: 1_500_000,
  duration_seconds: 600,
  status: 'completed',
  created_at: '2026-11-26T08:30:00Z',
}

const completedStatus = {
  id: 'job-done',
  status: 'completed',
  current_stage: null,
  last_successful_stage: 'generate_pdf',
  retry_count: 0,
  attempts_by_stage: {
    validate_upload: 1,
    transcribe: 1,
    generate_notes: 1,
    generate_explanations: 1,
    generate_revision_points: 1,
    generate_quiz: 1,
    generate_pdf: 1,
  },
  manual_retry_count: 0,
  last_error: null,
  can_retry: false,
}

const savedNotes = {
  lecture_id: 'lec-done',
  updated_at: '2026-11-26T08:40:00Z',
  content: {
    title: 'First Law of Thermodynamics',
    sections: [
      {
        heading: 'Energy Conservation',
        summary: 'Energy cannot be created or destroyed.',
        key_points: ['Internal energy changes with heat and work', 'Delta U equals Q minus W'],
        source_excerpt: 'Energy cannot be created or destroyed in an isolated system.',
      },
    ],
    concepts: [
      { name: 'Internal Energy', source_excerpt: 'Internal energy changes with heat and work' },
    ],
  },
}

const savedExplanations = [
  {
    id: 'exp-1',
    position: 0,
    concept: 'Internal Energy',
    source_excerpt: 'Internal energy changes with heat and work',
    explanation_telugu: 'అంతర్గత శక్తి అంటే వ్యవస్థలోని కణాల మొత్తం శక్తి.',
    updated_at: '2026-11-26T08:41:00Z',
  },
]

const savedRevisionPoints = [
  {
    id: 'rev-1',
    position: 0,
    content: 'First law relates internal energy change to heat added and work done.',
    source_excerpt: 'Energy cannot be created or destroyed in an isolated system.',
    updated_at: '2026-11-26T08:42:00Z',
  },
]

const savedQuiz = {
  lecture_id: 'lec-done',
  questions: [
    {
      id: 'q-1',
      position: 0,
      prompt: 'What does the first law state?',
      options: [
        { id: 'o-1', position: 0, content: 'Energy is conserved' },
        { id: 'o-2', position: 1, content: 'Entropy decreases always' },
        { id: 'o-3', position: 2, content: 'Work equals zero' },
        { id: 'o-4', position: 3, content: 'Heat cannot transfer' },
      ],
    },
    {
      id: 'q-2',
      position: 1,
      prompt: 'What changes internal energy?',
      options: [
        { id: 'o-5', position: 0, content: 'Color alone' },
        { id: 'o-6', position: 1, content: 'Heat and work' },
        { id: 'o-7', position: 2, content: 'Mass loss only' },
        { id: 'o-8', position: 3, content: 'None of these' },
      ],
    },
  ],
}

describe('Study workspace, quiz, PDF, and saved-output reuse', () => {
  afterEach(() => {
    cleanup()
    window.history.replaceState({}, '', '/')
  })

  beforeEach(() => {
    vi.clearAllMocks()
    getLecture.mockResolvedValue(completedLecture)
    getLectures.mockResolvedValue({
      items: [completedLecture],
      total: 1,
      limit: 10,
      offset: 0,
    })
    getProcessingStatus.mockResolvedValue(completedStatus)
    getTranscript.mockResolvedValue({
      id: 'tr-1',
      lecture_id: 'lec-done',
      provider: 'groq',
      detected_language: 'telugu',
      cleaned_text: 'Energy cannot be created or destroyed.',
      original_text: 'Energy cannot be created or destroyed.',
      segments: [{ start: 0, end: 5, text: 'Energy cannot be created or destroyed.' }],
    })
    getNotes.mockResolvedValue(savedNotes)
    getExplanations.mockResolvedValue(savedExplanations)
    getRevisionPoints.mockResolvedValue(savedRevisionPoints)
    getQuiz.mockResolvedValue(savedQuiz)
    downloadLecturePdf.mockResolvedValue({ filename: 'thermo.pdf' })
    submitQuiz.mockResolvedValue({
      lecture_id: 'lec-done',
      score: 1,
      total_questions: 2,
      answers: [
        {
          question_id: 'q-1',
          selected_option_position: 0,
          correct_option_position: 0,
          is_correct: true,
          explanation: 'First law states energy conservation.',
        },
        {
          question_id: 'q-2',
          selected_option_position: 0,
          correct_option_position: 1,
          is_correct: false,
          explanation: 'Both heat and work change internal energy.',
        },
      ],
    })
  })

  it('reopens completed outputs across tabs without duplicating AI calls or re-fetching cached tabs', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/lectures/lec-done')
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Thermodynamics Lecture 1' })).toBeInTheDocument()
    expect(await screen.findByRole('region', { name: 'Lecture transcript' })).toBeInTheDocument()

    // Navigate to Notes
    await user.click(screen.getByRole('link', { name: 'Notes' }))
    expect(await screen.findByRole('heading', { name: 'First Law of Thermodynamics' })).toBeInTheDocument()
    expect(screen.getByText('Internal energy changes with heat and work')).toBeInTheDocument()

    // Navigate to Telugu Explanations
    await user.click(screen.getByRole('link', { name: 'Telugu explanations' }))
    expect(
      await screen.findByText('అంతర్గత శక్తి అంటే వ్యవస్థలోని కణాల మొత్తం శక్తి.'),
    ).toBeInTheDocument()

    // Navigate to Revision Points
    await user.click(screen.getByRole('link', { name: 'Revision points' }))
    expect(
      await screen.findByText('First law relates internal energy change to heat added and work done.'),
    ).toBeInTheDocument()

    // Switch back to Notes -> must reuse cached notes without another GET request
    await user.click(screen.getByRole('link', { name: 'Notes' }))
    expect(await screen.findByRole('heading', { name: 'First Law of Thermodynamics' })).toBeInTheDocument()

    // Trigger PDF download
    await user.click(screen.getByRole('button', { name: 'Download PDF' }))
    await waitFor(() => {
      expect(downloadLecturePdf).toHaveBeenCalledWith('lec-done')
    })

    // Critical reopening assertions: zero AI regeneration/retry calls and each GET called once
    expect(regenerateFeature).not.toHaveBeenCalled()
    expect(retryProcessing).not.toHaveBeenCalled()
    expect(getTranscript).toHaveBeenCalledTimes(1)
    expect(getNotes).toHaveBeenCalledTimes(1)
    expect(getExplanations).toHaveBeenCalledTimes(1)
    expect(getRevisionPoints).toHaveBeenCalledTimes(1)
  })

  it('keeps quiz answers hidden until submission and grades answers on submit', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/lectures/lec-done/quiz')
    render(<App />)

    expect(await screen.findByText(/What does the first law state/)).toBeInTheDocument()
    expect(screen.queryByText('First law states energy conservation.')).not.toBeInTheDocument()
    expect(screen.queryByText(/Score:/)).not.toBeInTheDocument()

    const submitButton = screen.getByRole('button', { name: 'Submit quiz' })
    expect(submitButton).toBeDisabled()

    await user.click(screen.getByLabelText('Energy is conserved'))
    expect(submitButton).toBeDisabled()

    await user.click(screen.getByLabelText('Color alone'))
    expect(submitButton).toBeEnabled()

    await user.click(submitButton)

    expect(await screen.findByText('Score: 1 / 2')).toBeInTheDocument()
    expect(screen.getByText('First law states energy conservation.')).toBeInTheDocument()
    expect(screen.getByText('Both heat and work change internal energy.')).toBeInTheDocument()
    expect(submitQuiz).toHaveBeenCalledWith('lec-done', [
      { question_id: 'q-1', selected_option_position: 0 },
      { question_id: 'q-2', selected_option_position: 0 },
    ])

    await user.click(screen.getByRole('button', { name: 'Retake quiz' }))
    expect(screen.queryByText(/Score:/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Submit quiz' })).toBeDisabled()
  })

  it('handles partially generated / unavailable outputs gracefully', async () => {
    getNotes.mockRejectedValueOnce({ response: { status: 404 } })
    window.history.replaceState({}, '', '/lectures/lec-done/notes')
    render(<App />)

    expect(await screen.findByText('Study notes not yet available')).toBeInTheDocument()
    expect(screen.getByText('Study notes have not been generated yet.')).toBeInTheDocument()
  })

  it('restores saved dark theme preference on load and opens dedicated transcript route', async () => {
    localStorage.setItem('theme', 'dark')
    window.history.replaceState({}, '', '/lectures/lec-done/transcript')
    render(<App />)

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    const region = await screen.findByRole('region', { name: 'Lecture transcript' })
    expect(region).toHaveTextContent('Energy cannot be created or destroyed.')
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })
})
