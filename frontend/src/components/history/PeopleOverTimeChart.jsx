import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import useChartColors from '../../hooks/useChartColors'
import { pct } from '../../utils/format'
import { formatDateTime } from '../../utils/timeRange'
import ChartTooltip from './ChartTooltip'

const HEIGHT = 260
const RAW_LIMIT = 150 // above this many detections, plot hourly averages instead of every point
const DOTS_UP_TO = 60 // show point markers only while they stay readable
const HOUR = 3600_000

/**
 * Raw detections as chart points, with a null point inserted wherever the gap
 * between detections is long, so the line breaks instead of implying data.
 */
export function rawPoints(records) {
  const pts = records.map((r) => ({
    t: Date.parse(r.timestamp),
    value: r.count,
    conf: r.avg_confidence,
    source: r.source,
    id: r.id,
  }))
  const gaps = pts.slice(1).map((p, i) => p.t - pts[i].t).sort((a, b) => a - b)
  const median = gaps.length ? gaps[Math.floor(gaps.length / 2)] : 0
  const maxGap = Math.max(2 * HOUR, 6 * median)

  const out = []
  pts.forEach((p, i) => {
    if (i > 0 && p.t - pts[i - 1].t > maxGap) out.push({ t: (p.t + pts[i - 1].t) / 2, value: null })
    out.push(p)
  })
  return out
}

/** Hourly timeline buckets ("YYYY-MM-DDTHH:00", local) with null for hours without data. */
export function hourlyPoints(buckets) {
  if (!buckets.length) return []
  const byTime = new Map(buckets.map((b) => [new Date(b.hour).getTime(), b])) // parsed as local time
  const times = [...byTime.keys()].sort((a, b) => a - b)
  const out = []
  for (let t = times[0]; t <= times[times.length - 1]; t += HOUR) {
    const b = byTime.get(t)
    out.push(b
      ? { t, value: b.avg_people, max: b.max_people, detections: b.detections, conf: b.avg_confidence }
      : { t, value: null })
  }
  return out
}

function tickFormatter(spanMs) {
  if (spanMs <= 36 * HOUR) {
    return (t) => new Date(t).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  }
  return (t) => new Date(t).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

/** For multi-day ranges: one tick per local midnight (thinned to ~8), so dates never repeat. */
export function dayTicks([from, to]) {
  if (to - from <= 36 * HOUR) return undefined // let the chart pick time-of-day ticks
  const d = new Date(from)
  d.setHours(24, 0, 0, 0) // first local midnight after `from`
  const ticks = []
  for (; d.getTime() <= to; d.setDate(d.getDate() + 1)) ticks.push(d.getTime())
  const step = Math.ceil(ticks.length / 8)
  return ticks.filter((_, i) => i % step === 0)
}

const hourRange = (t) => {
  const from = new Date(t)
  const to = new Date(t + HOUR)
  const time = (d) => d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  return `${from.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}, ${time(from)}–${time(to)}`
}

/**
 * People over time (single series: no legend; the title names it).
 * Few detections: every detection as a step line (a count holds until the next one).
 * Many detections: hourly average, which keeps a week of data readable.
 * Long gaps break the line rather than implying a value.
 */
export default function PeopleOverTimeChart({ records, total, timeline }) {
  const c = useChartColors()

  if (!records?.length) {
    return <p className="muted chart-empty">No detections in this range.</p>
  }

  const hourly = total > RAW_LIMIT && timeline?.length > 0
  const data = hourly ? hourlyPoints(timeline) : rawPoints(records)
  const first = data[0].t
  const last = data[data.length - 1].t
  // A single point (or identical times) still needs a visible time window
  const domain = last > first ? [first, last] : [first - HOUR / 2, last + HOUR / 2]
  const plotted = data.filter((d) => d.value != null).length
  const dot = plotted <= DOTS_UP_TO ? { r: 4, fill: c.mark, stroke: c.surface, strokeWidth: 2 } : false

  return (
    <figure className="chart">
      <ResponsiveContainer width="100%" height={HEIGHT} initialDimension={{ width: 600, height: HEIGHT }}>
        <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={c.grid} strokeWidth={1} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={domain}
            ticks={dayTicks(domain)}
            tickFormatter={tickFormatter(domain[1] - domain[0])}
            tick={{ fill: c.text, fontSize: 12 }}
            stroke={c.grid}
            tickLine={false}
            minTickGap={40}
          />
          <YAxis
            allowDecimals={hourly}
            width={36}
            tick={{ fill: c.text, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ stroke: c.text, strokeWidth: 1 }}
            content={({ active, payload }) => {
              const d = payload?.[0]?.payload
              if (!active || !d || d.value == null) return null
              return hourly ? (
                <ChartTooltip
                  value={`${d.value} avg people`}
                  lines={[hourRange(d.t), `peak ${d.max} · ${d.detections} detections`,
                    d.conf != null && `avg confidence ${pct(d.conf)}`]}
                />
              ) : (
                <ChartTooltip
                  value={`${d.value} ${d.value === 1 ? 'person' : 'people'}`}
                  lines={[formatDateTime(d.t), d.conf != null && `avg confidence ${pct(d.conf)}`,
                    d.source && `${d.source} · #${d.id}`]}
                />
              )
            }}
          />
          <Area
            type={hourly ? 'linear' : 'stepAfter'}
            dataKey="value"
            stroke={c.mark}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            fill={c.mark}
            fillOpacity={0.1}
            connectNulls={false}
            dot={dot}
            activeDot={{ r: 5, fill: c.mark, stroke: c.surface, strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
      <figcaption className="muted small">
        {hourly
          ? `Hourly average of ${total.toLocaleString()} detections. Gaps are hours without detections.`
          : 'Each point is one detection. Gaps are periods without detections.'}
      </figcaption>
    </figure>
  )
}
