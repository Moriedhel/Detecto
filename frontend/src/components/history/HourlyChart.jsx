import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import useChartColors from '../../hooks/useChartColors'
import { pct } from '../../utils/format'
import ChartTooltip from './ChartTooltip'

const HEIGHT = 220
const hourLabel = (h) => `${String(h).padStart(2, '0')}:00`

/**
 * Average crowd size per hour of day (local time). One series, one colour;
 * hours without detections keep their slot but have no bar (no data != zero people).
 * A table view below gives every value without hovering.
 */
export default function HourlyChart({ buckets }) {
  const c = useChartColors()

  if (!buckets?.length) {
    return <p className="muted chart-empty">No detections in this range.</p>
  }

  const byHour = new Map(buckets.map((b) => [Number(b.hour), b]))
  const data = Array.from({ length: 24 }, (_, h) => {
    const b = byHour.get(h)
    return {
      hour: h,
      avg: b ? b.avg_people : null,
      max: b?.max_people ?? null,
      detections: b?.detections ?? 0,
      conf: b?.avg_confidence ?? null,
    }
  })

  return (
    <figure className="chart">
      <ResponsiveContainer width="100%" height={HEIGHT} initialDimension={{ width: 600, height: HEIGHT }}>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={c.grid} strokeWidth={1} />
          <XAxis
            dataKey="hour"
            tickFormatter={hourLabel}
            ticks={[0, 3, 6, 9, 12, 15, 18, 21]}
            tick={{ fill: c.text, fontSize: 12 }}
            stroke={c.grid}
            tickLine={false}
          />
          <YAxis width={36} tick={{ fill: c.text, fontSize: 12 }} axisLine={false} tickLine={false} />
          <Tooltip
            cursor={{ fill: c.grid, opacity: 0.5 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const d = payload[0].payload
              if (!d.detections) return <ChartTooltip value="No detections" lines={[hourLabel(d.hour)]} />
              return (
                <ChartTooltip
                  value={`${d.avg} avg people`}
                  lines={[
                    `${hourLabel(d.hour)}–${hourLabel((d.hour + 1) % 24)}`,
                    `peak ${d.max} · ${d.detections} detections`,
                    d.conf != null && `avg confidence ${pct(d.conf)}`,
                  ]}
                />
              )
            }}
          />
          <Bar dataKey="avg" fill={c.mark} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>

      <details className="table-view">
        <summary>View as table</summary>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Hour</th>
                <th scope="col">Avg people</th>
                <th scope="col">Peak</th>
                <th scope="col">Detections</th>
                <th scope="col">Avg confidence</th>
              </tr>
            </thead>
            <tbody>
              {data.filter((d) => d.detections > 0).map((d) => (
                <tr key={d.hour}>
                  <td>{hourLabel(d.hour)}</td>
                  <td className="num">{d.avg}</td>
                  <td className="num">{d.max}</td>
                  <td className="num">{d.detections}</td>
                  <td className="num">{pct(d.conf)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  )
}
