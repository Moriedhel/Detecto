import { useEffect, useRef, useState } from 'react'

import { detectBase64 } from '../api'
import { DEFAULT_CONF } from '../config'
import useCamera from '../hooks/useCamera'
import useElementWidth from '../hooks/useElementWidth'
import { captureFrame } from '../utils/capture'
import { ms, pct } from '../utils/format'
import { createSavePolicy, DEFAULT_SAVE_PRESET, SAVE_PRESETS } from '../utils/savePolicy'
import BoxLayer from './BoxLayer'
import DetectionControls from './DetectionControls'
import DetectionList from './DetectionList'
import ErrorBanner from './ErrorBanner'

export const LIVE_IMG_SIZE = 640 // model input + capture width for live frames (~3x faster than 1280)
const MIN_FRAME_MS = 100 // cap at ~10 fps to leave CPU for the rest of the machine
const HIDDEN_POLL_MS = 500 // check interval while the tab is hidden

const sleep = (t) => new Promise((r) => setTimeout(r, t))

// Detection View, webcam mode: live detection on camera frames.
export default function WebcamMode() {
  const cam = useCamera()
  const displayWidth = useElementWidth(cam.videoRef, cam.status)

  const [settings, setSettings] = useState({ conf: DEFAULT_CONF, enhance: false })
  const [preset, setPreset] = useState(DEFAULT_SAVE_PRESET)
  const [frame, setFrame] = useState(null) // latest detection result
  const [perf, setPerf] = useState({ fps: null, latency: null })
  const [saved, setSaved] = useState({ count: 0, lastId: null, lastAt: null })
  const [error, setError] = useState(null)
  const [hovered, setHovered] = useState(null)

  // The loop reads current settings without restarting
  const settingsRef = useRef(settings)
  useEffect(() => {
    settingsRef.current = settings
  }, [settings])

  const live = cam.status === 'live'

  // Capture -> detect -> draw loop. Sends the next frame only after the previous
  // result arrives, so requests never pile up and boxes are never stale by more than one frame.
  useEffect(() => {
    if (!live) return undefined
    let cancelled = false
    let controller = null
    const policy = createSavePolicy(SAVE_PRESETS[preset])
    let ema = null
    let lastDone = performance.now()

    const handleResult = (res, t0) => {
      policy.observe(res.count)
      if (res.saved) {
        policy.markSaved(Date.now(), res.count)
        setSaved((s) => ({ count: s.count + 1, lastId: res.record_id, lastAt: new Date() }))
      }
      const now = performance.now()
      ema = ema == null ? now - lastDone : ema * 0.8 + (now - lastDone) * 0.2 // smoothed frame interval
      lastDone = now
      setFrame(res)
      setPerf({ fps: 1000 / ema, latency: now - t0 })
    }

    // Process one frame; returns the delay (ms) before the next one, or null to stop.
    const runFrame = async () => {
      if (document.hidden) return HIDDEN_POLL_MS // pause while the tab is in the background
      const t0 = performance.now()
      const shot = captureFrame(cam.videoRef.current, LIVE_IMG_SIZE)
      if (!shot) return MIN_FRAME_MS // video has no frame yet

      const save = policy.shouldSave(Date.now())
      const { conf, enhance } = settingsRef.current
      controller = new AbortController()
      const res = await detectBase64(
        shot.dataUrl,
        { source: 'webcam', imgSize: LIVE_IMG_SIZE, returnImage: false, save, conf, enhance },
        { signal: controller.signal },
      )
      if (cancelled) return null
      handleResult(res, t0)
      return Math.max(0, MIN_FRAME_MS - (performance.now() - t0))
    }

    const loop = async () => {
      while (!cancelled) {
        let wait
        try {
          wait = await runFrame() // frames are processed strictly one after another
        } catch (err) {
          if (!cancelled && err.name !== 'AbortError') {
            setError(`Live detection stopped: ${err.message}`)
            cam.stop()
          }
          return
        }
        if (wait == null) return
        if (wait > 0) await sleep(wait)
      }
    }

    void loop()
    return () => {
      cancelled = true
      controller?.abort()
    }
    // cam.videoRef and cam.stop are stable, so they are not dependencies
  }, [live, preset])

  const start = async (deviceId) => {
    setError(null)
    setFrame(null)
    setPerf({ fps: null, latency: null })
    await cam.start(deviceId)
  }

  const stop = () => {
    cam.stop()
    setFrame(null)
    setHovered(null)
  }

  const shownError = error || cam.error

  return (
    <>
      <ErrorBanner message={shownError} onDismiss={() => setError(null)} />

      <div className="detection-layout">
        <aside className="panel side-panel">
          <div className="webcam-actions">
            {live ? (
              <button type="button" className="button" onClick={stop}>Stop camera</button>
            ) : (
              <button
                type="button"
                className="button primary"
                onClick={() => start(cam.deviceId)}
                disabled={cam.status === 'starting'}
              >
                {cam.status === 'starting' ? 'Starting camera…' : 'Start camera'}
              </button>
            )}
          </div>

          {cam.devices.length > 1 && (
            <label className="control">
              <span>Camera</span>
              <select
                value={cam.deviceId ?? ''}
                onChange={(e) => start(e.target.value)}
                disabled={cam.status === 'starting'}
              >
                {cam.devices.map((d, i) => (
                  <option key={d.deviceId} value={d.deviceId}>{d.label || `Camera ${i + 1}`}</option>
                ))}
              </select>
            </label>
          )}

          <DetectionControls settings={settings} onChange={setSettings} canRerun={false} />

          <label className="control">
            <span>Save to history</span>
            <select value={preset} onChange={(e) => setPreset(e.target.value)}>
              {Object.entries(SAVE_PRESETS).map(([key, p]) => (
                <option key={key} value={key}>{p.label}</option>
              ))}
            </select>
            <span className="hint">
              Live frames are analysed at {LIVE_IMG_SIZE} px for speed. Only selected frames are stored.
            </span>
          </label>
        </aside>

        <div className="result-area">
          <div className="panel viewer">
            <div className="viewer-head">
              <span className="file-name">
                {live ? <><span className="live-dot" aria-hidden="true" /> Live</> : 'Camera'}
              </span>
              {live && frame && (
                <span className="muted small">threshold {pct(settings.conf)} · {frame.image_width}×{frame.image_height}</span>
              )}
            </div>
            <div className="viewer-body">
              <div className={`overlay${live ? '' : ' hidden-video'}`}>
                <video ref={cam.videoRef} muted playsInline aria-label="Camera preview" />
                {live && frame && (
                  <BoxLayer
                    width={frame.image_width}
                    height={frame.image_height}
                    detections={frame.detections}
                    hovered={hovered}
                    onHover={setHovered}
                    displayWidth={displayWidth}
                  />
                )}
              </div>
              {!live && (
                <p className="muted camera-off">
                  {cam.status === 'starting' ? 'Waiting for camera permission…' : 'Camera is off.'}
                </p>
              )}
            </div>
          </div>

          {live && (
            <dl className="stats">
              <div className="stat stat-main">
                <dt>People</dt>
                <dd data-testid="live-count">{frame ? frame.count : '–'}</dd>
              </div>
              <div className="stat">
                <dt>Avg confidence</dt>
                <dd>{pct(frame?.avg_confidence)}</dd>
              </div>
              <div className="stat">
                <dt>Frame rate</dt>
                <dd data-testid="live-fps">{perf.fps ? `${perf.fps.toFixed(1)} fps` : '–'}</dd>
              </div>
              <div className="stat">
                <dt>Per frame</dt>
                <dd title="Capture + upload + detection + response, measured in the browser">{ms(perf.latency)}</dd>
              </div>
              <div className="stat">
                <dt>Inference</dt>
                <dd>{ms(frame?.timings.inference_ms)}</dd>
              </div>
              <div className="stat">
                <dt>Saved</dt>
                <dd data-testid="live-saved" title={saved.lastAt ? `Last saved ${saved.lastAt.toLocaleTimeString()} as #${saved.lastId}` : 'Nothing saved yet'}>
                  {saved.count}
                </dd>
              </div>
            </dl>
          )}

          {live && frame && (
            <div className="panel">
              <h2>Detected people</h2>
              <DetectionList detections={frame.detections} hovered={hovered} onHover={setHovered} />
            </div>
          )}
        </div>
      </div>
    </>
  )
}
