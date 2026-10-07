import { useEffect, useRef, useState } from 'react'

import { confidenceLevel, pct } from '../utils/format'

const LABEL_PX = 12 // label font size on screen, regardless of image scale

/**
 * Image with bounding boxes drawn as an SVG layer.
 *
 * The SVG's viewBox uses the ORIGINAL image's pixel size (as returned by the
 * API), so box coordinates map directly and the browser scales boxes together
 * with the image. Only the label size depends on the displayed size, so that
 * text stays readable on phones and big screens alike.
 */
export default function DetectionOverlay({ src, alt, width, height, detections = [], hovered, onHover }) {
  const imgRef = useRef(null)
  const [displayWidth, setDisplayWidth] = useState(0)
  const [broken, setBroken] = useState(false)

  useEffect(() => setBroken(false), [src])

  // Track the rendered image width (ResizeObserver is missing in some test environments)
  useEffect(() => {
    const img = imgRef.current
    if (!img || typeof ResizeObserver === 'undefined') return undefined
    const ro = new ResizeObserver(([entry]) => setDisplayWidth(entry.contentRect.width))
    ro.observe(img)
    return () => ro.disconnect()
  }, [src])

  if (broken) {
    return <p className="muted preview-missing">Preview not available for this file.</p>
  }

  const hasBoxes = width > 0 && height > 0
  const scale = displayWidth > 0 ? width / displayWidth : 1 // image px per screen px
  const fontSize = LABEL_PX * scale
  const pad = fontSize * 0.3
  const labelH = fontSize + pad * 2

  const labels = detections.map((d, i) => {
    const [x1, y1] = d.bbox
    const text = `#${i + 1} ${pct(d.confidence)}`
    const w = text.length * fontSize * 0.62 + pad * 2
    return {
      text,
      w,
      x: Math.max(0, Math.min(x1, width - w)), // keep inside the image horizontally
      y: y1 - labelH >= 0 ? y1 - labelH : y1, // above the box, or inside at the top edge
    }
  })

  const boxClass = (d, i) => {
    const active = hovered === i
    const dimmed = hovered != null && !active
    return `box box-${confidenceLevel(d.confidence)}${active ? ' active' : ''}${dimmed ? ' dimmed' : ''}`
  }

  // Draw the hovered label last so it is never covered by a neighbour
  const labelOrder = detections.map((_, i) => i).filter((i) => i !== hovered)
  if (hovered != null && hovered < detections.length) labelOrder.push(hovered)

  return (
    <div className="overlay">
      <img ref={imgRef} src={src} alt={alt} onError={() => setBroken(true)} />
      {hasBoxes && (
        <svg
          className="overlay-svg"
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={`${detections.length} ${detections.length === 1 ? 'person' : 'people'} detected`}
          onMouseLeave={() => onHover?.(null)}
        >
          {/* Pass 1: boxes */}
          {detections.map((d, i) => {
            const [x1, y1, x2, y2] = d.bbox
            return (
              <g key={i} className={boxClass(d, i)} onMouseEnter={() => onHover?.(i)} data-testid="detection-box">
                <rect x={x1} y={y1} width={x2 - x1} height={y2 - y1} className="box-rect" vectorEffect="non-scaling-stroke" />
              </g>
            )
          })}
          {/* Pass 2: labels on top of every box */}
          {labelOrder.map((i) => {
            const l = labels[i]
            return (
              <g key={`label-${i}`} className={boxClass(detections[i], i)} onMouseEnter={() => onHover?.(i)}>
                <rect x={l.x} y={l.y} width={l.w} height={labelH} className="box-label-bg" />
                <text x={l.x + pad} y={l.y + labelH - pad * 1.4} fontSize={fontSize} className="box-label">
                  {l.text}
                </text>
              </g>
            )
          })}
        </svg>
      )}
    </div>
  )
}
