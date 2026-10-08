// Tooltip body shared by the history charts: value first (strong), context after (muted).
// React renders strings as text, so record values (e.g. file names) are never parsed as HTML.
export default function ChartTooltip({ value, lines = [] }) {
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-value">{value}</div>
      {lines.filter(Boolean).map((l) => (
        <div key={l} className="chart-tooltip-line">{l}</div>
      ))}
    </div>
  )
}
