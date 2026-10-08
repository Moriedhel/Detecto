import { ms, pct } from '../../utils/format'

const num = (v, digits = 0) =>
  v == null ? '–' : v.toLocaleString(undefined, { maximumFractionDigits: digits })

// Headline numbers for the filtered history.
export default function KpiRow({ summary }) {
  const s = summary ?? {}
  const tiles = [
    { label: 'Detections', value: num(s.total_detections), note: `${num(s.frames_with_people)} with people` },
    { label: 'People counted', value: num(s.total_people) },
    { label: 'Avg per detection', value: num(s.avg_people, 2) },
    { label: 'Peak', value: num(s.max_people), note: 'most people in one image' },
    { label: 'Avg confidence', value: pct(s.avg_confidence), note: 'per detected person' },
    { label: 'Avg inference', value: ms(s.avg_inference_ms), note: `p95 ${ms(s.p95_inference_ms)}` },
  ]

  return (
    <dl className="stats kpis">
      {tiles.map((t) => (
        <div className="stat" key={t.label}>
          <dt>{t.label}</dt>
          <dd>{t.value}</dd>
          {t.note && <div className="stat-note">{t.note}</div>}
        </div>
      ))}
    </dl>
  )
}
