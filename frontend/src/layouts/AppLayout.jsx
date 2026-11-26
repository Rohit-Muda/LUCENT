import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  clearAuthCredentials,
  hasAuthCredentials,
  notifyAuthRequired,
  setAuthCredentials,
  subscribeAuthState,
} from '../api/client'
import LucentLogo from '../components/LucentLogo'
import ThemeToggle from '../components/ThemeToggle'

function getPageContextLabel(pathname) {
  if (pathname === '/') return 'Overview'
  if (pathname.startsWith('/upload')) return 'Upload Lecture'
  if (pathname === '/lectures') return 'Lecture Library'
  if (pathname.includes('/processing')) return 'Processing Status'
  if (pathname.includes('/transcript')) return 'Transcript Viewer'
  if (pathname.includes('/notes')) return 'Structured Notes'
  if (pathname.includes('/explanations')) return 'Telugu Explanations'
  if (pathname.includes('/revision')) return 'Revision Points'
  if (pathname.includes('/quiz')) return 'MCQ Quiz'
  if (pathname.startsWith('/lectures/')) return 'Lecture Details'
  return 'Workspace'
}

export default function AppLayout({ theme, onToggleTheme }) {
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [authState, setAuthState] = useState(() => ({
    required: false,
    message: '',
    signedIn: hasAuthCredentials(),
  }))
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [formError, setFormError] = useState('')
  const [sessionGeneration, setSessionGeneration] = useState(0)

  useEffect(() => {
    return subscribeAuthState((nextState) => {
      setAuthState(nextState)
    })
  }, [])

  function handleSignIn(event) {
    event.preventDefault()
    if (!username.trim() || !password) {
      setFormError('Enter both username and password.')
      return
    }
    setFormError('')
    setAuthCredentials(username.trim(), password)
    setPassword('')
    setSessionGeneration((current) => current + 1)
  }

  function handleSignOut() {
    clearAuthCredentials()
    notifyAuthRequired('Signed out. Enter credentials to continue.')
    setSessionGeneration((current) => current + 1)
  }

  function closeSidebar() {
    setSidebarOpen(false)
  }

  const contextLabel = getPageContextLabel(location.pathname)

  return (
    <div className="app-shell">
      {sidebarOpen && (
        <div
          className="sidebar-backdrop"
          aria-hidden="true"
          onClick={closeSidebar}
        />
      )}

      <aside className={`app-sidebar ${sidebarOpen ? 'is-open' : ''}`}>
        <div className="sidebar-top">
          <div className="sidebar-brand-row">
            <Link className="brand" to="/" onClick={closeSidebar}>
              <LucentLogo />
            </Link>
            <button
              className="sidebar-close-btn"
              type="button"
              onClick={closeSidebar}
              aria-label="Close navigation menu"
            >
              ✕
            </button>
          </div>

          <div className="sidebar-motto">
            <p>&ldquo;Turn lectures into clarity&rdquo;</p>
          </div>

          <nav className="sidebar-nav" aria-label="Main navigation">
            <NavLink to="/" end onClick={closeSidebar}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="3" y="3" width="7" height="7" rx="1.5" />
                <rect x="14" y="3" width="7" height="7" rx="1.5" />
                <rect x="3" y="14" width="7" height="7" rx="1.5" />
                <rect x="14" y="14" width="7" height="7" rx="1.5" />
              </svg>
              <span>Dashboard</span>
            </NavLink>
            <NavLink to="/upload" onClick={closeSidebar}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="12" y1="18" x2="12" y2="12" />
                <polyline points="9 15 12 12 15 15" />
              </svg>
              <span>Upload lecture</span>
            </NavLink>
            <NavLink to="/lectures" onClick={closeSidebar}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
              <span>Lecture history</span>
            </NavLink>
          </nav>
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-archive-pill">
            <div>
              <strong>EN + TE Archive</strong>
              <span>Bilingual Study Notes</span>
            </div>
            <span className="status-dot" aria-hidden="true" />
          </div>
          <p className="sidebar-version">LUCENT Academic Workspace</p>
        </div>
      </aside>

      <div className="app-main-frame">
        <header className="topbar">
          <div className="topbar-context">
            <button
              className="sidebar-menu-btn"
              type="button"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open navigation menu"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
            <div className="topbar-breadcrumb">
              <span className="topbar-breadcrumb-root">LUCENT</span>
              <span className="topbar-breadcrumb-sep" aria-hidden="true">/</span>
              <span className="topbar-breadcrumb-current">{contextLabel}</span>
            </div>
          </div>

          <div className="topbar-actions">
            {authState.signedIn && (
              <button
                className="button button-small button-secondary"
                type="button"
                onClick={handleSignOut}
              >
                Sign out
              </button>
            )}
            <ThemeToggle theme={theme} onToggle={onToggleTheme} />
          </div>
        </header>

        <main className="page-content">
          {authState.required ? (
            <section className="upload-page" aria-label="Deployment authentication">
              <p className="eyebrow">ACCESS CONTROL</p>
              <h1>Sign in required</h1>
              <p className="page-intro">
                {authState.message || 'Enter deployment credentials to access lectures and study materials.'}
              </p>
              <form className="upload-card auth-form" onSubmit={handleSignIn}>
                <label className="auth-field" htmlFor="auth-username">
                  <span>Username</span>
                  <input
                    id="auth-username"
                    type="text"
                    autoComplete="username"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                  />
                </label>
                <label className="auth-field" htmlFor="auth-password">
                  <span>Password</span>
                  <input
                    id="auth-password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                </label>
                {formError && <p className="notice notice-error" role="alert">{formError}</p>}
                <button className="button button-primary" type="submit">
                  Sign in
                </button>
              </form>
            </section>
          ) : (
            <Outlet key={sessionGeneration} />
          )}
        </main>

        <footer className="app-footer">
          <p>
            LUCENT · English–Telugu Lecture Notes Generator · AI-assisted study material; verify key
            definitions against course sources.
          </p>
        </footer>
      </div>
    </div>
  )
}
