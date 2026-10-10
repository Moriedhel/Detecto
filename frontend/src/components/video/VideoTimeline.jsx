import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import useChartColors from '../../hooks/useChartColors'
import { clock } from '../../utils/format'
import ChartTooltip from '../history/ChartTooltip'

const HEIGHT = 180

/**
 * People in frame over video time (single series, so no legend). The playhead is
 * a vertical line; clicking the chart seeks the video there.
 */
export default function VideoTimeline({ frames, duration, currentTime, onSeek }) {
  const c = useChartColors()
  const data = frames.map((f) => ({ t: f.t, count: f.boxes.length }))

  return (
    <figure className="chart">
      <ResponsiveContainer width="100%" height={HEIGHT} initialDimension={{ width: 600, height: HEIGHT }}>
        <AreaChart
          data={data}
          margin={{ top: 8, right: 16, bottom: 0, left: 0 }}
          onClick={(e) => e?.activeLabel != null && onSeek(Number(e.activeLabel))}
          style={{ cursor: 'pointer' }}
        >
          <CartesianGrid vertical={false} stroke={c.grid} strokeWidth={1} />
          <XAxis
            dataKey="t"
            type="number"
            domain={[0, Math.max(duration, data.at(-1)?.t ?? 0)]}
            tickFormatter={(t) => clock(t, 0)}
            tick={{ fill: c.text, fontSize: 12 }}
            stroke={c.grid}
            tickLine={false}
            minTickGap={40}
          />
          <YAxis allowDecimals={false} width={32} tick={{ fill: c.text, fontSize: 12 }} axisLine={false} tickLine={false} />
          <Tooltip
            cursor={{ stroke: c.text, strokeWidth: 1 }}
            content={({ active, payload }) => {
              const d = payload?.[0]?.payload
              if (!active || !d) return null
              return <ChartTooltip value={`${d.count} ${d.count === 1 ? 'person' : 'people'}`} lines={[`at ${clock(d.t)} · click to jump`]} />
            }}
          />
          <Area
            type="stepAfter"
            dataKey="count"
            stroke={c.mark}
            strokeWidth={2}
            fill={c.mark}
            fillOpacity={0.1}
            dot={false}
            activeDot={{ r: 5, fill: c.mark, stroke: c.surface, strokeWidth: 2 }}
            isAnimationActive={false}
          />
          {currentTime != null && <ReferenceLine x={currentTime} stroke={c.text} strokeWidth={1.5} />}
        </AreaChart>
      </ResponsiveContainer>
      <figcaption className="muted small">People in frame at each analysed moment. Click to jump the video there.</figcaption>
    </figure>
  )
}
