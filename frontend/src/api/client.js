import axios from 'axios'

const AUTH_STORAGE_KEY = 'cm_notes_basic_auth'
const authListeners = new Set()
let authRequiredMessage = ''

function readStorage() {
  if (typeof window === 'undefined') return ''
  try {
    return window.sessionStorage.getItem(AUTH_STORAGE_KEY) || ''
  } catch {
    return ''
  }
}

function writeStorage(value) {
  if (typeof window === 'undefined') return
  try {
    if (value) {
      window.sessionStorage.setItem(AUTH_STORAGE_KEY, value)
    } else {
      window.sessionStorage.removeItem(AUTH_STORAGE_KEY)
    }
  } catch {
    /* ignore restricted storage environments */
  }
}

export function encodeBasicCredentials(username, password) {
  const bytes = new TextEncoder().encode(`${username}:${password}`)
  let binary = ''
  for (const byte of bytes) {
    binary += String.fromCharCode(byte)
  }
  return `Basic ${btoa(binary)}`
}

export function hasAuthCredentials() {
  return Boolean(readStorage())
}

function emitAuthState(required, message = '') {
  authRequiredMessage = required ? message : ''
  const snapshot = {
    required,
    message: authRequiredMessage,
    signedIn: hasAuthCredentials(),
  }
  for (const listener of authListeners) {
    listener(snapshot)
  }
}

export function setAuthCredentials(username, password) {
  const token = encodeBasicCredentials(username, password)
  writeStorage(token)
  emitAuthState(false, '')
}

export function clearAuthCredentials() {
  writeStorage('')
  emitAuthState(false, '')
}

export function notifyAuthRequired(message = 'Authentication is required.') {
  writeStorage('')
  emitAuthState(true, message)
}

export function subscribeAuthState(listener) {
  authListeners.add(listener)
  return () => {
    authListeners.delete(listener)
  }
}

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000,
})

apiClient.interceptors.request.use((config) => {
  const token = readStorage()
  if (token && !config.headers?.Authorization) {
    config.headers = config.headers || {}
    config.headers.Authorization = token
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      const message =
        error?.response?.data?.error?.message || 'Sign in to access this deployment.'
      notifyAuthRequired(message)
    }
    return Promise.reject(error)
  },
)

export default apiClient
