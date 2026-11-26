import { act, cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearAuthCredentials, hasAuthCredentials, notifyAuthRequired } from '../api/client'
import App from '../App'

vi.mock('../api/lectures', () => ({
  getLectures: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 }),
  getLecture: vi.fn(),
  getProcessingStatus: vi.fn(),
  getTranscript: vi.fn(),
  getNotes: vi.fn(),
  getExplanations: vi.fn(),
  getRevisionPoints: vi.fn(),
  getQuiz: vi.fn(),
  submitQuiz: vi.fn(),
  regenerateFeature: vi.fn(),
  retryProcessing: vi.fn(),
  uploadLecture: vi.fn(),
  downloadLecturePdf: vi.fn(),
  getPdfDownloadUrl: vi.fn((id) => `/api/lectures/${id}/pdf`),
}))

describe('AppLayout public deployment authentication gate', () => {
  afterEach(() => {
    cleanup()
    clearAuthCredentials()
    sessionStorage.clear()
    window.history.replaceState({}, '', '/')
  })

  it('prompts for credentials on 401, stores Basic token, and supports Sign out', async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(await screen.findByText('No lectures uploaded yet')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sign out' })).not.toBeInTheDocument()

    act(() => {
      notifyAuthRequired('Authentication is required.')
    })

    expect(await screen.findByRole('heading', { name: 'Sign in required' })).toBeInTheDocument()
    expect(screen.getByText('Authentication is required.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Enter both username and password.')

    await user.type(screen.getByLabelText('Username'), 'ops-user')
    await user.type(screen.getByLabelText('Password'), 'ops-secret')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(hasAuthCredentials()).toBe(true)
    expect(await screen.findByText('No lectures uploaded yet')).toBeInTheDocument()
    const signOutBtn = screen.getByRole('button', { name: 'Sign out' })

    await user.click(signOutBtn)
    expect(hasAuthCredentials()).toBe(false)
    expect(await screen.findByRole('heading', { name: 'Sign in required' })).toBeInTheDocument()
  })
})
