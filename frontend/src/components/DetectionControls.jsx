import { pct } from '../utils/format'

// Detection settings. Changes are applied with an explicit re-run, since every
// run is stored in history (dragging the slider shouldn't create many records).
export default function DetectionControls({ settings, onChange, onRerun, canRerun, disabled = false }) {
  return (
    <fieldset className="controls" disabled={disabled}>
      <legend>Settings</legend>

      <label className="control">
        <span className="control-row">
          <span>Confidence threshold</span>
          <output>{pct(settings.conf)}</output>
        </span>
        <input
          type="range"
          min="0.05"
          max="0.95"
          step="0.05"
          value={settings.conf}
          onChange={(e) => onChange({ ...settings, conf: Number(e.target.value) })}
        />
        <span className="hint">Lower finds more people but adds false alarms.</span>
      </label>

      <label className="control checkbox">
        <input
          type="checkbox"
          checked={settings.enhance}
          onChange={(e) => onChange({ ...settings, enhance: e.target.checked })}
        />
        <span>Contrast boost (CLAHE) for dark images</span>
      </label>

      {canRerun && (
        <button type="button" className="button primary" onClick={onRerun}>
          Re-run detection
        </button>
      )}
    </fieldset>
  )
}
