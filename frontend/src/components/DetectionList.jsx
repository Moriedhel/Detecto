import { confidenceLevel, duration, pct } from '../utils/format'

// Table of detected people. Hovering a row highlights its box (and vice versa).
// Extra columns appear with face recognition ("Name") and tracking ("Visible for").
export default function DetectionList({ detections, hovered, onHover, showIdentity = false }) {
  if (detections.length === 0) {
    return <p className="muted empty">No people detected at this threshold.</p>
  }
  const tracking = detections.some((d) => d.track_id != null)

  return (
    <div className="table-wrap detection-list">
      <table>
        <thead>
          <tr>
            <th scope="col">{tracking ? 'ID' : '#'}</th>
            {showIdentity && <th scope="col">Name</th>}
            <th scope="col">Confidence</th>
            {tracking && <th scope="col">Visible for</th>}
            <th scope="col">Size (px)</th>
            <th scope="col">Center (x, y)</th>
          </tr>
        </thead>
        <tbody onMouseLeave={() => onHover(null)}>
          {detections.map((d, i) => (
            <tr
              key={d.track_id ?? i}
              className={hovered === i ? 'active' : undefined}
              onMouseEnter={() => onHover(i)}
            >
              <td>{d.track_id ?? i + 1}</td>
              {showIdentity && (
                <td>
                  {d.identity?.name ? (
                    <>
                      <strong>{d.identity.name}</strong>{' '}
                      <span className="muted">
                        {d.identity.from_track ? 'recognised earlier' : pct(d.identity.similarity)}
                      </span>
                    </>
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
              {tracking && <td className="num">{duration(d.tracked_s)}</td>}
              <td className="num">{Math.round(d.width)} × {Math.round(d.height)}</td>
              <td className="num">{Math.round(d.center[0])}, {Math.round(d.center[1])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
