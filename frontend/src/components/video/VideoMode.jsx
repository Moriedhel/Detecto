import { useCallback, useEffect, useRef, useState } from 'react'

import { DEFAULT_CONF } from '../../config'
import useVideoJob from '../../hooks/useVideoJob'
import { clock, duration, ms, pct } from '../../utils/format'
import ErrorBanner from '../ErrorBanner'
import VideoPlayer from './VideoPlayer'
import VideoTimeline from './VideoTimeline'

const MAX_VIDEO_MB = Number(import.meta.env.VITE_MAX_VIDEO_MB || 200)
const VIDEO_EXT = ['mp4', 'm4v', 'webm', 'mov', 'avi', 'mkv']

export function validateVideoFile(file) {
  if (!file) return 'No file selected.'
  if (file.size === 0) return `"${file.name}" is empty.`
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!file.type.startsWith('video/') && !VIDEO_EXT.includes(ext)) {
    return `"${file.name}" is not a video. Use MP4, WebM, MOV, AVI or MKV.`
  }
  if (file.size > MAX_VIDEO_MB * 1024 * 1024) {
    return `"${file.name}" is ${(file.size / 1024 / 1024).toFixed(0)} MB; the limit is ${MAX_VIDEO_MB} MB.`
  }
  return null
}

const PHASE_LABEL = {
  uploading: 'Uploading',
  processing: 'Analysing',
}

