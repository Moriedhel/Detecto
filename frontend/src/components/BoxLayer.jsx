import { confidenceLevel, pct } from '../utils/format'

const LABEL_PX = 12 // label font size on screen, regardless of image scale

/**
 * SVG layer of bounding boxes, placed over an <img> or <video> of the same aspect ratio.
 *
 * The viewBox uses the source image's pixel size (as returned by the API), so
 * box coordinates map directly and the browser scales them with the media.
 * Only the label size depends on `displayWidth` (rendered CSS px), so labels
 * stay readable at any size.
 */
export default function BoxLayer({ width, height, detections = [], faces = null, hovered, onHover, displayWidth = 0 }) {
  if (!(width > 0 && height > 0)) return null

  const scale = displayWidth > 0 ? width / displayWidth : 1 // source px per screen px
  const fontSize = LABEL_PX * scale
  const pad = fontSize * 0.3
  const labelH = fontSize + pad * 2

  const labels = detections.map((d, i) => {
    const [x1, y1] = d.bbox
    // Track ID when tracking (stable across frames), else position in the list.
    // A recognised face names the person; otherwise show the detection confidence.
    // "?" while a new person is still being compared with people who left (ID may change)
    const num = d.pending ? '?' : d.track_id ?? i + 1
    const text = d.identity?.name ? `#${num} ${d.identity.name}` : `#${num} ${pct(d.confidence)}`
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
      {/* Faces (when recognition is on): thin boxes, name or "Unknown" below the face */}
      {faces?.map((f, i) => {
        const [x1, y1, x2, y2] = f.bbox
        const text = f.name ? `${f.name} ${pct(f.similarity)}` : 'Unknown'
        const w = text.length * fontSize * 0.62 + pad * 2
        const lx = Math.max(0, Math.min(x1, width - w))
        const ly = Math.min(y2, height - labelH)
        return (
          <g key={`face-${i}`} className={`face ${f.name ? 'face-known' : 'face-unknown'}`} data-testid="face-box">
            <rect x={x1} y={y1} width={x2 - x1} height={y2 - y1} className="face-rect" vectorEffect="non-scaling-stroke" />
            <rect x={lx} y={ly} width={w} height={labelH} className="face-label-bg" />
            <text x={lx + pad} y={ly + labelH - pad * 1.4} fontSize={fontSize} className="face-label">{text}</text>
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
  )
}
