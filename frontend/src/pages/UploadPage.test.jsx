import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import UploadPage from './UploadPage'

vi.mock('../api/lectures', () => ({
  uploadLecture: vi.fn(),
}))

import { uploadLecture } from '../api/lectures'

function renderUploadPage() {
  return render(
    <MemoryRouter>
      <UploadPage />
    </MemoryRouter>,
  )
}

describe('UploadPage', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows selected filename and size before upload', async () => {
    renderUploadPage()
    const file = new File([new Uint8Array([1, 2, 3])], 'lecture.wav', { type: 'audio/wav' })

    fireEvent.change(screen.getByLabelText(/Select a lecture recording/), {
      target: { files: [file] },
    })

    expect(screen.getByText('lecture.wav')).toBeInTheDocument()
    expect(screen.getByText('3 B')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upload lecture' })).toBeEnabled()
  })

  it('rejects unsupported extensions before making an API request', async () => {
    renderUploadPage()
    const file = new File(['not audio'], 'notes.txt', { type: 'text/plain' })

    fireEvent.change(screen.getByLabelText(/Select a lecture recording/), {
      target: { files: [file] },
    })

    expect(await screen.findByRole('alert')).toHaveTextContent('Choose an MP3 or WAV audio file.')
    expect(uploadLecture).not.toHaveBeenCalled()
  })

  it('rejects empty files before making an API request', async () => {
    const user = userEvent.setup()
    renderUploadPage()
    const file = new File([], 'empty.wav', { type: 'audio/wav' })

    await user.upload(screen.getByLabelText(/Select a lecture recording/), file)

    expect(screen.getByRole('alert')).toHaveTextContent('The selected file is empty.')
    expect(uploadLecture).not.toHaveBeenCalled()
  })

  it('uploads once, reports progress, and shows the saved lecture link', async () => {
    let finishUpload
    uploadLecture.mockImplementation((_file, onUploadProgress) => {
      onUploadProgress({ loaded: 50, total: 100 })
      return new Promise((resolve) => {
        finishUpload = resolve
      })
    })
    const user = userEvent.setup()
    renderUploadPage()
    const file = new File([new Uint8Array([1, 2, 3])], 'lecture.mp3', { type: 'audio/mpeg' })
    await user.upload(screen.getByLabelText(/Select a lecture recording/), file)
    const button = screen.getByRole('button', { name: 'Upload lecture' })

    await user.click(button)

    expect(uploadLecture).toHaveBeenCalledTimes(1)
    expect(uploadLecture).toHaveBeenCalledWith(file, expect.any(Function))
    expect(await screen.findByText('50%')).toBeInTheDocument()
    expect(button).toBeDisabled()

    await user.click(button)
    expect(uploadLecture).toHaveBeenCalledTimes(1)

    finishUpload({ id: 'lecture-123' })
    expect(await screen.findByRole('status')).toHaveTextContent('Lecture uploaded.')
    expect(screen.getByRole('link', { name: 'View lecture details' })).toHaveAttribute(
      'href',
      '/lectures/lecture-123',
    )
  })

  it('shows the backend error message and permits retry', async () => {
    uploadLecture.mockRejectedValueOnce({
      response: { data: { error: { message: 'Audio file is not readable.' } } },
    })
    const user = userEvent.setup()
    renderUploadPage()
    const file = new File([new Uint8Array([1])], 'lecture.wav', { type: 'audio/wav' })
    await user.upload(screen.getByLabelText(/Select a lecture recording/), file)

    await user.click(screen.getByRole('button', { name: 'Upload lecture' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Audio file is not readable.')
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Upload lecture' })).toBeEnabled()
    })
  })

  it('shows progress for a pending upload without reporting a fake percentage', async () => {
    let finishUpload
    uploadLecture.mockImplementation((_file, onUploadProgress) => {
      onUploadProgress({ loaded: 10 })
      return new Promise((resolve) => {
        finishUpload = resolve
      })
    })
    const user = userEvent.setup()
    renderUploadPage()
    const file = new File([new Uint8Array([1])], 'lecture.wav', { type: 'audio/wav' })
    await user.upload(screen.getByLabelText(/Select a lecture recording/), file)

    await user.click(screen.getByRole('button', { name: 'Upload lecture' }))

    expect(await screen.findByText('Starting upload...')).toBeInTheDocument()
    finishUpload({ id: 'lecture-456' })
  })

  it('prevents default form navigation on submission', async () => {
    const user = userEvent.setup()
    renderUploadPage()
    const file = new File([new Uint8Array([1])], 'lecture.wav', { type: 'audio/wav' })
    await user.upload(screen.getByLabelText(/Select a lecture recording/), file)
    uploadLecture.mockResolvedValue({ id: 'lecture-789' })

    fireEvent.submit(screen.getByRole('button', { name: 'Upload lecture' }).closest('form'))

    expect(await screen.findByRole('status')).toHaveTextContent('Lecture uploaded.')
  })
})
