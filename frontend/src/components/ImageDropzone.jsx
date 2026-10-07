import { useState } from 'react'

import { ALLOWED_TYPES, MAX_UPLOAD_MB } from '../config'

// Drag-and-drop area that also works as a click/keyboard file picker.
export default function ImageDropzone({ onFile, disabled = false, compact = false }) {
  const [dragging, setDragging] = useState(false)

  const pick = (files) => {
    if (!disabled && files && files.length > 0) onFile(files[0])
  }

  const onDragOver = (e) => {
    e.preventDefault()
    if (!disabled) setDragging(true)
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    pick(e.dataTransfer.files)
  }

  return (
    <label
      className={`dropzone${dragging ? ' dragging' : ''}${compact ? ' compact' : ''}${disabled ? ' disabled' : ''}`}
      onDragOver={onDragOver}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <input
        type="file"
        className="visually-hidden"
        accept={ALLOWED_TYPES.join(',')}
        disabled={disabled}
        aria-label="Choose an image"
        onChange={(e) => {
          pick(e.target.files)
          e.target.value = '' // allow choosing the same file again
        }}
      />
      <span className="dropzone-title">{compact ? 'Choose another image' : 'Drop an image here'}</span>
      {!compact && (
        <span className="dropzone-hint">
          or click to browse · JPEG or PNG · up to {MAX_UPLOAD_MB} MB
        </span>
      )}
    </label>
  )
}
