import { lazy, Suspense, useState } from 'react'

import UploadMode from '../components/UploadMode'
import WebcamMode from '../components/WebcamMode'

// Video mode pulls in the chart library; load it only when the tab is opened
const VideoMode = lazy(() => import('../components/video/VideoMode'))

const MODES = [
  { id: 'upload', label: 'Image' },
  { id: 'webcam', label: 'Webcam' },
  { id: 'video', label: 'Video' },
]

// Detection View: switch between image upload, live webcam and video analysis.
// Switching unmounts the other modes, which releases the camera and cancels
// unfinished video work.
export default function DetectionPage() {
  const [mode, setMode] = useState('upload')

  return (
    <section className="detection-page">
      <header className="page-header page-header-row">
        <div>
          <h1>Detection</h1>
          <p className="muted">Count people in an image, live from the webcam, or through a video.</p>
        </div>
        <div className="segmented" role="tablist" aria-label="Input source">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              role="tab"
              id={`tab-${m.id}`}
              aria-selected={mode === m.id}
              aria-controls={`panel-${m.id}`}
              className={mode === m.id ? 'active' : undefined}
              onClick={() => setMode(m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>
      </header>

      <div role="tabpanel" id={`panel-${mode}`} aria-labelledby={`tab-${mode}`}>
        {mode === 'upload' && <UploadMode />}
        {mode === 'webcam' && <WebcamMode />}
        {mode === 'video' && (
          <Suspense fallback={<p className="muted">Loading video analysis…</p>}>
            <VideoMode />
          </Suspense>
        )}
      </div>
    </section>
  )
}
