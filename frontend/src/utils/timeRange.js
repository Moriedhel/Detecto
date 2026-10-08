// Date-range presets and helpers for the History filters (all in the browser's local time).

export const PRESETS = [
  { id: 'all', label: 'All time' },
  { id: '1h', label: 'Last hour' },
  { id: 'today', label: 'Today' },
  { id: '7d', label: 'Last 7 days' },
  { id: 'custom', label: 'Custom' },
]

/** Resolve a preset to { start, end } as ISO strings (null = open-ended). */
export function presetRange(id, now = new Date()) {
  switch (id) {
    case '1h':
      return { start: new Date(now.getTime() - 3600_000).toISOString(), end: null }
    case 'today': {
      const midnight = new Date(now)
      midnight.setHours(0, 0, 0, 0)
      return { start: midnight.toISOString(), end: null }
    }
    case '7d':
      return { start: new Date(now.getTime() - 7 * 86400_000).toISOString(), end: null }
    default:
      return { start: null, end: null }
  }
}

/** ISO string -> value for <input type="datetime-local"> (local time, minutes). */
export function toLocalInput(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** <input type="datetime-local"> value -> ISO string (UTC), or null when empty/invalid. */
export function fromLocalInput(value) {
  if (!value) return null
  const d = new Date(value) // parsed as local time
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

/** Local date+time for tables and tooltips. */
export const formatDateTime = (iso) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'medium' })
