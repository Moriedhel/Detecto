import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'

import useElementWidth from '../../hooks/useElementWidth'
import BoxLayer from '../BoxLayer'

/** Index of the last analysed frame at or before time t (frames sorted by t). */
export function frameIndexAt(frames, t) {
  let lo = 0
  let hi = frames.length - 1
  if (hi < 0 || t < frames[0].t) return -1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (frames[mid].t <= t) lo = mid
    else hi = mid - 1
  }
  return lo
}

/** Analysed frame boxes ([id, x1, y1, x2, y2, conf]) -> BoxLayer detections. */
export const toDetections = (boxes) =>
  boxes.map(([id, x1, y1, x2, y2, conf]) => ({ track_id: id, bbox: [x1, y1, x2, y2], confidence: conf }))

/**
 * The user's own video file playing with the analysed tracks drawn on top.
 * Boxes follow the video clock (requestAnimationFrame while playing), so pausing,
 * seeking and scrubbing all stay in sync. Exposes seek(t) to the parent.
 */
const VideoPlayer = forwardRef(function VideoPlayer(
  { src, frames, width, height, highlightId, onHighlight, onTime }, ref,
) {
  const videoRef = useRef(null)
  const displayWidth = useElementWidth(videoRef, src)
  const [index, setIndex] = useState(-1)

  useImperativeHandle(ref, () => ({
    seek(t) {
      const v = videoRef.current
      if (!v) return
      v.currentTime = Math.max(0, t)
      v.pause()
    },
  }))

  useEffect(() => {
    const v = videoRef.current
    if (!v || !frames?.length) return undefined
    let raf = 0
    let lastIndex = null
    // Runs every animation frame while playing, but only re-renders when the
    // analysed frame changes (~10 times per second, not 60)
    const sync = () => {
      const i = frameIndexAt(frames, v.currentTime)
      if (i === lastIndex) return
      lastIndex = i
      setIndex(i)
      onTime?.(i >= 0 ? frames[i].t : 0)
    }
    const tick = () => {
      sync()
      raf = requestAnimationFrame(tick)
    }
    const play = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(tick)
    }
    const pause = () => {
      cancelAnimationFrame(raf)
      sync()
    }
    v.addEventListener('play', play)
    v.addEventListener('pause', pause)
    v.addEventListener('seeked', sync)
    v.addEventListener('loadeddata', sync)
    sync()
    return () => {
      cancelAnimationFrame(raf)
      v.removeEventListener('play', play)
      v.removeEventListener('pause', pause)
      v.removeEventListener('seeked', sync)
      v.removeEventListener('loadeddata', sync)
    }
  }, [frames, onTime])

  const detections = index >= 0 && frames ? toDetections(frames[index].boxes) : []
  const hovered = highlightId == null ? null : detections.findIndex((d) => d.track_id === highlightId)

  return (
    <div className="overlay">
      <video ref={videoRef} src={src} controls playsInline muted aria-label="Uploaded video" />
      {frames && (
        <BoxLayer
          width={width}
          height={height}
          detections={detections}
          hovered={hovered >= 0 ? hovered : null}
          onHover={(i) => onHighlight?.(i == null ? null : detections[i]?.track_id ?? null)}
          displayWidth={displayWidth}
        />
      )}
    </div>
  )
})

export default VideoPlayer
