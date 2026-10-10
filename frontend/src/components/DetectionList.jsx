import { confidenceLevel, pct } from '../utils/format'

// Table of detected people. Hovering a row highlights its box (and vice versa).
// A "Name" column appears when face recognition results are present.
export default function DetectionList({ detections, hovered, onHover, showIdentity = false }) {
  if (detections.length === 0) {
    return <p className="muted empty">No people detected at this threshold.</p>
  }

  return (
    <div className="table-wrap detection-list">
      <table>
        <thead>
          <tr>
            <th scope="col">#</th>
            {showIdentity && <th scope="col">Name</th>}
            <th scope="col">Confidence</th>
            <th scope="col">Size (px)</th>
            <th scope="col">Center (x, y)</th>
          </tr>
        </thead>
        <tbody onMouseLeave={() => onHover(null)}>
          {detections.map((d, i) => (
            <tr
              key={i}
              className={hovered === i ? 'active' : undefined}
              onMouseEnter={() => onHover(i)}
            >
              <td>{i + 1}</td>
              {showIdentity && (
                <td>
                  {d.identity?.name ? (
                    <><strong>{d.identity.name}</strong> <span className="muted">{pct(d.identity.similarity)}</span></>
                  ) : (
                    <span className="muted">{d.identity ? 'Unknown' : 'No face visible'}</span>
                  )}
                </td>
              )}
              <td>
                <span className="conf-cell">
                  <span className={`conf-bar conf-${confidenceLevel(d.confidence)}`}>
                    <span style={{ width: pct(d.confidence) }} />
                  </span>
                  {pct(d.confidence)}
                </span>
              </td>
              <td className="num">{Math.round(d.width)} × {Math.round(d.height)}</td>
              <td className="num">{Math.round(d.center[0])}, {Math.round(d.center[1])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
