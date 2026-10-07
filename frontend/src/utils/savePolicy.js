/**
 * Decides which live frames are stored in history, so a webcam running at
 * ~10 fps produces a useful time series instead of thousands of rows.
 *
 * A frame is saved when:
 *   - it is the first frame of the session,
 *   - the people count has changed AND stayed at the new value for
 *     `stableFrames` consecutive frames (ignores one-frame flicker), or
 *   - `intervalMs` has passed since the last save (periodic snapshot).
 */
export function createSavePolicy({ onChange = true, intervalMs = null, stableFrames = 3 } = {}) {
  let lastSaveAt = null
  let lastSavedCount = null
  let candidate = null
  let streak = 0

  return {
    /** Call before sending a frame: should this one be saved? */
    shouldSave(now) {
      if (!onChange && intervalMs == null) return false // saving disabled
      if (lastSaveAt == null) return true
      if (intervalMs != null && now - lastSaveAt >= intervalMs) return true
      return onChange && streak >= stableFrames
    },

    /** Call with each frame's people count. */
    observe(count) {
      if (count === lastSavedCount) {
        candidate = null
        streak = 0
      } else if (count === candidate) {
        streak += 1
      } else {
        candidate = count
        streak = 1
      }
    },

    /** Call when a frame was actually saved. */
    markSaved(now, count) {
      lastSaveAt = now
      lastSavedCount = count
      candidate = null
      streak = 0
    },
  }
}

// Options offered in the UI
export const SAVE_PRESETS = {
  'change+30s': { label: 'On count change + every 30 s', onChange: true, intervalMs: 30000 },
  change: { label: 'On count change only', onChange: true, intervalMs: null },
  '5s': { label: 'Every 5 s', onChange: false, intervalMs: 5000 },
  off: { label: "Don't save", onChange: false, intervalMs: null },
}
export const DEFAULT_SAVE_PRESET = 'change+30s'
