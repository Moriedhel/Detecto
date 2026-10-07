import { useCallback, useEffect, useRef, useState } from 'react'

/** Turn getUserMedia errors into messages an operator can act on. */
export function cameraErrorMessage(err) {
  switch (err?.name) {
    case 'NotAllowedError':
    case 'PermissionDeniedError':
      return 'Camera access was denied. Allow the camera for this site in your browser settings, then try again.'
    case 'NotFoundError':
    case 'DevicesNotFoundError':
    case 'OverconstrainedError':
      return 'No camera was found. Connect a camera and try again.'
    case 'NotReadableError':
    case 'TrackStartError':
      return 'The camera is busy or unavailable. Close other apps that use it (video calls, camera app) and try again.'
    case 'SecurityError':
      return 'The browser blocked camera access. Open the app via http://localhost or HTTPS.'
    default:
      return `Could not start the camera${err?.message ? `: ${err.message}` : '.'}`
  }
}

const VIDEO_CONSTRAINTS = { width: { ideal: 1280 }, height: { ideal: 720 } }

/**
 * Manage a webcam stream bound to a <video> element.
 * status: 'idle' | 'starting' | 'live' | 'error'
 */
export default function useCamera() {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState(null)
  const [devices, setDevices] = useState([])
  const [deviceId, setDeviceId] = useState(null)

  const releaseStream = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
  }

  const stop = useCallback(() => {
    releaseStream()
    setStatus('idle')
  }, [])

  const start = useCallback(async (requestedDeviceId = null) => {
    setError(null)
    if (!navigator.mediaDevices?.getUserMedia) {
      setError(
        window.isSecureContext === false
          ? 'Camera access needs a secure page. Open the app via http://localhost or HTTPS.'
          : 'This browser does not support camera access.',
      )
      setStatus('error')
      return false
    }

    setStatus('starting')
    releaseStream()
    try {
      const video = requestedDeviceId
        ? { ...VIDEO_CONSTRAINTS, deviceId: { exact: requestedDeviceId } }
        : VIDEO_CONSTRAINTS
      const stream = await navigator.mediaDevices.getUserMedia({ video, audio: false })
      streamRef.current = stream

      const [track] = stream.getVideoTracks()
      if (track) {
        // e.g. USB camera unplugged
        track.onended = () => {
          releaseStream()
          setError('The camera stopped (disconnected or turned off).')
          setStatus('error')
        }
        setDeviceId(track.getSettings?.().deviceId ?? requestedDeviceId)
      }

      const el = videoRef.current
      if (el) {
        el.srcObject = stream
        await el.play()
      }

      // Device labels are only available after permission is granted
      const all = (await navigator.mediaDevices.enumerateDevices?.()) ?? []
      setDevices(all.filter((d) => d.kind === 'videoinput'))
      setStatus('live')
      return true
    } catch (err) {
      releaseStream()
      setError(cameraErrorMessage(err))
      setStatus('error')
      return false
    }
  }, [])

  // Always release the camera when the component using it unmounts
  useEffect(() => releaseStream, [])

  return { videoRef, status, error, devices, deviceId, start, stop }
}
