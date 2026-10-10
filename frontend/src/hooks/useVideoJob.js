import { useCallback, useEffect, useRef, useState } from 'react'

import { deleteVideoJob, getVideoJob, uploadVideo } from '../api'

const POLL_MS = 700

/**
 * Upload a video, then poll its analysis job until it finishes.
 * phase: 'idle' | 'uploading' | 'processing' | 'done' | 'error' | 'cancelled'
 */
export default function useVideoJob() {
  const [state, setState] = useState({ phase: 'idle', progress: 0, job: null, error: null })
  const run = useRef({ controller: null, jobId: null, timer: null })

  const stopPolling = () => {
    clearTimeout(run.current.timer)
    run.current.controller?.abort()
  }

  const poll = useCallback(async (jobId, controller) => {
    try {
      const job = await getVideoJob(jobId, { signal: controller.signal })
      if (controller.signal.aborted) return
      if (job.status === 'done') {
        setState({ phase: 'done', progress: 1, job, error: null })
      } else if (job.status === 'error' || job.status === 'cancelled') {
        setState({ phase: job.status, progress: 0, job, error: job.error || null })
      } else {
        setState((s) => ({ ...s, phase: 'processing', progress: job.progress, job }))
        run.current.timer = setTimeout(() => poll(jobId, controller), POLL_MS)
      }
    } catch (err) {
      if (err.name !== 'AbortError') setState((s) => ({ ...s, phase: 'error', error: err.message }))
    }
  }, [])

  const start = useCallback(async (file, options) => {
    stopPolling()
    const controller = new AbortController()
    run.current = { controller, jobId: null, timer: null }
    setState({ phase: 'uploading', progress: 0, job: null, error: null })
    try {
      const job = await uploadVideo(file, options, {
        signal: controller.signal,
        onUploadProgress: (p) => setState((s) => ({ ...s, progress: p })),
      })
      run.current.jobId = job.id
      setState({ phase: 'processing', progress: 0, job, error: null })
      poll(job.id, controller)
    } catch (err) {
      if (err.name === 'AbortError') setState({ phase: 'cancelled', progress: 0, job: null, error: null })
      else setState({ phase: 'error', progress: 0, job: null, error: err.message })
    }
  }, [poll])

  /** Abort the upload or cancel the server-side job. */
  const cancel = useCallback(() => {
    const { jobId } = run.current
    stopPolling()
    if (jobId) deleteVideoJob(jobId).catch(() => {})
    setState((s) => ({ ...s, phase: 'cancelled', progress: 0 }))
  }, [])

  const reset = useCallback(() => {
    stopPolling()
    run.current = { controller: null, jobId: null, timer: null }
    setState({ phase: 'idle', progress: 0, job: null, error: null })
  }, [])

  // Leaving the page cancels unfinished work so the server doesn't keep processing
  useEffect(() => () => {
    const { jobId } = run.current
    const busy = run.current.controller && !run.current.controller.signal.aborted
    stopPolling()
    if (jobId && busy) deleteVideoJob(jobId).catch(() => {})
  }, [])

  return { ...state, start, cancel, reset }
}
