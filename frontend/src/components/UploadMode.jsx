import { useCallback, useEffect, useRef, useState } from 'react'

import { detectFile } from '../api'
import { DEFAULT_CONF } from '../config'
import { sampleUrl } from '../samples'
import { pct } from '../utils/format'
import { guessType, validateImageFile } from '../utils/validation'
import DetectionControls from './DetectionControls'
import DetectionList from './DetectionList'
import DetectionOverlay from './DetectionOverlay'
import ErrorBanner from './ErrorBanner'
import ImageDropzone from './ImageDropzone'
import ResultStats from './ResultStats'
import SampleGallery from './SampleGallery'

// Detection View, upload mode: pick an image, run detection, inspect the result.
export default function UploadMode() {
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [sampleName, setSampleName] = useState(null)
  const [settings, setSettings] = useState({ conf: DEFAULT_CONF, enhance: false })
  const [applied, setApplied] = useState(null) // settings used for the current result
  const [result, setResult] = useState(null)
  const [roundTripMs, setRoundTripMs] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [hovered, setHovered] = useState(null)
  const abortRef = useRef(null)

  // Cancel any in-flight request when leaving the page
  useEffect(() => () => abortRef.current?.abort(), [])

  // Release the preview's object URL when it is replaced or the page unmounts
  useEffect(() => () => previewUrl && URL.revokeObjectURL(previewUrl), [previewUrl])

  const runDetection = useCallback(async (imageFile, runSettings) => {
    abortRef.current?.abort() // newest request wins
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError(null)
    setHovered(null)
    const t0 = performance.now()
    try {
      const res = await detectFile(
        imageFile,
        { conf: runSettings.conf, enhance: runSettings.enhance, returnImage: false },
        { signal: controller.signal },
      )
      setResult(res)
      setApplied(runSettings)
      setRoundTripMs(performance.now() - t0)
    } catch (err) {
      if (err.name === 'AbortError') return
      setResult(null)
      setError(err.message)
    } finally {
      if (abortRef.current === controller) setLoading(false)
    }
  }, [])

  const handleFile = useCallback(
    (newFile, fromSample = null) => {
      const problem = validateImageFile(newFile)
      if (problem) {
        setError(problem) // keep the current image/result visible
        return
      }
      // Ensure a correct MIME type even when the OS didn't provide one
      const typed = newFile.type ? newFile : new File([newFile], newFile.name, { type: guessType(newFile) })
      setFile(typed)
      setSampleName(fromSample)
      setPreviewUrl(URL.createObjectURL(typed))
      setResult(null)
      runDetection(typed, settings)
    },
    [runDetection, settings],
  )

  const handleSample = async (name) => {
    setError(null)
    try {
      const res = await fetch(sampleUrl(name))
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      handleFile(new File([blob], name, { type: blob.type || 'image/jpeg' }), name)
    } catch (err) {
      setError(`Could not load sample "${name}" (${err.message}).`)
    }
  }

  const settingsChanged =
    applied != null && (applied.conf !== settings.conf || applied.enhance !== settings.enhance)

  return (
    <>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <div className="detection-layout">
        <aside className="panel side-panel">
          <ImageDropzone onFile={(f) => handleFile(f)} compact={file != null} />
          <DetectionControls
            settings={settings}
            onChange={setSettings}
            onRerun={() => runDetection(file, settings)}
            canRerun={file != null && settingsChanged && !loading}
            disabled={loading}
          />
          <SampleGallery onSelect={handleSample} selected={sampleName} disabled={loading} />
        </aside>

        <div className="result-area">
          {!file && (
            <div className="panel placeholder">
              <p>Choose an image or a sample to start.</p>
            </div>
          )}

          {file && (
            <div className="panel viewer" aria-busy={loading}>
              <div className="viewer-head">
                <span className="file-name" title={file.name}>{file.name}</span>
                {applied && result && (
                  <span className="muted small">
                    threshold {pct(applied.conf)}
                    {applied.enhance ? ' · contrast boost' : ''}
                    {result.record_id != null ? ` · saved as #${result.record_id}` : ''}
                  </span>
                )}
              </div>
              <div className="viewer-body">
                <DetectionOverlay
                  src={previewUrl}
                  alt={file.name}
                  width={result?.image_width}
                  height={result?.image_height}
                  detections={result?.detections}
                  hovered={hovered}
                  onHover={setHovered}
                />
                {loading && (
                  <div className="loading-overlay" role="status">
                    <span className="spinner" aria-hidden="true" />
                    Detecting people…
                  </div>
                )}
              </div>
            </div>
          )}

          {result && (
            <>
              <ResultStats result={result} roundTripMs={roundTripMs} />
              <div className="panel">
                <h2>Detected people</h2>
                <DetectionList detections={result.detections} hovered={hovered} onHover={setHovered} />
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )
}
