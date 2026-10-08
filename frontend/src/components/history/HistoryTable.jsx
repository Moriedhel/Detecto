import { ms, pct } from '../../utils/format'
import { formatDateTime } from '../../utils/timeRange'

// Paged table of stored detections (also the table view of the time chart).
export default function HistoryTable({ page, pageIndex, pageSize, onPage }) {
  if (!page) return null
  const { total, items } = page

  if (total === 0) {
    return <p className="muted empty">No detections match these filters.</p>
  }

  const from = pageIndex * pageSize + 1
  const to = Math.min(total, from + items.length - 1)
  const lastPage = Math.max(0, Math.ceil(total / pageSize) - 1)

  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Time</th>
              <th scope="col">People</th>
              <th scope="col">Avg confidence</th>
              <th scope="col">Inference</th>
              <th scope="col">Source</th>
              <th scope="col">Threshold</th>
              <th scope="col">#</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id}>
                <td>{formatDateTime(r.timestamp)}</td>
                <td className="num strong">{r.count}</td>
                <td className="num">{pct(r.avg_confidence)}</td>
                <td className="num">{ms(r.inference_ms)}</td>
                <td className="source" title={r.source ?? ''}>{r.source ?? '–'}</td>
                <td className="num">
                  {pct(r.conf_threshold)}
                  {r.contrast_enhanced ? ' · CLAHE' : ''}
                </td>
                <td className="num muted">{r.id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <nav className="pager" aria-label="Table pages">
        <span className="muted small">
          {from.toLocaleString()}–{to.toLocaleString()} of {total.toLocaleString()}
        </span>
        <button type="button" className="button" onClick={() => onPage(pageIndex - 1)} disabled={pageIndex === 0}>
          Previous
        </button>
        <button type="button" className="button" onClick={() => onPage(pageIndex + 1)} disabled={pageIndex >= lastPage}>
          Next
        </button>
      </nav>
    </>
  )
}
