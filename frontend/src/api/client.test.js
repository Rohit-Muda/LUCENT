import { afterEach, describe, expect, it, vi } from 'vitest'
import apiClient, {
  clearAuthCredentials,
  encodeBasicCredentials,
  hasAuthCredentials,
  setAuthCredentials,
  subscribeAuthState,
} from './client'

describe('apiClient authentication handling', () => {
  afterEach(() => {
    clearAuthCredentials()
    sessionStorage.clear()
    delete apiClient.defaults.adapter
  })

  it('attaches Basic auth header when credentials are set and clears it on sign out', async () => {
    setAuthCredentials('student', 'pass-123')
    expect(hasAuthCredentials()).toBe(true)

    const adapter = vi.fn(async (config) => ({
      data: { ok: true },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    }))
    apiClient.defaults.adapter = adapter

    await apiClient.get('/lectures')
    expect(adapter).toHaveBeenCalledTimes(1)
    expect(adapter.mock.calls[0][0].headers.Authorization).toBe(
      encodeBasicCredentials('student', 'pass-123'),
    )

    clearAuthCredentials()
    expect(hasAuthCredentials()).toBe(false)
    await apiClient.get('/lectures')
    expect(adapter.mock.calls[1][0].headers.Authorization).toBeUndefined()
  })

  it('clears credentials and notifies subscribers when backend returns 401', async () => {
    setAuthCredentials('student', 'bad-pass')
    const events = []
    const unsubscribe = subscribeAuthState((snapshot) => events.push(snapshot))

    apiClient.defaults.adapter = async (config) =>
      Promise.reject({
        config,
        response: {
          status: 401,
          data: { error: { code: 'authentication_failed', message: 'Invalid credentials.' } },
        },
      })

    await expect(apiClient.get('/lectures')).rejects.toBeTruthy()
    unsubscribe()

    expect(hasAuthCredentials()).toBe(false)
    expect(events).toContainEqual({
      required: true,
      message: 'Invalid credentials.',
      signedIn: false,
    })
  })
})