// Detection View, video mode: track people through an uploaded video.
export default function VideoMode() {
  const job = useVideoJob()
  const [file, setFile] = useState(null)
  const [url, setUrl] = useState(null)
  const [options, setOptions] = useState({ sampleFps: 10, imgSize: 640, conf: DEFAULT_CONF, enhance: false })
  const [localError, setLocalError] = useState(null)
  const [highlightId, setHighlightId] = useState(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [dragging, setDragging] = useState(false)
  const playerRef = useRef(null)

  useEffect(() => () => url && URL.revokeObjectURL(url), [url])

  const choose = (f) => {
    const problem = validateVideoFile(f)
    if (problem) {
      setLocalError(problem)
      return
    }
    setLocalError(null)
    job.reset()
    setHighlightId(null)
    setFile(f)
    setUrl(URL.createObjectURL(f))
  }

  const busy = job.phase === 'uploading' || job.phase === 'processing'
  const result = job.phase === 'done' ? job.job?.result : null
  const onTime = useCallback((t) => setCurrentTime(t), [])
  const seek = (t) => playerRef.current?.seek(t)

  return (
    <>
      <ErrorBanner message={localError || job.error} onDismiss={() => setLocalError(null)} />

      <div className="detection-layout">
        <aside className="panel side-panel">
          <label
            className={`dropzone${file ? ' compact' : ''}${dragging ? ' dragging' : ''}${busy ? ' disabled' : ''}`}
            onDragOver={(e) => {
              e.preventDefault()
              if (!busy) setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              if (!busy && e.dataTransfer.files[0]) choose(e.dataTransfer.files[0])
            }}
          >
            <input
              type="file"
              className="visually-hidden"
              accept="video/*"
              disabled={busy}
              aria-label="Choose a video"
              onChange={(e) => {
                if (e.target.files[0]) choose(e.target.files[0])
                e.target.value = ''
              }}
            />
            <span className="dropzone-title">{file ? 'Choose another video' : 'Drop a video here'}</span>
            {!file && <span className="dropzone-hint">or click to browse · MP4, WebM, MOV · up to {MAX_VIDEO_MB} MB</span>}
          </label>

          <fieldset className="controls" disabled={busy}>
            <legend>Analysis settings</legend>
            <label className="control">
              <span>Frames analysed per second</span>
              <select value={options.sampleFps} onChange={(e) => setOptions({ ...options, sampleFps: Number(e.target.value) })}>
                <option value={5}>5 (faster)</option>
                <option value={10}>10 (recommended)</option>
                <option value={15}>15 (smoother tracking)</option>
              </select>
            </label>
            <label className="control">
              <span>Model input size</span>
              <select value={options.imgSize} onChange={(e) => setOptions({ ...options, imgSize: Number(e.target.value) })}>
                <option value={640}>640 px (fast)</option>
                <option value={1280}>1280 px (small people, ~3× slower)</option>
              </select>
            </label>
            <label className="control">
              <span className="control-row">
                <span>Confidence threshold</span>
                <output>{pct(options.conf)}</output>
              </span>
              <input
                type="range" min="0.1" max="0.9" step="0.05" value={options.conf}
                onChange={(e) => setOptions({ ...options, conf: Number(e.target.value) })}
              />
            </label>
            <label className="control checkbox">
              <input type="checkbox" checked={options.enhance} onChange={(e) => setOptions({ ...options, enhance: e.target.checked })} />
              <span>Contrast boost (CLAHE) for dark footage</span>
            </label>
          </fieldset>

          {busy ? (
            <div className="job-progress" role="status">
              <div className="control-row">
                <span>{PHASE_LABEL[job.phase]}…</span>
                <output>{Math.round(job.progress * 100)}%</output>
              </div>
              <progress max="1" value={job.progress} aria-label={`${PHASE_LABEL[job.phase]} progress`} />
              <button type="button" className="button" onClick={job.cancel}>Cancel</button>
            </div>
          ) : (
            <button type="button" className="button primary" disabled={!file} onClick={() => job.start(file, options)}>
              {result ? 'Analyse again' : 'Analyse video'}
            </button>
          )}
          {job.phase === 'cancelled' && <p className="hint">Analysis cancelled.</p>}
          <p className="hint">
            The video is processed on the server and deleted right after. People get anonymous IDs that exist only in
            this result.
          </p>
        </aside>

        <div className="result-area">
          {!file ? (
            <div className="panel placeholder"><p>Choose a video to track the people in it.</p></div>
          ) : (
            <div className="panel viewer">
              <div className="viewer-head">
                <span className="file-name" title={file.name}>{file.name}</span>
                {result && (
                  <span className="muted small">
                    {result.video.width}×{result.video.height} · {result.video.analysed_fps} frames/s analysed
                  </span>
                )}
              </div>
              <div className="viewer-body">
                <VideoPlayer
                  ref={playerRef}
                  src={url}
                  frames={result?.frames}
                  width={result?.video.width}
                  height={result?.video.height}
                  highlightId={highlightId}
                  onHighlight={setHighlightId}
                  onTime={onTime}
                />
              </div>
            </div>
          )}

          {result && (
            <>
              <dl className="stats">
                <div className="stat stat-main">
                  <dt>Unique people</dt>
                  <dd data-testid="video-unique">{result.summary.unique_people}</dd>
                </div>
                <div className="stat">
                  <dt>Peak in frame</dt>
                  <dd>{result.summary.peak_people}</dd>
                  {result.summary.peak_t != null && (
                    <button type="button" className="link-button stat-note" onClick={() => seek(result.summary.peak_t)}>
                      at {clock(result.summary.peak_t)}
                    </button>
                  )}
                </div>
                <div className="stat">
                  <dt>Avg in frame</dt>
                  <dd>{result.summary.avg_people}</dd>
                </div>
                <div className="stat">
                  <dt>Video length</dt>
                  <dd>{duration(result.video.duration_s)}</dd>
                </div>
                <div className="stat">
                  <dt>Processing</dt>
                  <dd>{duration(result.summary.processing_s)}</dd>
                  <div className="stat-note">{result.summary.speed_factor}× real time · {ms(result.summary.avg_inference_ms)}/frame</div>
                </div>
              </dl>

              <section className="panel">
                <h2>People over the video</h2>
                <VideoTimeline
                  frames={result.frames}
                  duration={result.video.duration_s}
                  currentTime={currentTime}
                  onSeek={seek}
                />
              </section>

              <section className="panel">
                <h2>Tracked people</h2>
                {result.people.length === 0 ? (
                  <p className="muted empty">Nobody was tracked in this video.</p>
                ) : (
                  <div className="table-wrap detection-list">
                    <table>
                      <thead>
                        <tr>
                          <th scope="col">ID</th>
                          <th scope="col">First seen</th>
                          <th scope="col">Last seen</th>
                          <th scope="col">On screen</th>
                          <th scope="col">Best confidence</th>
                          <th scope="col"><span className="visually-hidden">Jump</span></th>
                        </tr>
                      </thead>
                      <tbody onMouseLeave={() => setHighlightId(null)}>
                        {result.people.map((p) => (
                          <tr
                            key={p.track_id}
                            className={highlightId === p.track_id ? 'active' : undefined}
                            onMouseEnter={() => setHighlightId(p.track_id)}
                          >
                            <td className="strong">#{p.track_id}</td>
                            <td className="num">{clock(p.first_t)}</td>
                            <td className="num">{clock(p.last_t)}</td>
                            <td className="num">{duration(p.duration_s)}</td>
                            <td className="num">{pct(p.best_confidence)}</td>
                            <td>
                              <button type="button" className="link-button" onClick={() => {
                                setHighlightId(p.track_id)
                                seek(p.first_t)
                              }}>
                                Show
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <p className="hint">
                  A person who leaves and returns after more than ~3 seconds gets a new ID, and people walking past each
                  other can swap IDs, so “unique people” is an estimate.
                </p>
              </section>
            </>
          )}
        </div>
      </div>
    </>
  )
}
