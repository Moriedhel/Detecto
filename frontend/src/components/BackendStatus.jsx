import { useEffect, useState } from 'react'

import { getHealth } from '../api'

const POLL_MS = 15000

// Small badge showing whether the API is reachable, and which model/device it runs.
export default function BackendStatus() {
  const [state, setState] = useState({ status: 'checking', info: null })

  useEffect(() => {
    const controller = new AbortController()

    const check = async () => {
      try {
        const info = await getHealth({ signal: controller.signal })
        setState({ status: info.model_loaded ? 'online' : 'loading', info })
      } catch (err) {
        if (err.name !== 'AbortError') setState({ status: 'offline', info: null })
      }
    }

    check()
    const id = setInterval(check, POLL_MS)
    return () => {
      controller.abort()
      clearInterval(id)
    }
  }, [])

  const { status, info } = state
  const label = {
    checking: 'Checking API…',
    online: `API online · ${info?.model} · ${info?.device}`,
    loading: 'API starting…',
    offline: 'API offline',
  }[status]

  return (
    <div className={`status status-${status}`} role="status" title={label}>
      <span className="status-dot" aria-hidden="true" />
      <span className="status-label">{label}</span>
    </div>
  )
}
