import { useEffect, useRef, useState } from 'react'

import useElementWidth from '../hooks/useElementWidth'
import BoxLayer from './BoxLayer'

// Uploaded image with its detection boxes drawn on top.
export default function DetectionOverlay({ src, alt, width, height, detections = [], hovered, onHover }) {
  const imgRef = useRef(null)
  const displayWidth = useElementWidth(imgRef, src)
  const [broken, setBroken] = useState(false)

  useEffect(() => setBroken(false), [src])

  if (broken) {
    return <p className="muted preview-missing">Preview not available for this file.</p>
  }

  return (
    <div className="overlay">
      <img ref={imgRef} src={src} alt={alt} onError={() => setBroken(true)} />
      <BoxLayer
        width={width}
        height={height}
        detections={detections}
        hovered={hovered}
        onHover={onHover}
        displayWidth={displayWidth}
      />
    </div>
  )
}
