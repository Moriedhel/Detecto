// Display formatting helpers.

/** 0.873 -> "87%"; null -> "–" */
export const pct = (v) => (v == null ? '–' : `${Math.round(v * 100)}%`)

/** 12.34 -> "12 ms"; 1234 -> "1.23 s"; null -> "–" */
export const ms = (v) => {
  if (v == null) return '–'
  return v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${Math.round(v)} ms`
}

/** Seconds as a video clock: 83.4 -> "1:23.4"; null -> "–" */
export const clock = (s, decimals = 1) => {
  if (s == null) return '–'
  const m = Math.floor(s / 60)
  const width = decimals ? 3 + decimals : 2 // "05" or "05.3"
  const sec = (s - m * 60).toFixed(decimals).padStart(width, '0')
  return `${m}:${sec}`
}

/** Seconds as a short duration: 4.2 -> "4.2 s", 125 -> "2 min 5 s" */
export const duration = (s) => {
  if (s == null) return '–'
  if (s < 60) return `${s.toFixed(1)} s`
  return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`
}

/** Confidence band used for colouring boxes and bars. */
export const confidenceLevel = (c) => (c >= 0.7 ? 'high' : c >= 0.5 ? 'medium' : 'low')
