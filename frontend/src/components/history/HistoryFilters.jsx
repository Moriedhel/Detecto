import { PRESETS, fromLocalInput, presetRange, toLocalInput } from '../../utils/timeRange'

const CONF_OPTIONS = [
  { value: '', label: 'Any' },
  { value: '0.5', label: '≥ 50%' },
  { value: '0.6', label: '≥ 60%' },
  { value: '0.7', label: '≥ 70%' },
  { value: '0.8', label: '≥ 80%' },
  { value: '0.9', label: '≥ 90%' },
]

/**
 * One filter row that scopes every number, chart and table row below it.
 * filters: { preset, start, end, minConfidence, minCount }
 */
export default function HistoryFilters({ filters, onChange }) {
  const set = (patch) => onChange({ ...filters, ...patch })

  const choosePreset = (id) => {
    if (id === 'custom') {
      set({ preset: 'custom' }) // keep the current range as the starting point
    } else {
      set({ preset: id, ...presetRange(id) })
    }
  }

  return (
    <div className="filters" role="group" aria-label="History filters">
      <div className="segmented" role="radiogroup" aria-label="Time range">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            role="radio"
            aria-checked={filters.preset === p.id}
            className={filters.preset === p.id ? 'active' : undefined}
            onClick={() => choosePreset(p.id)}
          >
            {p.label}
          </button>
        ))}
      </div>

      {filters.preset === 'custom' && (
        <>
          <label className="filter-field">
            <span>From</span>
            <input
              type="datetime-local"
              value={toLocalInput(filters.start)}
              onChange={(e) => set({ start: fromLocalInput(e.target.value) })}
            />
          </label>
          <label className="filter-field">
            <span>To</span>
            <input
              type="datetime-local"
              value={toLocalInput(filters.end)}
              onChange={(e) => set({ end: fromLocalInput(e.target.value) })}
            />
          </label>
        </>
      )}

      <label className="filter-field">
        <span>Min. confidence</span>
        <select
          value={filters.minConfidence ?? ''}
          onChange={(e) => set({ minConfidence: e.target.value === '' ? null : Number(e.target.value) })}
        >
          {CONF_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </label>

      <label className="filter-field">
        <span>Min. people</span>
        <input
          type="number"
          min="0"
          step="1"
          inputMode="numeric"
          className="narrow"
          placeholder="Any"
          value={filters.minCount ?? ''}
          onChange={(e) => {
            const v = e.target.value
            set({ minCount: v === '' ? null : Math.max(0, Math.floor(Number(v))) })
          }}
        />
      </label>
    </div>
  )
}
