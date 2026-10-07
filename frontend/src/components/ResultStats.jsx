import { ms, pct } from '../utils/format'

// Headline numbers for one detection result.
export default function ResultStats({ result, roundTripMs }) {
  const { count, avg_confidence: avg, timings } = result
  return (
    <dl className="stats">
      <div className="stat stat-main">
        <dt>People</dt>
        <dd data-testid="people-count">{count}</dd>
      </div>
      <div className="stat">
        <dt>Avg confidence</dt>
        <dd>{pct(avg)}</dd>
      </div>
      <div className="stat">
        <dt>Inference</dt>
        <dd>{ms(timings.inference_ms)}</dd>
      </div>
      <div className="stat">
        <dt>Server total</dt>
        <dd title="Decode + preprocess + detect + response, measured on the server">{ms(timings.total_ms)}</dd>
      </div>
      {roundTripMs != null && (
        <div className="stat">
          <dt>Round trip</dt>
          <dd title="Upload + server processing + download, measured in the browser">{ms(roundTripMs)}</dd>
        </div>
      )}
    </dl>
  )
}
