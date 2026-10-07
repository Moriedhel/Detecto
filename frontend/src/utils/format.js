// Display formatting helpers.

/** 0.873 -> "87%"; null -> "–" */
export const pct = (v) => (v == null ? '–' : `${Math.round(v * 100)}%`)

/** 12.34 -> "12 ms"; 1234 -> "1.23 s"; null -> "–" */
export const ms = (v) => {
  if (v == null) return '–'
  return v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${Math.round(v)} ms`
}

/** Confidence band used for colouring boxes and bars. */
export const confidenceLevel = (c) => (c >= 0.7 ? 'high' : c >= 0.5 ? 'medium' : 'low')
