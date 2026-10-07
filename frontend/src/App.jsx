import { Navigate, Route, Routes } from 'react-router-dom'

import Layout from './components/Layout'
import DetectionPage from './pages/DetectionPage'
import HistoryPage from './pages/HistoryPage'

// Top-level routes. The router itself is provided by main.jsx (or by tests).
export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DetectionPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
