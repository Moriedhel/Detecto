import { useState } from 'react'

import { resetHistory } from '../../api'

// "Clear history" with an inline confirmation step. /reset deletes ALL records,
// regardless of the current filters, and the message says so.
// `total` is the number of stored records when known (no filters active), else null.
export default function ResetHistory({ total, disabled = false, onDone, onError }) {
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)

  const confirm = async () => {
    setBusy(true)
    try {
      const { deleted } = await resetHistory()
      setConfirming(false)
      onDone(deleted)
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (!confirming) {
    return (
      <button type="button" className="button danger-outline" onClick={() => setConfirming(true)} disabled={disabled}>
        Clear history
      </button>
    )
  }

  const what = total != null ? `all ${total.toLocaleString()} stored detections` : 'all stored detections'

  return (
    <div className="confirm" role="alertdialog" aria-label="Confirm clearing history">
      <span>
        Delete <strong>{what}</strong>? This ignores the filters and cannot be undone.
      </span>
      <button type="button" className="button" onClick={() => setConfirming(false)} disabled={busy}>
        Cancel
      </button>
      <button type="button" className="button danger" onClick={confirm} disabled={busy}>
        {busy ? 'Deleting…' : 'Delete all'}
      </button>
    </div>
  )
}
