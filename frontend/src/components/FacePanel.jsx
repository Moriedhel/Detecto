import { useCallback, useEffect, useState } from 'react'

import { deletePerson, enrollPerson, getPeople } from '../api'
import { ALLOWED_TYPES } from '../config'
import { validateImageFile } from '../utils/validation'

/**
 * Face recognition controls for webcam mode: on/off toggle, enrolled people,
 * and an enrolment form (name + photos + consent). Only face features
 * (embeddings) are stored on the server, never the photos.
 */
export default function FacePanel({ enabled, onToggle }) {
  const [state, setState] = useState({ loading: true, available: true, people: [] })
  const [name, setName] = useState('')
  const [files, setFiles] = useState([])
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null) // { kind: 'error' | 'ok', text, results? }
  const [fileKey, setFileKey] = useState(0) // resets the file input after enrolment

  const load = useCallback(async () => {
    try {
      const res = await getPeople()
      setState({ loading: false, available: res.available, people: res.people })
    } catch (err) {
      setState((s) => ({ ...s, loading: false }))
      setMessage({ kind: 'error', text: err.message })
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const enroll = async (e) => {
    e.preventDefault()
    const bad = files.map(validateImageFile).find(Boolean)
    if (bad) {
      setMessage({ kind: 'error', text: bad })
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      const res = await enrollPerson(name, files, { consent })
      const used = res.results.filter((r) => r.ok).length
      setMessage({
        kind: 'ok',
        text: `Enrolled ${res.person.name}: ${used} of ${res.results.length} photos used.`,
        results: res.results.filter((r) => !r.ok),
      })
      setName('')
      setFiles([])
      setConsent(false)
      setFileKey((k) => k + 1)
      load()
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const remove = async (person) => {
    setMessage(null)
    try {
      await deletePerson(person.id)
      setMessage({ kind: 'ok', text: `Deleted ${person.name} and their face data.` })
      load()
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    }
  }

  const canSubmit = name.trim() && files.length > 0 && consent && !busy

  return (
    <fieldset className="controls face-panel">
      <legend>Face recognition</legend>

      {!state.available ? (
        <p className="hint">
          Face models are missing on the server. Run <code>scripts/download_face_models.py</code> and restart the backend.
        </p>
      ) : (
        <>
          <label className="control checkbox">
            <input type="checkbox" checked={enabled} onChange={(e) => onToggle(e.target.checked)} />
            <span>Recognise enrolled faces</span>
          </label>

          <div>
            <span className="control-title">Enrolled people</span>
            {state.loading ? (
              <p className="hint">Loading…</p>
            ) : state.people.length === 0 ? (
              <p className="hint">Nobody enrolled yet. Faces will show as “Unknown”.</p>
            ) : (
              <ul className="people-list">
                {state.people.map((p) => (
                  <li key={p.id}>
                    <span className="person-name">{p.name}</span>
                    <span className="hint">{p.photos} {p.photos === 1 ? 'photo' : 'photos'}</span>
                    <button
                      type="button"
                      className="icon-button"
                      onClick={() => remove(p)}
                      aria-label={`Delete ${p.name}`}
                      title="Delete this person and their face data"
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <form className="enroll-form" onSubmit={enroll}>
            <span className="control-title">Add a person</span>
            <label className="filter-field">
              <span>Name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} placeholder="e.g. Maria" />
            </label>
            <label className="filter-field">
              <span>Photos (one face each, front-facing)</span>
              <input
                key={fileKey}
                type="file"
                multiple
                accept={ALLOWED_TYPES.join(',')}
                onChange={(e) => setFiles([...e.target.files])}
              />
            </label>
            <label className="control checkbox">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              <span>This person agreed to have their face enrolled</span>
            </label>
            <button type="submit" className="button primary" disabled={!canSubmit}>
              {busy ? 'Enrolling…' : 'Enrol'}
            </button>
            <span className="hint">Photos are not stored: only face features, deleted with the person.</span>
          </form>
        </>
      )}

      {message && (
        <div className={`face-message ${message.kind}`} role={message.kind === 'error' ? 'alert' : 'status'}>
          {message.text}
          {message.results?.length > 0 && (
            <ul>
              {message.results.map((r) => (
                <li key={r.file}>{r.file}: {r.reason}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </fieldset>
  )
}
