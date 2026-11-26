import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import useTheme from './hooks/useTheme'
import AppLayout from './layouts/AppLayout'
import LectureDetailsLayout from './layouts/LectureDetailsLayout'
import DashboardPage from './pages/DashboardPage'
import ExplanationsPage from './pages/ExplanationsPage'
import HistoryPage from './pages/HistoryPage'
import LectureDetailsPage from './pages/LectureDetailsPage'
import NotesPage from './pages/NotesPage'
import ProcessingPage from './pages/ProcessingPage'
import QuizPage from './pages/QuizPage'
import RevisionPointsPage from './pages/RevisionPointsPage'
import TranscriptPage from './pages/TranscriptPage'
import UploadPage from './pages/UploadPage'
import './App.css'

function NotFoundPage() {
  return (
    <section className="empty-state">
      <h1>Page not found</h1>
      <p>The requested page could not be found.</p>
      <Link className="button button-primary" to="/">
        Return to dashboard
      </Link>
    </section>
  )
}

export default function App() {
  const { theme, toggleTheme } = useTheme()

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout theme={theme} onToggleTheme={toggleTheme} />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/lectures" element={<HistoryPage />} />
          <Route path="/lectures/:lectureId" element={<LectureDetailsLayout />}>
            <Route index element={<LectureDetailsPage />} />
            <Route path="processing" element={<ProcessingPage />} />
            <Route path="transcript" element={<TranscriptPage />} />
            <Route path="notes" element={<NotesPage />} />
            <Route path="explanations" element={<ExplanationsPage />} />
            <Route path="revision" element={<RevisionPointsPage />} />
            <Route path="quiz" element={<QuizPage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
