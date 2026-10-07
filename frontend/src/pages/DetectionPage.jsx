import { useState } from 'react'

import UploadMode from '../components/UploadMode'
import WebcamMode from '../components/WebcamMode'

const MODES = [
  { id: 'upload', label: 'Upload' },
  { id: 'webcam', label: 'Webcam' },
]

// Detection View: switch between image upload and live webcam detection.
// Switching unmounts the other mode, which also releases the camera.
export default function DetectionPage() {
  const [mode, setMode] = useState('upload')

  return (
    <section className="detection-page">
      <header className="page-header page-header-row">
        <div>
          <h1>Detection</h1>
          <p className="muted">Upload an image or use the webcam to count people.</p>
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
        {mode === 'upload' ? <UploadMode /> : <WebcamMode />}
      </div>
    </section>
  )
}
