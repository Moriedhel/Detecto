import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import Layout from './components/Layout'
import DetectionPage from './pages/DetectionPage'

// History pulls in the chart library; load it only when the page is opened
const HistoryPage = lazy(() => import('./pages/HistoryPage'))

// Top-level routes. The router itself is provided by main.jsx (or by tests).
export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DetectionPage />} />
        <Route
          path="history"
          element={
            <Suspense fallback={<p className="muted">Loading history…</p>}>
              <HistoryPage />
            </Suspense>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
